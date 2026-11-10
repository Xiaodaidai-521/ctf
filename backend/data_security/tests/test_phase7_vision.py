"""Official multimodal wire captures only; no live Ark requests or semantic-quality claim."""
from dataclasses import replace
from datetime import datetime, timezone
import json
import secrets
import unittest
from unittest.mock import patch

import requests

from ctf_backend.security_bootstrap import _confidentiality
from data_security.adapters.keys import FileKeyResolver
from data_security.adapters.llm.official import ENDPOINTS, OfficialAI
from data_security.adapters.persistence.policies import FilePolicyRepository
from data_security.application.policy_catalog import PolicyCatalog
from data_security.application.protection import ProtectionService
from data_security.contracts import (AIRequest, BASELINE_LIMITS, BoundedPayload, EmbeddingResult,
    Environment, FrozenJSON, MediaType, Outlet, PayloadKind, ProtectionContext, ProtectionError,
    Purpose, Role)
from data_security.tests.phase3_fixtures import configuration, ROOT
from data_security.tests.test_phase3_official import DurableAudit

MODEL = 'doubao-embedding-vision-251215'
AT = datetime(2026, 11, 5, 6, tzinfo=timezone.utc)


class VisionEmbeddingTests(unittest.TestCase):
    def setUp(self):
        files = configuration(providers=('volcano', 'qwen'))
        _, config, refs, _, self.binding = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        self.audit = DurableAudit()
        self.keys = FileKeyResolver(manifest_path=config['key_manifest'],
                                    environment=Environment.EVALUATION, repository_root=ROOT)
        catalog = PolicyCatalog(repository=FilePolicyRepository(path=config['policy_file']), clock=lambda: AT)
        self.protection = ProtectionService(policies=catalog, audit=self.audit, clock=lambda: AT,
            random_bytes=secrets.token_bytes, environment=Environment.EVALUATION,
            limits=BASELINE_LIMITS, field_ref='content/body')
        self.context = ProtectionContext(schema_version=ProtectionContext.SCHEMA,
            actor_ref='service/security', authorization_ref='authorization/phase7-capture',
            scope_refs=('content/body',), environment=Environment.EVALUATION, domain='ctf',
            outlet=Outlet.EMBEDDING, purpose=Purpose.ANALYSIS, role=Role.SERVICE,
            object_ref='rag/document-7', object_version='v1', source_ref=None, source_version=None,
            source_hash=None, trace_id='trace/phase7-vision')
        self.adapter = OfficialAI(endpoint_ref='volcano', base_url=ENDPOINTS['volcano'],
            models=(MODEL,), key_ref=refs['volcano'], keys=self.keys, protection=self.protection,
            confidentiality=_confidentiality, limits=BASELINE_LIMITS, service_identity='service/security',
            clock=lambda: AT)
        self.response = {'data': {'object': 'embedding', 'embedding': [0.25] * 1024}}
        self.sent = []

    def request(self, content=None):
        return AIRequest(schema_version=AIRequest.SCHEMA, endpoint_ref='volcano', model_ref=MODEL,
            output_token_limit=64, temperature=0.0,
            content=BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.JSON,
                media_type=MediaType.JSON, text=None, binary=None,
                tree=FrozenJSON(content if content is not None else {
                    'input': [{'type': 'text', 'text': 'Query rag-private@example.invalid 192.0.2.7'}],
                    'dimensions': 1024}), limits=BASELINE_LIMITS))

    def send(self, session, prepared, **kwargs):
        self.assertTrue(self.audit.events)
        self.assertFalse(session.trust_env)
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(prepared.url, ENDPOINTS['volcano'] + '/embeddings/multimodal')
        body = json.loads(prepared.body)
        self.assertEqual(body['model'], MODEL)
        self.assertEqual(body['dimensions'], 1024)
        self.assertEqual(body['encoding_format'], 'float')
        self.assertEqual(body['input'][0]['type'], 'text')
        self.assertNotIn('rag-private@example.invalid', str(body))
        self.assertNotIn('192.0.2.7', str(body))
        self.sent.append(body)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(self.response).encode()
        response._content_consumed = True
        return response

    def test_native_1024_text_request_uses_multimodal_endpoint_and_object_response(self):
        with patch.object(requests.Session, 'send', autospec=True, side_effect=self.send):
            result = self.adapter.embed(self.request(), self.context, self.binding)
        self.assertIsInstance(result, EmbeddingResult)
        self.assertEqual(len(result.vectors), 1)
        self.assertEqual(len(result.vectors[0]), 1024)
        self.assertEqual(len(self.sent), 1)

    def test_no_default_dimension_or_2048_projection_is_accepted(self):
        for fields in ({}, {'dimensions': 2048}, {'dimensions': True}):
            with self.subTest(fields=fields), patch.object(requests.Session, 'send') as send:
                request = self.request({'input': [{'type': 'text', 'text': 'Query'}], **fields})
                result = self.adapter.embed(request, self.context, self.binding)
                self.assertIsInstance(result, ProtectionError)
                send.assert_not_called()

    def test_2048_response_is_rejected_not_truncated(self):
        self.response['data']['embedding'] = [0.25] * 2048
        with patch.object(requests.Session, 'send', autospec=True, side_effect=self.send):
            result = self.adapter.embed(self.request(), self.context, self.binding)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(len(self.sent), 1)

    def test_legacy_data_array_is_not_misread_as_multimodal_result(self):
        self.response = {'data': [{'index': 0, 'embedding': [0.25] * 1024}]}
        with patch.object(requests.Session, 'send', autospec=True, side_effect=self.send):
            result = self.adapter.embed(self.request(), self.context, self.binding)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(len(self.sent), 1)

    def test_no_authentication_or_send_after_protection_failure(self):
        self.audit.reject = True
        with patch.object(self.keys, 'resolve', wraps=self.keys.resolve) as keys, \
             patch.object(requests.Session, 'send') as send:
            result = self.adapter.embed(self.request(), self.context, self.binding)
        self.assertIsInstance(result, ProtectionError)
        keys.assert_not_called()
        send.assert_not_called()

    def test_arbitrary_image_url_has_no_document_authorization_and_cannot_send(self):
        content = {'input': [{'type': 'image_url', 'image_url': {'url': 'https://example.invalid/private.png'}}],
                   'dimensions': 1024}
        with patch.object(requests.Session, 'send') as send:
            result = self.adapter.embed(self.request(content), self.context, self.binding)
        self.assertIsInstance(result, ProtectionError)
        send.assert_not_called()

    def test_video_and_multiple_independent_text_inputs_are_not_scope_expansions(self):
        for parts in ([{'type': 'video_url', 'video_url': {'url': 'https://example.invalid/video'}}],
                      [{'type': 'text', 'text': 'first'}, {'type': 'text', 'text': 'second'}]):
            with self.subTest(parts=parts), patch.object(requests.Session, 'send') as send:
                result = self.adapter.embed(self.request({'input': parts, 'dimensions': 1024}),
                                            self.context, self.binding)
                self.assertIsInstance(result, ProtectionError)
                send.assert_not_called()

    def test_wrong_model_and_endpoint_never_call_provider(self):
        for request in (replace(self.request(), model_ref='doubao-embedding-vision-unknown'),
                        replace(self.request(), endpoint_ref='qwen')):
            with patch.object(requests.Session, 'send') as send:
                self.assertIsInstance(self.adapter.embed(request, self.context, self.binding), ProtectionError)
                send.assert_not_called()
