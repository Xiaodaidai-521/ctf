"""Pure official tool-call protocol tests: in-memory keys, no database or temp files."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import secrets
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from ai_providers import Message, ProviderHandle
from ctf_backend.security_bootstrap import _confidentiality
from data_security.adapters.django.canary_tools import CanaryToolRegistry
from data_security.adapters.llm.official import ENDPOINTS, MAX_RESPONSE_BYTES, OfficialAI
from data_security.application.policy_catalog import PolicyCatalog
from data_security.application.protection import ProtectionService
from data_security.contracts import (
    AIRequest, AIResponse, BASELINE_LIMITS, BoundedPayload, Environment, FrozenJSON,
    KeyPurpose, KeyReference, KeyStatus, MediaType, Outlet, PayloadKind, PolicyBinding,
    PolicySnapshot, ProtectionContext, ProtectionError, Purpose, ReasonCode, SecretMaterial,
)
from data_security.tests.fixtures import dto, examples
from data_security.tests.phase3_fixtures import MODELS
from data_security.tests.test_phase3_official import AT, DurableAudit


def tool_call(name='canary_check', arguments=None, call_id='call_1'):
    return {'id': call_id, 'type': 'function', 'function': {'name': name,
        'arguments': json.dumps({'artifact_ref': 'output/1'} if arguments is None else arguments)}}


def tool_response(calls=None, content=None, finish='tool_calls'):
    return {'choices': [{'message': {'role': 'assistant', 'content': content,
        'tool_calls': [tool_call()] if calls is None else calls}, 'finish_reason': finish}],
        'usage': {'prompt_tokens': 3, 'completion_tokens': 4}}


class ToolProtocolFixture:
    def setUp(self):
        super().setUp()
        policy_path = Path(__file__).resolve().parents[3] / 'docs/data-security/phase3-policy.json'
        snapshot = PolicySnapshot.from_json(policy_path.read_bytes())
        self.binding = replace(examples()[PolicyBinding], protection_version=snapshot.version,
            protection_hash=snapshot.content_hash)
        self.audit = DurableAudit()
        self.protection = ProtectionService(
            policies=PolicyCatalog(repository=Mock(read=Mock(return_value=snapshot)), clock=lambda: AT),
            audit=self.audit, clock=lambda: AT, random_bytes=secrets.token_bytes,
            environment=Environment.EVALUATION, limits=BASELINE_LIMITS, field_ref='content/body')
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security',
            environment=Environment.EVALUATION, domain='ctf', scope_refs=('content/body',),
            outlet=Outlet.MODEL, purpose=Purpose.ANALYSIS)
        self.keys = Mock(resolve=Mock(return_value=SecretMaterial(b'synthetic-protocol-key', KeyPurpose.PROVIDER)))
        self.canary = Mock(check=Mock(return_value=()))
        self.registry = CanaryToolRegistry(plant=Mock(), checker=Mock(), resolve_context=Mock(), load_output=Mock())
        self.tools = self.registry.model_definitions()

    def adapter(self, name='deepseek', limits=BASELINE_LIMITS):
        return OfficialAI(endpoint_ref=name, base_url=ENDPOINTS[name], models=(MODELS[name],),
            key_ref=dto(KeyReference, key_ref=f'provider/{name}/v1', purpose=KeyPurpose.PROVIDER,
                version='v1', status=KeyStatus.ACTIVE), keys=self.keys, protection=self.protection,
            confidentiality=_confidentiality, limits=limits, service_identity='service/security',
            clock=lambda: AT, canary=self.canary)

    def request(self, name='deepseek', content=None):
        return dto(AIRequest, endpoint_ref=name, model_ref=MODELS[name], output_token_limit=64,
            temperature=0.7, content=dto(BoundedPayload, kind=PayloadKind.JSON, media_type=MediaType.JSON,
                text=None, tree=FrozenJSON(content if content is not None else {
                    'messages': [{'role': 'user', 'content': 'Check the authorized synthetic output.'}],
                    'tools': self.tools}), binary=None, limits=BASELINE_LIMITS))

    def handle(self, adapter):
        async def run_sync(function, *args):
            return function(*args)
        return ProviderHandle(name=adapter.endpoint_ref, model=MODELS[adapter.endpoint_ref], port=adapter,
            context_factory=lambda outlet: replace(self.context, outlet=outlet), binding=self.binding,
            limits=BASELINE_LIMITS, sanitize_response=lambda value: value, run_sync=run_sync)


class OfficialToolProtocolTests(ToolProtocolFixture, TestCase):
    def test_four_official_endpoints_protect_and_check_before_keys_and_send(self):
        for name in ('volcano', 'deepseek', 'moonshot', 'qwen'):
            with self.subTest(provider=name):
                self.keys.reset_mock()
                self.canary.reset_mock()
                adapter = self.adapter(name)
                def check(*, payload, context):
                    self.assertTrue(self.audit.events)
                    self.keys.resolve.assert_not_called()
                    encoded = json.dumps(payload.tree.to_value())
                    self.assertFalse('contact@example.invalid' in encoded)
                    self.assertFalse('192.0.2.1' in encoded)
                    self.assertFalse('synthetic-user-token' in encoded)
                    self.assertEqual(context, self.context)
                    return ()
                self.canary.check.side_effect = check
                body = tool_response(content='contact@example.invalid password=synthetic-reply-token')
                body['provider_metadata'] = {'note': '192.0.2.1 synthetic-protocol-key'}
                response = requests.Response()
                response.status_code = 200
                response._content = json.dumps(body).encode()
                response._content_consumed = True
                def send(session, prepared, **kwargs):
                    self.canary.check.assert_called_once()
                    self.keys.resolve.assert_called_once()
                    self.assertFalse(kwargs['allow_redirects'])
                    wire = json.loads(prepared.body)
                    self.assertEqual(wire['tools'], self.tools)
                    self.assertEqual(wire['tool_choice'], 'auto')
                    self.assertIs(wire['parallel_tool_calls'], False)
                    self.assertIs(wire['stream'], False)
                    self.assertEqual(prepared.headers['Authorization'], 'Bearer synthetic-protocol-key')
                    self.assertEqual(wire, self.canary.check.call_args.kwargs['payload'].tree.to_value())
                    return response
                content = {'messages': [{'role': 'user', 'content':
                    'contact@example.invalid 192.0.2.1 Authorization: Bearer synthetic-user-token'}],
                    'tools': self.tools}
                with patch.object(requests.Session, 'send', autospec=True, side_effect=send):
                    result = adapter.chat(self.request(name, content), self.context, self.binding)
                self.assertIs(type(result), AIResponse)
                self.assertIs(result.content.kind, PayloadKind.JSON)
                message = result.content.tree.to_value()
                self.assertEqual(message['tool_calls'][0]['function']['arguments'], {'artifact_ref': 'output/1'})
                self.assertFalse('contact@example.invalid' in message['content'])
                self.assertFalse('synthetic-reply-token' in message['content'])
                self.assertEqual((result.input_tokens, result.output_tokens), (3, 4))

    def test_wenxin_spark_and_stream_refuse_tools_before_keys_or_transport(self):
        with patch.object(requests.Session, 'send') as send, \
                patch('data_security.adapters.llm.official.connect') as connect:
            for name in ('wenxin', 'spark'):
                result = self.adapter(name).chat(self.request(name), self.context, self.binding)
                self.assertEqual(result.code, ReasonCode.UNSUPPORTED_SCOPE)
            result = list(self.adapter().stream(self.request(), self.context, self.binding))
            self.assertEqual(result[0].code, ReasonCode.UNSUPPORTED_SCOPE)
            self.keys.resolve.assert_not_called()
            self.canary.check.assert_not_called()
            send.assert_not_called()
            connect.assert_not_called()

    def test_closed_tool_definitions_and_history_refuse_before_authentication(self):
        bad_tools = [[], self.tools * 2, [{'type': 'function', 'function': dict(
            self.tools[0]['function'], name='canary.plant')}], [dict(self.tools[0], unknown=True)]]
        histories = [
            [{'role': 'tool', 'tool_call_id': 'missing', 'content': '{}'}],
            [{'role': 'user', 'content': 'safe', 'tool_calls': []}],
            [{'role': 'assistant', 'content': None, 'tool_calls': [dict(tool_call(), function={
                'name': 'canary_check', 'arguments': {'artifact_ref': 'output/1'}})]}],
        ]
        adapter = self.adapter()
        with patch.object(adapter, '_http') as send:
            for tools in bad_tools:
                result = adapter.chat(self.request(content={'messages': [{'role': 'user', 'content': 'safe'}],
                    'tools': tools}), self.context, self.binding)
                self.assertIs(type(result), ProtectionError)
            for messages in histories:
                result = adapter.chat(self.request(content={'messages': messages, 'tools': self.tools}),
                    self.context, self.binding)
                self.assertIs(type(result), ProtectionError)
            self.keys.resolve.assert_not_called()
            self.canary.check.assert_not_called()
            send.assert_not_called()

    def test_complete_reply_bound_before_redaction_and_discarding_metadata(self):
        adapter = self.adapter(limits=replace(BASELINE_LIMITS, max_text_chars=1024))
        self.protection.limits = adapter.limits
        bodies = [tool_response(), tool_response()]
        bodies[0]['discarded_metadata'] = 'x' * 1025
        bodies[1]['choices'][0]['message']['tool_calls'][0]['function']['arguments'] += ' ' * 1025
        for body in bodies:
            with patch.object(adapter, '_http', return_value=json.dumps(body).encode()):
                result = adapter.chat(self.request(), self.context, self.binding)
            self.assertEqual(result.code, ReasonCode.LIMIT_EXCEEDED)
        self.assertEqual(len(self.audit.events), 2)  # Only outbound protection succeeded.

    def test_complete_response_is_protected_including_decoded_arguments_and_metadata(self):
        adapter = self.adapter()
        body = tool_response(calls=[tool_call(arguments={'artifact_ref': 'mail@example.invalid'})])
        body['discarded_metadata'] = '192.0.2.1 synthetic-protocol-key password=synthetic-secret'
        protected_payloads = []
        original = adapter._protect
        def protect(payload, context, binding):
            result = original(payload, context, binding)
            if context.outlet is Outlet.API:
                protected_payloads.append(result.tree.to_value())
            return result
        with patch.object(adapter, '_http', return_value=json.dumps(body).encode()), \
                patch.object(adapter, '_protect', side_effect=protect):
            result = adapter.chat(self.request(), self.context, self.binding)
        self.assertIs(type(result), AIResponse)
        self.assertEqual(len(protected_payloads), 1)
        encoded = json.dumps(protected_payloads[0])
        for forbidden in ('mail@example.invalid', '192.0.2.1', 'synthetic-protocol-key', 'synthetic-secret'):
            self.assertFalse(forbidden in encoded)
        self.assertFalse('discarded_metadata' in result.content.tree.to_value())

    def test_malformed_or_unknown_calls_return_only_fixed_errors(self):
        valid = tool_call()
        invalid_calls = [
            [tool_call('canary.check')], [tool_call('unknown')],
            [dict(valid, id='bad.id')], [valid, valid],
            [dict(valid, type='unknown')], [dict(valid, extra=True)],
            [dict(valid, function={'name': 'canary_check', 'arguments': '{}'})],
            [dict(valid, function={'name': 'canary_check', 'arguments': '{broken'})],
            [tool_call(arguments={'artifact_ref': 'output/1', 'body': 'synthetic-body'})],
            [tool_call(arguments={'artifact_ref': 'output/1', 'user': 'admin'})],
            [tool_call(arguments={'artifact_ref': False})],
            [dict(valid, function={'name': 'canary_check', 'arguments':
                '{"artifact_ref":"output/1","artifact_ref":"output/2"}'})],
        ]
        adapter = self.adapter()
        for calls in invalid_calls:
            with self.subTest(case=invalid_calls.index(calls)), \
                    patch.object(adapter, '_http', return_value=json.dumps(tool_response(calls=calls)).encode()):
                result = adapter.chat(self.request(), self.context, self.binding)
                self.assertIs(type(result), ProtectionError)
                self.assertFalse(result.retryable)
                self.assertFalse('synthetic-body' in str(result.to_wire()))

    def test_incomplete_multi_choice_and_legacy_protocol_are_not_executable(self):
        bodies = [tool_response(finish='length'), tool_response(finish='stop')]
        multiple = tool_response()
        multiple['choices'] *= 2
        bodies.append(multiple)
        legacy = tool_response(calls=[], finish='stop')
        legacy['choices'][0]['message']['function_call'] = {'name': 'canary_check', 'arguments': '{}'}
        bodies.append(legacy)
        bodies.append(tool_response(calls=[], content=None, finish='stop'))
        invalid_usage = tool_response()
        invalid_usage['usage']['completion_tokens'] = False
        bodies.append(invalid_usage)
        for body in bodies:
            adapter = self.adapter()
            with patch.object(adapter, '_http', return_value=json.dumps(body).encode()):
                self.assertIs(type(adapter.chat(self.request(), self.context, self.binding)), ProtectionError)

    def test_text_only_tool_mode_final_accepts_omitted_null_or_empty_calls(self):
        for calls in ('absent', None, []):
            body = tool_response(calls=[], content='Finished safely.', finish='stop')
            if calls == 'absent':
                del body['choices'][0]['message']['tool_calls']
            else:
                body['choices'][0]['message']['tool_calls'] = calls
            adapter = self.adapter()
            with patch.object(adapter, '_http', return_value=json.dumps(body).encode()):
                result = adapter.chat(self.request(), self.context, self.binding)
            self.assertIs(type(result), AIResponse)
            self.assertEqual(result.content.tree.to_value(),
                {'role': 'assistant', 'content': 'Finished safely.', 'tool_calls': []})

    def test_canary_and_protection_failures_never_resolve_keys_or_send(self):
        failure = dto(ProtectionError, code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='tool/test')
        for outcome in (failure, None, (Mock(),), RuntimeError('synthetic body-bearing error')):
            self.keys.reset_mock()
            adapter = self.adapter()
            adapter.canary = Mock()
            if isinstance(outcome, Exception):
                adapter.canary.check.side_effect = outcome
            else:
                adapter.canary.check.return_value = outcome
            with patch.object(adapter, '_http') as send:
                result = adapter.chat(self.request(), self.context, self.binding)
            self.assertIs(type(result), ProtectionError)
            self.keys.resolve.assert_not_called()
            send.assert_not_called()
        self.audit.reject = True
        adapter = self.adapter()
        with patch.object(adapter, '_http') as send:
            self.assertEqual(adapter.chat(self.request(), self.context, self.binding).code, ReasonCode.AUDIT_UNAVAILABLE)
            self.keys.resolve.assert_not_called()
            send.assert_not_called()

    def test_http_byte_cap_applies_to_tool_mode_without_partial_result(self):
        response = requests.Response()
        response.status_code = 200
        response._content = b'x' * (MAX_RESPONSE_BYTES + 1)
        response._content_consumed = True
        with patch.object(requests.Session, 'send', return_value=response):
            result = self.adapter().chat(self.request(), self.context, self.binding)
        self.assertEqual(result.code, ReasonCode.LIMIT_EXCEEDED)

    def test_handle_preserves_json_dto_and_only_explicit_mode_sends_tools(self):
        adapter = self.adapter()
        handle = self.handle(adapter)
        body = tool_response()
        with patch.object(adapter, '_http', return_value=json.dumps(body).encode()) as send:
            result = asyncio.run(handle.chat_tools([{'role': 'user', 'content': 'safe'}], tools=self.tools))
        self.assertIs(type(result), AIResponse)
        self.assertIs(result.content.kind, PayloadKind.JSON)
        self.assertIn('tools', send.call_args.kwargs['body'])
        final = {'choices': [{'message': {'content': 'Ordinary chat.'}}]}
        with patch.object(adapter, '_http', return_value=json.dumps(final).encode()) as send:
            result = asyncio.run(handle.chat([Message(role='user', content='safe')]))
        self.assertEqual(result.content, 'Ordinary chat.')
        self.assertNotIn('tools', send.call_args.kwargs['body'])
        with self.assertRaisesRegex(RuntimeError, '^UNSUPPORTED_SCOPE$'):
            asyncio.run(self.handle(self.adapter('spark')).chat_tools(
                [{'role': 'user', 'content': 'safe'}], tools=self.tools))

    def test_round_trip_history_keeps_wire_json_strings_and_blocks_orphan_results(self):
        call = tool_call()
        call['function']['arguments'] = {'artifact_ref': 'output/1'}
        messages = [{'role': 'user', 'content': 'safe'}, {'role': 'assistant', 'content': None, 'tool_calls': [call]},
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': '{"status":"clean","alert_count":0}'}]
        adapter = self.adapter()
        final = tool_response(calls=[], content='Done.', finish='stop')
        with patch.object(adapter, '_http', return_value=json.dumps(final).encode()) as send:
            result = adapter.chat(self.request(content={'messages': messages, 'tools': self.tools}),
                self.context, self.binding)
        self.assertIs(type(result), AIResponse)
        args = send.call_args.kwargs['body']['messages'][1]['tool_calls'][0]['function']['arguments']
        self.assertIs(type(args), str)
        self.assertEqual(json.loads(args), {'artifact_ref': 'output/1'})
        bad = deepcopy(messages)
        bad[-1]['tool_call_id'] = 'unknown'
        self.keys.reset_mock()
        with patch.object(adapter, '_http') as send:
            result = adapter.chat(self.request(content={'messages': bad, 'tools': self.tools}),
                self.context, self.binding)
        self.assertIs(type(result), ProtectionError)
        self.keys.resolve.assert_not_called()
        send.assert_not_called()
