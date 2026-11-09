"""Prepare -> protect -> protocol authentication -> send, with bounded responses.

No SDK responses, clients or credentials cross this adapter. HTTP and WebSocket
transports never follow redirects or inherit environment proxy/credential files.
"""
import base64
from dataclasses import replace
import hashlib
import hmac
import json
from urllib.parse import urlencode

import requests
from websockets.sync.client import connect

from data_security.contracts import (AIRequest, AIResponse, BoundedPayload, ContractViolation,
    EmbeddingResult, FrozenJSON, KeyPurpose, KeyStatus, MediaType, Outlet, PayloadKind,
    ProtectedResult, ProtectionError, ReasonCode)
from data_security.contracts.schema import require

ENDPOINTS = {
    'volcano': 'https://ark.cn-beijing.volces.com/api/v3',
    'deepseek': 'https://api.deepseek.com',
    'moonshot': 'https://api.moonshot.cn/v1',
    'qwen': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'wenxin': 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat',
    'spark': 'wss://spark-api.xf-yun.com/v3.5/chat',
}
WENXIN_MODELS = {'ernie-bot-4': 'completions_pro', 'ernie-bot': 'completions'}
MAX_RESPONSE_BYTES = 1024 * 1024


class OfficialAI:
    def __init__(self, *, endpoint_ref, base_url, models, key_ref, keys,
                 protection, confidentiality, limits, service_identity, clock):
        require(endpoint_ref in ENDPOINTS and base_url == ENDPOINTS[endpoint_ref],
                ReasonCode.AUTHORIZATION_DENIED)
        require(type(models) is tuple and 0 < len(models) <= 16, ReasonCode.INVALID_VALUE)
        require(key_ref.purpose is KeyPurpose.PROVIDER and key_ref.status is KeyStatus.ACTIVE and
                key_ref.key_ref.split('/')[1] == endpoint_ref, ReasonCode.KEY_UNAVAILABLE)
        self.endpoint_ref, self.base_url, self.models = endpoint_ref, base_url, models
        self.key_ref, self.keys, self.protection = key_ref, keys, protection
        self.confidentiality, self.limits = confidentiality, limits
        self.service_identity, self.clock = service_identity, clock

    def _json(self, value):
        return BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.JSON,
            media_type=MediaType.JSON, text=None, tree=FrozenJSON(value), binary=None, limits=self.limits)

    def _protect(self, payload, context, binding):
        result = self.protection.protect(payload, context, binding)
        if type(result) is ProtectionError:
            raise ContractViolation(result.code)
        require(type(result) is ProtectedResult, ReasonCode.SCOPE_INCOMPLETE)
        return result.payload

    def _http(self, url, *, body=None, headers=None, params=None, form=None):
        with requests.Session() as session:
            session.trust_env = False
            with session.post(url, json=body, headers=headers, params=params, data=form,
                              timeout=(10, 60), stream=True, allow_redirects=False) as response:
                require(response.status_code == 200, ReasonCode.PROVIDER_UNAVAILABLE)
                chunks, size = [], 0
                for chunk in response.iter_content(8192):
                    size += len(chunk)
                    require(size <= MAX_RESPONSE_BYTES, ReasonCode.LIMIT_EXCEEDED)
                    chunks.append(chunk)
                return b''.join(chunks)

    def _run(self, request, context, binding, *, embedding=False, streaming=False):
        stage = ReasonCode.PROVIDER_UNAVAILABLE
        try:
            require(type(request) is AIRequest and request.endpoint_ref == self.endpoint_ref and
                    request.model_ref in self.models, ReasonCode.AUTHORIZATION_DENIED)
            require(context.actor_ref == self.service_identity and context.outlet is
                    (Outlet.EMBEDDING if embedding else Outlet.MODEL), ReasonCode.AUTHORIZATION_DENIED)
            neutral = request.content.tree.to_value() if request.content.kind is PayloadKind.JSON else None
            require(type(neutral) is dict and set(neutral) == ({'input'} if embedding else {'messages'}),
                    ReasonCode.INVALID_VALUE)
            if embedding:
                require(self.endpoint_ref in ('volcano', 'qwen'), ReasonCode.UNSUPPORTED_SCOPE)
                require(type(neutral['input']) is list and 0 < len(neutral['input']) <= 1024 and
                        all(type(value) is str for value in neutral['input']), ReasonCode.INVALID_VALUE)
                prepared = {'model': request.model_ref, 'input': neutral['input'], 'encoding_format': 'float'}
            else:
                messages = neutral['messages']
                require(type(messages) is list and 0 < len(messages) <= 64, ReasonCode.LIMIT_EXCEEDED)
                require(all(type(m) is dict and set(m) == {'role', 'content'} and
                            m['role'] in ('system', 'user', 'assistant') and type(m['content']) is str
                            for m in messages), ReasonCode.INVALID_VALUE)
                prepared = {'model': request.model_ref, 'messages': messages,
                    'temperature': request.temperature, 'max_tokens': request.output_token_limit,
                    'stream': streaming}
                if self.endpoint_ref == 'wenxin':
                    require(request.model_ref in WENXIN_MODELS, ReasonCode.AUTHORIZATION_DENIED)
                    prepared = {'messages': [m for m in messages if m['role'] != 'system'],
                        'system': '\n'.join(m['content'] for m in messages if m['role'] == 'system'),
                        'temperature': request.temperature, 'max_output_tokens': request.output_token_limit,
                        'stream': streaming}
                elif self.endpoint_ref == 'spark':
                    require(request.model_ref == 'generalv3.5', ReasonCode.AUTHORIZATION_DENIED)
                    prepared = {'parameter': {'chat': {'domain': request.model_ref,
                        'temperature': request.temperature, 'max_tokens': request.output_token_limit}},
                        'payload': {'message': {'text': messages}}}
            # Legacy credential confidentiality is injected, not a fourth Detect category.
            prepared = self.confidentiality(prepared)
            stage = ReasonCode.SCOPE_INCOMPLETE
            prepared = self._protect(self._json(prepared), context, binding).tree.to_value()
            stage = ReasonCode.KEY_UNAVAILABLE
            material = self.keys.resolve(self.key_ref, KeyPurpose.PROVIDER, self.service_identity)
            if type(material) is ProtectionError:
                raise ContractViolation(material.code)
            credential = bytes(material.borrow(KeyPurpose.PROVIDER)).decode('utf-8')
            parts = credential.split('|')
            require(all(parts) and len(parts) == (3 if self.endpoint_ref == 'spark' else
                    2 if self.endpoint_ref == 'wenxin' else 1), ReasonCode.KEY_UNAVAILABLE)
            require(all('\r' not in part and '\n' not in part for part in parts), ReasonCode.KEY_UNAVAILABLE)
            # A caller knowing a credential still cannot smuggle it into ordinary fields.
            encoded = json.dumps(prepared, ensure_ascii=False)
            require(not any(part in encoded for part in parts), ReasonCode.AUTHORIZATION_DENIED)
            stage = ReasonCode.PROVIDER_UNAVAILABLE
            if self.endpoint_ref == 'spark':
                app_id, api_key, api_secret = parts
                date = self.clock().strftime('%a, %d %b %Y %H:%M:%S GMT')
                host, path = 'spark-api.xf-yun.com', '/v3.5/chat'
                signing = f'host: {host}\ndate: {date}\nGET {path} HTTP/1.1'
                signature = base64.b64encode(hmac.new(api_secret.encode(), signing.encode(),
                                                     hashlib.sha256).digest()).decode()
                authorization = base64.b64encode((f'api_key="{api_key}", algorithm="hmac-sha256", '
                    f'headers="host date request-line", signature="{signature}"').encode()).decode()
                url = self.base_url + '?' + urlencode({'authorization': authorization, 'date': date, 'host': host})
                prepared['header'] = {'app_id': app_id}
                chunks, size = [], 0
                with connect(url, proxy=None, open_timeout=10, close_timeout=10,
                             max_size=MAX_RESPONSE_BYTES) as socket:
                    socket.send(json.dumps(prepared, ensure_ascii=False))
                    for _ in range(1024):
                        raw = socket.recv(timeout=60)
                        size += len(raw.encode() if type(raw) is str else raw)
                        require(size <= MAX_RESPONSE_BYTES, ReasonCode.LIMIT_EXCEEDED)
                        item = json.loads(raw)
                        require(item['header']['code'] == 0, ReasonCode.PROVIDER_UNAVAILABLE)
                        choices = item['payload']['choices']
                        chunks.extend(part['content'] for part in choices['text'])
                        if choices['status'] == 2:
                            break
                    else:
                        raise ContractViolation(ReasonCode.LIMIT_EXCEEDED)
                content, usage = ''.join(chunks), {}
            else:
                headers, params = None, None
                if self.endpoint_ref == 'wenxin':
                    token = json.loads(self._http('https://aip.baidubce.com/oauth/2.0/token',
                        form={'grant_type': 'client_credentials', 'client_id': parts[0], 'client_secret': parts[1]}))
                    access_token = token['access_token']
                    require(type(access_token) is str and 0 < len(access_token) <= 4096,
                            ReasonCode.PROVIDER_UNAVAILABLE)
                    params = {'access_token': access_token}
                    url = self.base_url + '/' + WENXIN_MODELS[request.model_ref]
                    parts.append(access_token)
                else:
                    url = self.base_url + ('/embeddings' if embedding else '/chat/completions')
                    headers = {'Authorization': 'Bearer ' + credential}
                raw = self._http(url, body=prepared, headers=headers, params=params)
                if streaming:
                    chunks, usage, finished = [], {}, False
                    for line in raw.decode('utf-8').splitlines():
                        if not line.startswith('data:'):
                            continue
                        value = line[5:].strip()
                        if value == '[DONE]':
                            finished = True
                            continue
                        item = json.loads(value)
                        if self.endpoint_ref == 'wenxin':
                            require('error_code' not in item, ReasonCode.PROVIDER_UNAVAILABLE)
                            chunks.append(item.get('result', ''))
                            finished = finished or item.get('is_end') is True
                        else:
                            for choice in item.get('choices', []):
                                chunks.append(choice.get('delta', {}).get('content') or '')
                        usage = item.get('usage') or usage
                    require(finished, ReasonCode.PROVIDER_UNAVAILABLE)
                    content = ''.join(chunks)
                else:
                    result = json.loads(raw)
                    require('error' not in result and 'error_code' not in result, ReasonCode.PROVIDER_UNAVAILABLE)
                    if embedding:
                        vectors = tuple(tuple(float(value) for value in item['embedding'])
                                        for item in sorted(result['data'], key=lambda item: item['index']))
                        require(len(vectors) == len(prepared['input']), ReasonCode.PROVIDER_UNAVAILABLE)
                        return EmbeddingResult(schema_version=EmbeddingResult.SCHEMA, vectors=vectors,
                            endpoint_ref=self.endpoint_ref, model_ref=request.model_ref, trace_id=context.trace_id)
                    content = result['result'] if self.endpoint_ref == 'wenxin' else result['choices'][0]['message']['content']
                    usage = result.get('usage') or {}
            require(type(content) is str, ReasonCode.PROVIDER_UNAVAILABLE)
            for part in parts:
                content = content.replace(part, '[REDACTED]')
            content = self.confidentiality(content)
            payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
                media_type=MediaType.TEXT, text=content, tree=None, binary=None, limits=self.limits)
            protected = self._protect(payload, replace(context, outlet=Outlet.API), binding)
            return AIResponse(schema_version=AIResponse.SCHEMA, content=protected,
                endpoint_ref=self.endpoint_ref, model_ref=request.model_ref,
                input_tokens=usage.get('prompt_tokens') or 0, output_tokens=usage.get('completion_tokens') or 0,
                trace_id=context.trace_id)
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                retryable=False, trace_id=context.trace_id)
        except Exception:
            # The exception may contain URLs, request bodies or provider credentials.
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=stage,
                retryable=False, trace_id=context.trace_id)

    def chat(self, request, context, binding):
        return self._run(request, context, binding)

    def stream(self, request, context, binding):
        result = self._run(request, context, binding, streaming=True)
        if type(result) is ProtectionError:
            yield result
            return
        # No chunk escapes before the complete bounded result passes protection.
        for start in range(0, max(1, len(result.content.text)), 512):
            yield replace(result, content=replace(result.content, text=result.content.text[start:start + 512]))

    def embed(self, request, context, binding):
        return self._run(request, context, binding, embedding=True)
