import io
import json
from dataclasses import replace
from datetime import datetime, timezone
import secrets
import unittest
from unittest.mock import patch

import requests

from ctf_backend.security_bootstrap import _confidentiality
from data_security.adapters.keys import FileKeyResolver
from data_security.adapters.persistence.policies import FilePolicyRepository
from data_security.adapters.llm.official import OfficialAI, ENDPOINTS, MAX_RESPONSE_BYTES
from data_security.application.policy_catalog import PolicyCatalog
from data_security.application.protection import ProtectionService
from data_security.contracts import *
from data_security.tests.phase3_fixtures import configuration, ROOT, MODELS

AT = datetime(2026, 11, 5, 6, tzinfo=timezone.utc)
CAPTURE_SUMMARIES = []


class DurableAudit:
    def __init__(self):
        self.events = []
        self.reject = False

    def record(self, event, durability):
        if self.reject:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                   retryable=False, trace_id='audit/test')
        self.events.append(event)
        return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=event.event_id, durability=durability,
            stored_at=AT, chain_version=None, entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)


class OfficialTests(unittest.TestCase):
    def setUp(self):
        self.files = configuration()
        self.path, self.config, self.refs, self.secrets, self.binding = self.files.__enter__()
        self.addCleanup(self.files.__exit__, None, None, None)
        self.keys = FileKeyResolver(manifest_path=self.config['key_manifest'], environment=Environment.EVALUATION,
                                    repository_root=ROOT)
        self.catalog = PolicyCatalog(repository=FilePolicyRepository(path=self.config['policy_file']), clock=lambda: AT)
        self.audit = DurableAudit()
        self.protection = ProtectionService(policies=self.catalog, audit=self.audit, clock=lambda: AT,
            random_bytes=secrets.token_bytes, environment=Environment.EVALUATION, limits=BASELINE_LIMITS,
            field_ref='content/body')
        self.context = ProtectionContext(schema_version=ProtectionContext.SCHEMA, actor_ref='service/security',
            authorization_ref='authorization/phase3-isolated', scope_refs=('content/body',),
            environment=Environment.EVALUATION, domain='ctf', outlet=Outlet.MODEL, purpose=Purpose.ANALYSIS,
            role=Role.SERVICE, object_ref='request/content', object_version='v1',
            source_ref=None, source_version=None, source_hash=None, trace_id='trace/official-test')
        self.captures = []

    def adapter(self, name):
        return OfficialAI(endpoint_ref=name, base_url=ENDPOINTS[name], models=(MODELS[name], 'embedding-v1'),
            key_ref=self.refs[name], keys=self.keys, protection=self.protection, confidentiality=_confidentiality,
            limits=BASELINE_LIMITS, service_identity='service/security', clock=lambda: AT)

    def request(self, name, content=None, embedding=False):
        content = content or {'messages': [{'role': 'system', 'content': 'Summarize safely'},
            {'role': 'user', 'content': 'a@example.invalid 192.0.2.1 4111111111111111 Authorization: Bearer synthetic-value'}]}
        return AIRequest(schema_version=AIRequest.SCHEMA, endpoint_ref=name,
            model_ref='embedding-v1' if embedding else MODELS[name], output_token_limit=64, temperature=0.7,
            content=BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.JSON,
                media_type=MediaType.JSON, text=None, tree=FrozenJSON(content), binary=None, limits=BASELINE_LIMITS))

    def wire(self, session, prepared, **kwargs):
        self.assertGreater(len(self.audit.events), 0)
        self.assertFalse(kwargs.get('allow_redirects'))
        self.captures.append(prepared)
        response = requests.Response()
        response.status_code = 200
        if '/oauth/' in prepared.url:
            CAPTURE_SUMMARIES.append({'endpoint': 'https://aip.baidubce.com/oauth/2.0/token',
                'authentication_location': 'protocol-oauth-form', 'business_payload': None})
            value = {'access_token': 'synthetic-oauth-response-value'}
        else:
            body = json.loads(prepared.body)
            for forbidden in ('a@example.invalid', '192.0.2.1', '4111111111111111', 'synthetic-value'):
                self.assertNotIn(forbidden, str(body))
            for name, value in self.secrets.items():
                self.assertNotIn(value, prepared.body)
                if name in ENDPOINTS:
                    for part in value.decode('utf-8').split('|'):
                        self.assertNotIn(part, str(body))
            CAPTURE_SUMMARIES.append({'endpoint': prepared.url.split('?')[0],
                'authentication_location': 'protocol-query' if 'baidubce' in prepared.url else 'authorization-header',
                'business_payload': body})
            if '/embeddings' in prepared.url:
                value = {'data': [{'index': i, 'embedding': [0.1, 0.2]} for i in range(len(body['input']))]}
            elif body.get('stream'):
                if 'baidubce' in prepared.url:
                    value = 'data: ' + json.dumps({'result': 'password=synthetic-'}) + '\n\ndata: ' + json.dumps(
                        {'result': 'credential a@example.invalid', 'is_end': True}) + '\n'
                else:
                    value = '\n'.join('data: ' + json.dumps({'choices': [{'delta': {'content': part}}]})
                        for part in ('password=synthetic-', 'credential a@example.invalid')) + '\ndata: [DONE]\n'
                response._content = value.encode()
                response._content_consumed = True
                return response
            elif 'baidubce' in prepared.url:
                value = {'result': 'a@example.invalid', 'usage': {}}
            else:
                value = {'choices': [{'message': {'content': 'a@example.invalid'}}], 'usage': {}}
        response._content = json.dumps(value).encode()
        response._content_consumed = True
        return response

    def test_each_http_provider_chat_and_stream_same_contract(self):
        with patch.object(requests.Session, 'send', autospec=True, side_effect=self.wire):
            for name in ENDPOINTS.keys() - {'spark'}:
                with self.subTest(provider=name):
                    response = self.adapter(name).chat(self.request(name), self.context, self.binding)
                    self.assertIsInstance(response, AIResponse)
                    self.assertNotIn('@', response.content.text)
                    results = list(self.adapter(name).stream(self.request(name), self.context, self.binding))
                    self.assertTrue(all(type(item) is AIResponse for item in results))
                    content = ''.join(item.content.text for item in results)
                    self.assertNotIn('synthetic-credential', content)
                    self.assertNotIn('@', content)
        self.assertEqual(len(self.captures), 12)

    def test_both_embedding_endpoints_protect_final_body(self):
        with patch.object(requests.Session, 'send', autospec=True, side_effect=self.wire):
            for name in ('qwen', 'volcano'):
                request = self.request(name, {'input': ['a@example.invalid', '192.0.2.1']}, embedding=True)
                result = self.adapter(name).embed(request, replace(self.context, outlet=Outlet.EMBEDDING), self.binding)
                self.assertIsInstance(result, EmbeddingResult)
                self.assertEqual(len(result.vectors), 2)
        self.assertEqual(len(self.captures), 2)

    def test_spark_auth_added_after_protection_and_complete_buffer(self):
        test = self
        class Socket:
            def __enter__(self):
                self.parts = iter(('password=synthetic-', 'credential a@example.invalid'))
                return self
            def __exit__(self, *args):
                pass
            def send(self, value):
                body = json.loads(value)
                test.assertGreater(len(test.audit.events), 0)
                test.assertEqual(body.pop('header'), {'app_id': test.secrets['spark'].decode().split('|')[0]})
                test.assertNotIn('a@example.invalid', str(body))
                test.captures.append(body)
                CAPTURE_SUMMARIES.append({'endpoint': ENDPOINTS['spark'],
                    'authentication_location': 'protocol-query-and-header.app_id', 'business_payload': body})
            def recv(self, **kwargs):
                part = next(self.parts)
                return json.dumps({'header': {'code': 0}, 'payload': {'choices':
                    {'text': [{'content': part}], 'status': 2 if part.startswith('credential') else 1}}})
        with patch('data_security.adapters.llm.official.connect', return_value=Socket()) as connect:
            result = self.adapter('spark').chat(self.request('spark'), self.context, self.binding)
            self.assertIsInstance(result, AIResponse)
            self.assertNotIn('synthetic-credential', result.content.text)
            self.assertIn('authorization=', connect.call_args.args[0])
            self.assertIsNone(connect.call_args.kwargs['proxy'])
            chunks = list(self.adapter('spark').stream(self.request('spark'), self.context, self.binding))
            self.assertTrue(all(type(item) is AIResponse for item in chunks))
            self.assertNotIn('synthetic-credential', ''.join(item.content.text for item in chunks))
            self.assertEqual(connect.call_count, 2)

    def test_private_key_block_is_removed_before_send_and_after_stream_join(self):
        marker = secrets.token_hex(24)
        value = '-----BEGIN PRIVATE KEY-----\n' + marker + '\n-----END PRIVATE KEY-----'
        request = self.request('deepseek', {'messages': [{'role': 'user', 'content': value}]})
        def capture(session, prepared, **kwargs):
            self.assertFalse(marker in prepared.body.decode())
            response = self.wire(session, prepared, **kwargs)
            response._content = ('\n'.join('data: ' + json.dumps({'choices': [{'delta': {'content': part}}]})
                for part in (value[:37], value[37:])) + '\ndata: [DONE]\n').encode()
            return response
        with patch.object(requests.Session, 'send', autospec=True, side_effect=capture):
            chunks = list(self.adapter('deepseek').stream(request, self.context, self.binding))
        self.assertTrue(all(type(item) is AIResponse for item in chunks))
        self.assertFalse(marker in ''.join(item.content.text for item in chunks))

    def test_audit_failure_has_zero_sends(self):
        self.audit.reject = True
        with patch.object(requests.Session, 'send') as send:
            result = self.adapter('deepseek').chat(self.request('deepseek'), self.context, self.binding)
            self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
            send.assert_not_called()

    def test_revoked_key_and_wrong_purpose_have_zero_sends(self):
        from pathlib import Path
        manifest = Path(self.config['key_manifest'])
        document = json.loads(manifest.read_bytes())
        document['entries'] = [entry for entry in document['entries'] if entry['reference']['key_ref'] != self.refs['deepseek'].key_ref]
        manifest.write_text(json.dumps(document))
        with patch.object(requests.Session, 'send') as send:
            result = self.adapter('deepseek').chat(self.request('deepseek'), self.context, self.binding)
            self.assertEqual(result.code, ReasonCode.KEY_UNAVAILABLE)
            send.assert_not_called()
        self.assertIsInstance(self.keys.resolve(self.refs['data_key'], KeyPurpose.AUDIT, 'service/security'), ProtectionError)

    def test_missing_policy_and_changed_hash_have_zero_sends(self):
        bad = replace(self.binding, protection_hash='0' * 64)
        with patch.object(requests.Session, 'send') as send:
            result = self.adapter('deepseek').chat(self.request('deepseek'), self.context, bad)
            self.assertIsInstance(result, ProtectionError)
            send.assert_not_called()

    def test_nonofficial_endpoint_and_model_refused(self):
        with self.assertRaises(ContractViolation):
            OfficialAI(endpoint_ref='deepseek', base_url='https://example.invalid', models=('x',),
                key_ref=self.refs['deepseek'], keys=self.keys, protection=self.protection,
                confidentiality=_confidentiality, limits=BASELINE_LIMITS, service_identity='service/security', clock=lambda: AT)
        with patch.object(requests.Session, 'send') as send:
            result = self.adapter('deepseek').chat(replace(self.request('deepseek'), model_ref='not-approved'), self.context, self.binding)
            self.assertIsInstance(result, ProtectionError)
            send.assert_not_called()

    def test_redirect_is_not_followed(self):
        response = requests.Response()
        response.status_code = 302
        response.headers['Location'] = 'https://example.invalid'
        response._content = b''
        response._content_consumed = True
        with patch.object(requests.Session, 'send', return_value=response) as send:
            result = self.adapter('deepseek').chat(self.request('deepseek'), self.context, self.binding)
            self.assertEqual(result.code, ReasonCode.PROVIDER_UNAVAILABLE)
            self.assertEqual(send.call_count, 1)

    def test_over_limit_response_returns_no_partial_chunks(self):
        response = requests.Response()
        response.status_code = 200
        response._content = b'x' * (MAX_RESPONSE_BYTES + 1)
        response._content_consumed = True
        with patch.object(requests.Session, 'send', return_value=response):
            result = list(self.adapter('deepseek').stream(self.request('deepseek'), self.context, self.binding))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].code, ReasonCode.LIMIT_EXCEEDED)

    def test_exception_never_exposes_payload_or_credential(self):
        with patch.object(requests.Session, 'send', side_effect=ValueError(self.secrets['deepseek'].decode())):
            result = self.adapter('deepseek').chat(self.request('deepseek'), self.context, self.binding)
        self.assertIsInstance(result, ProtectionError)
        self.assertNotIn(self.secrets['deepseek'].decode(), str(result.to_wire()))

    def test_credentials_cannot_be_ordinary_payload(self):
        request = self.request('deepseek', {'messages': [{'role': 'user', 'content': self.secrets['deepseek'].decode()}]})
        with patch.object(requests.Session, 'send') as send:
            result = self.adapter('deepseek').chat(request, self.context, self.binding)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
            send.assert_not_called()

    def test_policy_lifecycle_stays_closed(self):
        snapshot = self.catalog.snapshot(self.binding)
        self.assertIsInstance(snapshot, PolicySnapshot)
        self.assertIsInstance(self.catalog.approve(snapshot, snapshot.approval, self.context), ProtectionError)
        self.assertIsInstance(self.catalog.retire(self.binding, self.context), ProtectionError)
        self.assertIsInstance(self.catalog.repository.put(snapshot, snapshot.version), ProtectionError)

    def test_manifest_permission_identity_environment_and_status(self):
        self.assertIsInstance(self.keys.resolve(self.refs['data_key'], KeyPurpose.DATA, 'service/wrong'), ProtectionError)
        from pathlib import Path
        keyfile = Path(self.config['key_manifest']).parent / 'data_key.key'
        keyfile.chmod(0o644)
        self.assertIsInstance(self.keys.resolve(self.refs['data_key'], KeyPurpose.DATA, 'service/security'), ProtectionError)
        keyfile.chmod(0o600)
        self.assertIsInstance(self.keys.resolve(replace(self.refs['data_key'], status=KeyStatus.RETIRED),
                             KeyPurpose.DATA, 'service/security'), ProtectionError)
        with self.assertRaises(ContractViolation):
            FileKeyResolver(manifest_path=self.config['key_manifest'], environment=Environment.PRODUCTION, repository_root=ROOT)
