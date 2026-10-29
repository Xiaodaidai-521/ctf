"""Narrow, opt-in loopback transport. The core must authorize the isolated actor.

No provider registry, configurable destination, proxy, redirect, or raw provider
material crosses this boundary. Credentials exist only in the in-memory request.
"""
import http.client
import json
import math
import re
import time
from http import HTTPStatus
from urllib import error, request

import yaml
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

COMPLETION_URL = 'http://127.0.0.1:8317/v1/chat/completions'
_CONFIG_PATH = '/home/hatch/workspace/cliproxyapi/config.yaml'
_MODELS = frozenset({'deepseek-v4-flash', 'deepseek-v4.1'})
_ACTIONS = frozenset({'allow', 'require_approval', 'deny', 'mask'})
_MAX_RESPONSE_BYTES = 128 * 1024
_RETRY_STATUSES = frozenset({429, 502, 503, 504})
_HTTP_STATUSES = frozenset(int(status) for status in HTTPStatus)
_MODEL_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z')
_USAGE_FIELDS = ('prompt_tokens', 'completion_tokens', 'total_tokens')


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _unknown_usage():
    return dict.fromkeys(_USAGE_FIELDS)


def _result(attempts, error_code, *, output=None, usage=None, response_model=None):
    return {'status': 'error' if error_code else 'ok', 'output': None if error_code else output,
            'usage': usage if usage is not None else _unknown_usage(),
            'response_model': response_model, 'attempts': attempts, 'error': error_code}


def _request_body(config, messages):
    if not isinstance(config, dict) or config.get('model_id') not in _MODELS:
        return None
    version = config.get('prompt_version')
    temperature, max_tokens = config.get('temperature'), config.get('max_tokens')
    if (not isinstance(version, str) or not 1 <= len(version) <= 128 or
            type(temperature) not in (int, float) or not 0 <= temperature <= 2 or
            type(max_tokens) is not int or max_tokens < 1):
        return None
    if not isinstance(messages, list) or not 1 <= len(messages) <= 32:
        return None
    clean_messages = []
    for message in messages:
        if (not isinstance(message, dict) or set(message) != {'role', 'content'} or
                message['role'] not in ('system', 'user', 'assistant') or
                not isinstance(message['content'], str) or len(message['content']) > 16384):
            return None
        clean_messages.append({'role': message['role'], 'content': message['content']})
    body = json.dumps({'model': config['model_id'], 'messages': clean_messages,
                       'temperature': temperature, 'max_tokens': max_tokens,
                       'stream': False}, ensure_ascii=False, allow_nan=False).encode('utf-8')
    return body if len(body) <= 65536 else None


@sensitive_variables()
def _authorized_request(body):
    """Never return the key independently or include loader errors in diagnostics."""
    index = getattr(settings, 'EVALUATION_GATEWAY_KEY_INDEX', 0)
    if type(index) is not int or index < 0:
        return None
    try:
        with open(_CONFIG_PATH, encoding='utf-8') as source:
            config = yaml.safe_load(source)
        access = config.get('access') if isinstance(config, dict) else None
        # New gateway schema separates client keys from upstream provider groups.
        keys = access.get('api-keys') if isinstance(access, dict) else (
            config.get('api-keys') if isinstance(config, dict) else None)
        if not isinstance(keys, list) or index >= len(keys):
            return None
        key = keys[index]
        # HTTP credentials must be a single bounded, printable ASCII token.
        if not isinstance(key, str) or not re.fullmatch(r'[\x21-\x7e]{1,4096}', key):
            return None
        return request.Request(COMPLETION_URL, data=body, method='POST', headers={
            'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
            'Accept': 'application/json',
        })
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, TypeError, RecursionError):
        return None


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('invalid_json')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('invalid_json')


def _json(value):
    return json.loads(value, object_pairs_hook=_strict_object, parse_constant=_invalid_constant)


@sensitive_variables()
def _parse_response(raw, req):
    usage, model = _unknown_usage(), None
    try:
        envelope = _json(raw.decode('utf-8'))
        if not isinstance(envelope, dict):
            return None, usage, model
        reported_usage = envelope.get('usage')
        if isinstance(reported_usage, dict):
            usage = {name: value if type(value := reported_usage.get(name)) is int and value >= 0
                     else None for name in _USAGE_FIELDS}
        reported_model = envelope.get('model')
        key = req.get_header('Authorization')[len('Bearer '):]
        if (isinstance(reported_model, str) and _MODEL_PATTERN.fullmatch(reported_model) and
                key not in reported_model):
            model = reported_model
        choices = envelope.get('choices')
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return None, usage, model
        choice = choices[0]
        # A syntactically complete prefix is still invalid if the provider cut it off.
        if choice.get('finish_reason') not in (None, 'stop'):
            return None, usage, model
        message = choice.get('message')
        if not isinstance(message, dict) or not isinstance(message.get('content'), str):
            return None, usage, model
        output = _json(message['content'])
        if (isinstance(output, dict) and set(output) == {'action'} and
                isinstance(output['action'], str) and output['action'] in _ACTIONS):
            return {'action': output['action']}, usage, model
    except (ValueError, UnicodeError, TypeError, RecursionError):
        pass
    return None, usage, model


