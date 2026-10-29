import http.client
import io
import json
from email.message import Message
from unittest.mock import Mock, call, mock_open, patch
from urllib.error import HTTPError, URLError
from urllib.response import addinfourl

import yaml
from django.test import SimpleTestCase, override_settings

from evaluation_center import gateway


class Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@override_settings(EVALUATION_LIVE_GATEWAY_ENABLED=True, EVALUATION_ISOLATED_TESTS=True,
                   ROOT_URLCONF='evaluation_center.test_urls', EVALUATION_GATEWAY_KEY_INDEX=0)
class GatewayTests(SimpleTestCase):
    def setUp(self):
        # Both credential access and transport are mocked for EVERY test. Socket
        # tripwires additionally prevent accidental network if a mock is bypassed.
        self.key = 'unit-test-secret-never-output'
        self.clock = Clock()
        self.patch('socket.socket.connect', side_effect=AssertionError('network forbidden'))
        self.patch('socket.create_connection', side_effect=AssertionError('network forbidden'))
        self.files = self.patch('evaluation_center.gateway.open', mock_open(
            read_data=f'api-keys:\n  - {self.key}\n  - second-unit-test-key\n'))
        self.patch('evaluation_center.gateway.time.monotonic', side_effect=self.clock.monotonic)
        self.sleep = self.patch('evaluation_center.gateway.time.sleep', side_effect=self.clock.advance)
        self.real_build_opener = gateway.request.build_opener
        self.transport = Mock()
        self.builder = self.patch('evaluation_center.gateway.request.build_opener',
                                  return_value=self.transport)
        self.config = {'model_id': 'deepseek-v4-flash', 'prompt_version': 'm8-prompt/1',
                       'temperature': 0, 'max_tokens': 256}
        self.messages = [{'role': 'system', 'content': 'Return the action JSON object only.'},
                         {'role': 'user', 'content': 'Synthetic server-owned case.'}]
        self.transport.open.side_effect = self.success

    def patch(self, target, *args, **kwargs):
        patcher = patch(target, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def response(self, envelope=None, *, raw=None, status=200, headers=None):
        if raw is None:
            envelope = envelope if envelope is not None else self.envelope()
            raw = json.dumps(envelope).encode('utf-8')
        response = Mock(status=status, headers=headers or {})
        response.read.return_value = raw
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def envelope(self, content='{"action":"allow"}', **overrides):
        return {'choices': [{'message': {'content': content, 'reasoning_content': self.key},
                             'finish_reason': 'stop'}],
                'model': 'deepseek-v4-flash',
                'usage': {'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15},
                'id': self.key, **overrides}

    def success(self, *args, **kwargs):
        self.clock.advance(0.125)
        return self.response()

    def complete(self, **kwargs):
        return gateway.call_completion(self.config, self.messages,
                                       deadline=kwargs.get('deadline', 200.0))

    def http_error(self, status):
        return HTTPError(gateway.COMPLETION_URL, status, self.key,
                         {'x-request-id': self.key}, io.BytesIO(self.key.encode()))

    def assert_sanitized(self, result):
        self.assertNotIn(self.key, json.dumps(result))
        self.assertEqual(set(result), {'status', 'output', 'usage', 'response_model', 'attempts', 'error'})
        for attempt in result['attempts']:
            self.assertEqual(set(attempt), {'status', 'error', 'http_status', 'elapsed_ms'})

    def test_minimal_pinned_body_and_normalized_result(self):
        self.config.update(url='http://attacker.invalid/', endpoint='file:///secret',
                           proxy='http://attacker.invalid', api_key='not-selected',
                           key_index=1, role='admin', messages=[{'role': 'tool', 'content': 'injected'}],
                           tools=[{'name': 'execute'}], stream=True)
        result = self.complete()
        req = self.transport.open.call_args.args[0]
        self.assertEqual(req.full_url, 'http://127.0.0.1:8317/v1/chat/completions')
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(req.get_header('Authorization'), 'Bearer ' + self.key)
        self.assertEqual(json.loads(req.data), {
            'model': 'deepseek-v4-flash', 'messages': self.messages,
            'temperature': 0, 'max_tokens': 256, 'stream': False})
        self.assertEqual(self.transport.open.call_args.kwargs, {'timeout': 30})
        self.assertEqual(result, {
            'status': 'ok', 'output': {'action': 'allow'},
            'usage': {'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15},
            'response_model': 'deepseek-v4-flash', 'error': None,
            'attempts': [{'status': 'ok', 'error': None, 'http_status': 200, 'elapsed_ms': 125.0}]})
        self.files.assert_called_once_with('/home/hatch/workspace/cliproxyapi/config.yaml', encoding='utf-8')
        self.assert_sanitized(result)
        self.sleep.assert_not_called()

    def test_nested_client_access_keys_not_upstream_provider_groups(self):
        config = ('server:\n  port: 8317\naccess:\n  api-keys:\n    - ' + self.key +
                  '\napi-keys:\n  provider-group:\n    - api-key: upstream-test-only\n')
        with patch('evaluation_center.gateway.open', mock_open(read_data=config)):
            result = self.complete()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(self.transport.open.call_args.args[0].get_header('Authorization'), 'Bearer ' + self.key)
        self.assert_sanitized(result)

    def test_invalid_client_section_does_not_fall_back_to_upstream_keys(self):
        config = 'access:\n  api-keys: {}\napi-keys:\n  - upstream-test-only\n'
        with patch('evaluation_center.gateway.open', mock_open(read_data=config)):
            result = self.complete()
        self.assertEqual(result['error'], 'credentials_unavailable')
        self.transport.open.assert_not_called()

    def test_second_allowlisted_model_and_all_labels(self):
        self.config['model_id'] = 'deepseek-v4.1'
        for action in ('allow', 'require_approval', 'deny', 'mask'):
            with self.subTest(action=action):
                self.transport.open.side_effect = None
                self.transport.open.return_value = self.response(self.envelope(json.dumps({'action': action})))
                self.assertEqual(self.complete()['output'], {'action': action})
                self.assertEqual(json.loads(self.transport.open.call_args.args[0].data)['model'], 'deepseek-v4.1')

    def test_key_selection_is_server_only_and_default_is_zero(self):
        with override_settings(EVALUATION_GATEWAY_KEY_INDEX=1):
            self.assertEqual(self.complete()['status'], 'ok')
            self.assertEqual(self.transport.open.call_args.args[0].get_header('Authorization'),
                             'Bearer second-unit-test-key')
        with override_settings():
            from django.conf import settings
            del settings.EVALUATION_GATEWAY_KEY_INDEX
            self.assertEqual(self.complete()['status'], 'ok')
            self.assertEqual(self.transport.open.call_args.args[0].get_header('Authorization'),
                             'Bearer ' + self.key)

    def test_yaml_uses_safe_loader(self):
        with patch('evaluation_center.gateway.yaml.safe_load', wraps=yaml.safe_load) as loader:
            self.assertEqual(self.complete()['status'], 'ok')
        loader.assert_called_once()
        self.files().read.assert_called()

    def test_bad_keys_and_yaml_are_sanitized_before_network(self):
        values = ('', '[]', 'null', 'api-keys: []', 'api-keys: wrong', 'api-keys: [null]',
                  'api-keys: [123]', 'api-keys: [""]', 'api-keys: ["header\\ninjection"]',
                  'api-keys: ["非ASCII"]', 'api-keys: [' + self.key,
                  '!!python/object/apply:builtins.str [unsafe]',
                  'api-keys: ["' + ('a' * 4097) + '"]')
        for text in values:
            with self.subTest(text=text[:50]), patch(
                    'evaluation_center.gateway.open', mock_open(read_data=text)):
                result = self.complete()
                self.assertEqual(result['error'], 'credentials_unavailable')
                self.assertEqual(result['attempts'], [])
                self.assert_sanitized(result)
        self.transport.open.assert_not_called()

    def test_invalid_key_index_and_loader_exceptions_are_sanitized(self):
        for index in (-1, 2, True, '0', None):
            with self.subTest(index=index), override_settings(EVALUATION_GATEWAY_KEY_INDEX=index):
                result = self.complete()
                self.assertEqual(result['error'], 'credentials_unavailable')
                self.assert_sanitized(result)
        for exc in (PermissionError(self.key), yaml.YAMLError(self.key), ValueError(self.key),
                    UnicodeError(self.key), RecursionError(self.key)):
            with self.subTest(exception=type(exc).__name__), patch(
                    'evaluation_center.gateway.yaml.safe_load', side_effect=exc):
                result = self.complete()
                self.assertEqual(result['error'], 'credentials_unavailable')
                self.assert_sanitized(result)
        self.transport.open.assert_not_called()

    def test_disabled_and_production_settings_never_read_credentials(self):
        for overrides in (
            {'EVALUATION_LIVE_GATEWAY_ENABLED': False}, {'EVALUATION_LIVE_GATEWAY_ENABLED': 1},
            {'EVALUATION_LIVE_GATEWAY_ENABLED': 'true'}, {'EVALUATION_ISOLATED_TESTS': False},
            {'EVALUATION_ISOLATED_TESTS': 1}, {'ROOT_URLCONF': 'ctf_backend.urls'},
            {'ROOT_URLCONF': 'evaluation_center.test_urls.evil'},
        ):
            with self.subTest(overrides=overrides), override_settings(**overrides):
                result = self.complete()
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['attempts'], [])
        with override_settings():
            from django.conf import settings
            del settings.EVALUATION_LIVE_GATEWAY_ENABLED
            self.assertEqual(self.complete()['error'], 'gateway_disabled')
        self.files.assert_not_called()
        self.transport.open.assert_not_called()

    def test_invalid_configuration_never_reaches_loader_or_network(self):
        for field, value in (
            ('model_id', 'gpt-anything'), ('model_id', ['deepseek-v4.1']),
            ('prompt_version', None), ('prompt_version', ''), ('temperature', True),
            ('temperature', float('nan')), ('temperature', float('inf')),
            ('temperature', -1), ('max_tokens', 0), ('max_tokens', True), ('max_tokens', 1.2),
        ):
            with self.subTest(field=field, value=value):
                config = {**self.config, field: value}
                result = gateway.call_completion(config, self.messages, deadline=200)
                self.assertEqual(result['error'], 'invalid_config')
                self.assertEqual(result['attempts'], [])
        for messages in ([], [{'role': 'tool', 'content': 'no'}],
                         [{'role': 'user', 'content': 10}],
                         [{'role': 'user', 'content': 'no', 'url': 'http://attacker.invalid'}],
                         [{'role': 'user', 'content': 'x' * 16385}]):
            self.assertEqual(gateway.call_completion(self.config, messages, deadline=200)['error'],
                             'invalid_config')
        self.files.assert_not_called()
        self.transport.open.assert_not_called()

    def test_retry_statuses_have_exact_backoff_and_three_actual_attempts(self):
        for status in (429, 502, 503, 504):
            with self.subTest(status=status):
                self.transport.open.reset_mock()
                self.sleep.reset_mock()
                responses = iter((self.http_error(status), self.http_error(status), self.response()))

                def attempt(*args, **kwargs):
                    self.clock.advance(0.25)
                    value = next(responses)
                    if isinstance(value, Exception):
                        raise value
                    return value

                self.transport.open.side_effect = attempt
                result = self.complete()
                self.assertEqual(result['status'], 'ok')
                self.assertEqual(self.transport.open.call_count, 3)
                self.assertEqual(self.sleep.call_args_list, [call(2), call(4)])
                self.assertEqual([a['http_status'] for a in result['attempts']], [status, status, 200])
                self.assertEqual([a['elapsed_ms'] for a in result['attempts']], [250.0] * 3)
                self.assert_sanitized(result)

    def test_connection_and_timeout_retries_exhaust_without_exception_text(self):
        for exc, code in ((URLError(self.key), 'connection_error'),
                          (URLError(TimeoutError(self.key)), 'timeout'),
                          (ConnectionResetError(self.key), 'connection_error'),
                          (TimeoutError(self.key), 'timeout')):
            with self.subTest(exception=type(exc).__name__):
                self.sleep.reset_mock()
                self.transport.open.reset_mock()
                self.transport.open.side_effect = exc
                result = self.complete()
                self.assertEqual(result['error'], code)
                self.assertEqual(result['output'], None)
                self.assertEqual(len(result['attempts']), 3)
                self.assertEqual(self.transport.open.call_count, 3)
                self.assertEqual(self.sleep.call_args_list, [call(2), call(4)])
                self.assertTrue(all(a['http_status'] is None for a in result['attempts']))
                self.assert_sanitized(result)

    def test_http_exhaustion_retains_each_attempt_and_does_not_switch_keys(self):
        def unavailable(*args, **kwargs):
            raise self.http_error(503)

        self.transport.open.side_effect = unavailable
        result = self.complete()
        self.assertEqual(result['error'], 'upstream_unavailable')
        self.assertEqual(len(result['attempts']), 3)
        self.assertEqual([attempt['http_status'] for attempt in result['attempts']], [503] * 3)
        self.assertEqual(self.sleep.call_args_list, [call(2), call(4)])
        for dispatched in self.transport.open.call_args_list:
            self.assertEqual(dispatched.args[0].get_header('Authorization'), 'Bearer ' + self.key)
        self.assert_sanitized(result)

    def test_authentication_and_other_non_retry_errors_never_retry(self):
        for status in (401, 403, 400, 404, 500, 418, 799):
            with self.subTest(status=status):
                self.transport.open.reset_mock()
                exc = self.http_error(status)
                body = exc.fp
                self.transport.open.side_effect = exc
                result = self.complete()
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['error'], 'authentication_failed' if status == 401 else 'http_error')
                self.assertEqual(len(result['attempts']), 1)
                self.assertEqual(result['attempts'][0]['http_status'], None if status == 799 else status)
                self.assertEqual(self.transport.open.call_count, 1)
                self.assertTrue(body.closed)
                self.assert_sanitized(result)
        self.sleep.assert_not_called()

    def test_deadline_before_io_after_loading_and_between_retries(self):
        result = self.complete(deadline=100)
        self.assertEqual(result['error'], 'deadline_exceeded')
        self.assertEqual(result['attempts'], [])
        self.files.assert_not_called()
        self.transport.open.assert_not_called()
        with patch('evaluation_center.gateway.yaml.safe_load', side_effect=lambda source: (
                self.clock.advance(1), {'api-keys': [self.key]})[1]):
            result = self.complete(deadline=101)
        self.assertEqual(result['error'], 'deadline_exceeded')
        self.assertEqual(result['attempts'], [])
        self.transport.open.assert_not_called()
        self.transport.open.side_effect = self.http_error(429)
        result = self.complete(deadline=102.5)
        self.assertEqual(result['error'], 'deadline_exceeded')
        self.assertEqual(len(result['attempts']), 1)
        self.assertEqual(result['attempts'][0]['http_status'], 429)
        self.sleep.assert_not_called()

    def test_deadline_limits_timeout_and_discards_late_output(self):
        result = self.complete(deadline=100.1)
        self.assertAlmostEqual(self.transport.open.call_args.kwargs['timeout'], 0.1)
        self.assertEqual(result['error'], 'deadline_exceeded')
        self.assertIsNone(result['output'])
        self.assertEqual(result['attempts'][0]['error'], 'deadline_exceeded')
        self.assertEqual(result['usage']['total_tokens'], 15)

    def test_backoff_cannot_start_new_attempt_after_oversleep(self):
        self.transport.open.side_effect = self.http_error(503)
        self.sleep.side_effect = lambda seconds: self.clock.advance(20)
        result = self.complete(deadline=110)
        self.assertEqual(result['error'], 'deadline_exceeded')
        self.assertEqual(len(result['attempts']), 1)
        self.assertEqual(self.transport.open.call_count, 1)

    def test_bad_deadlines_are_sanitized(self):
        for deadline in (None, True, float('nan'), float('inf'), 'later'):
            self.assertEqual(self.complete(deadline=deadline)['error'], 'invalid_config')
        self.files.assert_not_called()
        self.transport.open.assert_not_called()

    def test_only_exact_json_action_object_is_accepted(self):
        invalid = ('```json\n{"action":"allow"}\n```', '{"action":"allow"',
                   '{"action":"allow","reason":"' + self.key + '"}',
                   '{"action":"ALLOW"}', '{"action":null}', '{"action":[]}',
                   '{"action":"unknown"}', '{}', '[]', 'null', '"allow"',
                   '{"action":"deny","action":"allow"}', '{"action":NaN}',
                   self.key, '{"action":"allow"} trailing text')
        for content in invalid:
            with self.subTest(content=content[:40]):
                self.transport.open.side_effect = None
                self.transport.open.return_value = self.response(self.envelope(content))
                result = self.complete()
                self.assertEqual(result['error'], 'invalid_response')
                self.assertIsNone(result['output'])
                self.assertEqual(len(result['attempts']), 1)
                self.assertEqual(result['usage']['total_tokens'], 15)
                self.assert_sanitized(result)
        self.sleep.assert_not_called()

    def test_invalid_envelope_and_truncated_responses(self):
        responses = [self.response(raw=b'{'), self.response(raw=b'\xff'),
                     self.response([]), self.response({'choices': []}),
                     self.response({'choices': [{'message': {'content': {'action': 'allow'}}}]}),
                     self.response(self.envelope(choices=[{'message': {'content': '{"action":"allow"}'},
                                                           'finish_reason': 'length'}])),
                     self.response(headers={'Content-Length': '9999999'}),
                     self.response(headers={'Content-Length': 'not-an-integer'}),
                     self.response(raw=b'x' * (128 * 1024 + 1))]
        for response in responses:
            self.transport.open.side_effect = None
            self.transport.open.return_value = response
            result = self.complete()
            self.assertEqual(result['error'], 'invalid_response')
            self.assertIsNone(result['output'])
            self.assertEqual(len(result['attempts']), 1)
            response.read.assert_called_once_with(128 * 1024 + 1)
        self.sleep.assert_not_called()

    def test_response_limit_accepts_exact_boundary_and_rejects_one_more_byte(self):
        raw = json.dumps(self.envelope()).encode().ljust(128 * 1024, b' ')
        self.transport.open.side_effect = None
        self.transport.open.return_value = self.response(raw=raw, headers={'Content-Length': str(len(raw))})
        self.assertEqual(self.complete()['status'], 'ok')
        self.transport.open.return_value = self.response(raw=raw + b' ')
        self.assertEqual(self.complete()['error'], 'invalid_response')

    def test_error_cleanup_cannot_expose_exception_or_read_error_body(self):
        exc = self.http_error(401)
        with patch.object(exc, 'close', side_effect=OSError(self.key)), \
                patch.object(exc, 'read', side_effect=AssertionError('error body must not be read')):
            self.transport.open.side_effect = exc
            result = self.complete()
        self.assertEqual(result['error'], 'authentication_failed')
        self.assertEqual(len(result['attempts']), 1)
        self.assert_sanitized(result)
        self.sleep.assert_not_called()
        exc.close()

    def test_incomplete_read_and_protocol_errors_are_not_retried(self):
        for exc in (http.client.IncompleteRead(self.key.encode(), 100),
                    http.client.BadStatusLine(self.key), OSError(self.key)):
            self.transport.open.reset_mock()
            response = self.response()
            response.read.side_effect = exc
            self.transport.open.side_effect = None
            self.transport.open.return_value = response
            result = self.complete()
            self.assertEqual(result['status'], 'error')
            self.assertEqual(self.transport.open.call_count, 1)
            self.assert_sanitized(result)
        self.sleep.assert_not_called()

    def test_usage_unknown_is_none_and_explicit_zero_is_preserved(self):
        for usage in (None, {}, [], {'prompt_tokens': True, 'completion_tokens': -1, 'total_tokens': '15'}):
            self.transport.open.side_effect = None
            self.transport.open.return_value = self.response(self.envelope(usage=usage))
            self.assertEqual(self.complete()['usage'], dict.fromkeys(gateway._USAGE_FIELDS))
        envelope = self.envelope()
        del envelope['usage']
        self.transport.open.return_value = self.response(envelope)
        self.assertEqual(self.complete()['usage'], dict.fromkeys(gateway._USAGE_FIELDS))
        self.transport.open.return_value = self.response(self.envelope(
            usage={'prompt_tokens': 0, 'completion_tokens': 2, 'total_tokens': 2.0, 'secret': self.key}))
        result = self.complete()
        self.assertEqual(result['usage'], {'prompt_tokens': 0, 'completion_tokens': 2, 'total_tokens': None})
        self.assert_sanitized(result)

    def test_response_model_is_bounded_safe_and_cannot_echo_credential(self):
        for model in (None, {}, 'a' * 129, 'model\nsecret', 'model with spaces', self.key):
            self.transport.open.side_effect = None
            self.transport.open.return_value = self.response(self.envelope(model=model))
            result = self.complete()
            self.assertIsNone(result['response_model'])
            self.assert_sanitized(result)
        self.transport.open.return_value = self.response(self.envelope(model='deepseek-v4.1-202610'))
        self.assertEqual(self.complete()['response_model'], 'deepseek-v4.1-202610')

    def test_real_opener_ignores_proxies_and_global_opener(self):
        self.builder.side_effect = self.real_build_opener
        headers = Message()
        response = addinfourl(io.BytesIO(json.dumps(self.envelope()).encode()), headers,
                              gateway.COMPLETION_URL, 200)
        response.msg = 'OK'
        with patch.dict('os.environ', {'http_proxy': 'http://attacker.invalid',
                                      'HTTP_PROXY': 'http://attacker.invalid',
                                      'ALL_PROXY': 'http://attacker.invalid', 'NO_PROXY': ''}), \
                patch('evaluation_center.gateway.request.getproxies', side_effect=AssertionError('proxy lookup')), \
                patch('evaluation_center.gateway.request.urlopen', side_effect=AssertionError('global opener')), \
                patch('evaluation_center.gateway.request.HTTPHandler.http_open', return_value=response) as local:
            result = self.complete()
        self.assertEqual(result['status'], 'ok')
        req = local.call_args.args[0]
        self.assertEqual(req.host, '127.0.0.1:8317')
        self.assertEqual(req.selector, '/v1/chat/completions')
        self.assertFalse(req.has_proxy())
        handlers = self.builder.call_args.args
        self.assertIsInstance(handlers[0], gateway.request.ProxyHandler)
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], gateway._NoRedirect)
        local.assert_called_once()

    def test_real_opener_refuses_all_redirects_without_reading_body(self):
        self.builder.side_effect = self.real_build_opener
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                headers = Message()
                headers['Location'] = 'http://attacker.invalid/' + self.key
                response = addinfourl(io.BytesIO(self.key.encode()), headers, gateway.COMPLETION_URL, status)
                response.msg = self.key
                with patch('evaluation_center.gateway.request.HTTPHandler.http_open', return_value=response) as local, \
                        patch.object(response, 'read', side_effect=AssertionError('error body must not be read')):
                    result = self.complete()
                self.assertEqual(result['error'], 'redirect_refused')
                self.assertEqual(len(result['attempts']), 1)
                self.assertEqual(result['attempts'][0]['http_status'], status)
                self.assert_sanitized(result)
                local.assert_called_once()
        self.sleep.assert_not_called()