def _http_error(status):
    if status is not None and 300 <= status < 400:
        return 'redirect_refused'
    if status == 401:
        return 'authentication_failed'
    if status == 429:
        return 'rate_limited'
    if status in (502, 503, 504):
        return 'upstream_unavailable'
    return 'http_error'


def _safe_status(status):
    return status if type(status) is int and status in _HTTP_STATUSES else None


@sensitive_variables()
def call_completion(config, messages, *, deadline):
    """Return only normalized actions, token counts and whitelisted diagnostics.

    ``deadline`` is an absolute monotonic deadline. Retries share that budget;
    insufficient remaining time for the next backoff fails without another call.
    Attempt latency excludes backoff and credential loading. urllib timeouts bound
    blocking socket operations, not a hard cancellation of a trickling response.
    """
    attempts = []
    if getattr(settings, 'EVALUATION_LIVE_GATEWAY_ENABLED', False) is not True:
        return _result(attempts, 'gateway_disabled')
    if (getattr(settings, 'EVALUATION_ISOLATED_TESTS', False) is not True or
            getattr(settings, 'ROOT_URLCONF', None) != 'evaluation_center.test_urls'):
        return _result(attempts, 'gateway_not_isolated')
    try:
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            return _result(attempts, 'invalid_config')
        if deadline <= time.monotonic():
            return _result(attempts, 'deadline_exceeded')
        body = _request_body(config, messages)
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        return _result(attempts, 'invalid_config')
    if body is None:
        return _result(attempts, 'invalid_config')
    req = _authorized_request(body)
    if req is None:
        return _result(attempts, 'credentials_unavailable')
    # An explicit empty proxy map disables environment/system proxies. A fresh
    # opener also avoids any process-global installed opener or auth handlers.
    opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())
    for attempt_number in range(3):
        started = time.monotonic()
        if started >= deadline:
            return _result(attempts, 'deadline_exceeded')
        status, output, model = None, None, None
        usage, retry = _unknown_usage(), False
        try:
            with opener.open(req, timeout=min(30, deadline - started)) as response:
                status = _safe_status(response.status)
                if status != 200:
                    code, retry = _http_error(status), status in _RETRY_STATUSES
                else:
                    raw = response.read(_MAX_RESPONSE_BYTES + 1)
                    content_length = response.headers.get('Content-Length')
                    if (len(raw) > _MAX_RESPONSE_BYTES or
                            (content_length is not None and int(content_length) != len(raw))):
                        code = 'invalid_response'
                    else:
                        output, usage, model = _parse_response(raw, req)
                        code = None if output is not None else 'invalid_response'
        except error.HTTPError as exc:
            status = _safe_status(exc.code)
            code, retry = _http_error(status), status in _RETRY_STATUSES
            # Never read/log an error body, reason, Location or request identifier.
            try:
                exc.close()
            except (OSError, http.client.HTTPException):
                pass
        except TimeoutError:
            code, retry = 'timeout', True
        except error.URLError as exc:
            code = 'timeout' if isinstance(exc.reason, TimeoutError) else 'connection_error'
            retry = True
        except ConnectionError:
            code, retry = 'connection_error', True
        except (http.client.HTTPException, ValueError, TypeError, UnicodeError, RecursionError):
            code = 'invalid_response'
        except OSError:
            code = 'transport_error'
        finished = time.monotonic()
        if finished >= deadline:
            code, output, retry = 'deadline_exceeded', None, False
        attempts.append({'status': 'error' if code else 'ok', 'error': code,
                         'http_status': status, 'elapsed_ms': max(0.0, (finished - started) * 1000)})
        if not retry or attempt_number == 2:
            return _result(attempts, code, output=output, usage=usage, response_model=model)
        delay = (2, 4)[attempt_number]
        if deadline - time.monotonic() <= delay:
            return _result(attempts, 'deadline_exceeded')
        time.sleep(delay)
