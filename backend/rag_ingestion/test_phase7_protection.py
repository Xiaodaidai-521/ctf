"""Isolated PostgreSQL RAG boundary tests using real M1/M4 and synthetic policy files."""
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from ctf_backend.security_bootstrap import assemble
from data_security.adapters.django import rag
from data_security.contracts import Outlet, PolicySnapshot, content_hash
from data_security.tests.phase3_fixtures import configuration
from legal_kb.models import LegalKnowledgeEmbedding, LegalRetrievalLog
from legal_kb.services.retrieval_service import LegalRetrievalService
from rag_ingestion.models import DocumentSource
from rag_ingestion.services import IngestionService

MARKER = 'rag-private@example.invalid'


@override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False)
class RagProtectionTests(TestCase):
    def setUp(self):
        previous = rag._protect
        self.addCleanup(rag.bind_rag_protection, previous)
        files = configuration(providers=())
        path, config, _, _, binding = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        policy_path = Path(config['policy_file'])
        policy = PolicySnapshot.from_json(policy_path.read_bytes())
        rules = policy.rules + tuple(replace(rule, outlet=Outlet.RAG)
                                     for rule in policy.rules if rule.outlet is Outlet.API)
        fields = dict(policy.content(), version='phase7-rag-synthetic.v1', rules=rules)
        digest = content_hash(fields)
        policy = PolicySnapshot(**fields, status=policy.status, content_hash=digest,
            approval=replace(policy.approval, approval_ref='approval/phase7-rag-synthetic', content_hash=digest))
        policy_path.write_text(json.dumps(policy.to_wire()))
        checkpoints = path.parent / 'checkpoints'
        checkpoints.mkdir(mode=0o700)
        config.update(schema_version='ds.bootstrap.v2', policy_repository={'kind': 'file', 'writable': False},
            policy_binding=replace(binding, protection_version=policy.version, protection_hash=digest).to_wire(),
            audit_chain={'chain_version': 'ds.audit.v2', 'project_ref': 'phase7/rag-synthetic',
                'object_uuid': '00000000-0000-4000-8000-000000000007', 'object_version': 'v1',
                'authorization_ref': 'authorization/phase7-rag-synthetic', 'retained_keys': [],
                'checkpoint_root': str(checkpoints), 'checkpoint_ref': None})
        path.write_text(json.dumps(config))
        self.components = assemble(config_path=path)
        rag.bind_rag_protection(self.components['protect_value'])
        self.admin = get_user_model().objects.create_user(
            username='phase7-rag-admin', password='synthetic-only-pass', role='admin', is_staff=True)

    def test_body_filename_title_and_nested_metadata_are_protected_before_persistence(self):
        document = IngestionService().ingest_bytes(
            data=('Evidence ' + MARKER + ' conclusion').encode(), filename=MARKER + '.txt',
            title='Title ' + MARKER, metadata={'notes': {'owner': MARKER}}, uploaded_by=self.admin)
        self.assertEqual(document.status, 'completed')
        chunks = list(LegalKnowledgeEmbedding.objects.filter(source_type='document', object_id=document.pk))
        self.assertEqual(len(chunks), document.embedded_count)
        self.assertTrue(chunks)
        for chunk in chunks:
            self.assertIn('Evidence', chunk.text)
            self.assertIn('conclusion', chunk.text)
            self.assertNotIn(MARKER, chunk.text + chunk.title + json.dumps(chunk.metadata))
        document.refresh_from_db()
        self.assertNotIn(MARKER, document.title + document.filename + json.dumps(document.metadata))

    def test_missing_rag_policy_scope_is_denied_before_persistence(self):
        with configuration(providers=()) as (path, _, _, _, _):
            components = assemble(config_path=path)
            rag.bind_rag_protection(components['protect_value'])
            with self.assertRaisesRegex(rag.RagProtectionError, '^RAG_PROTECTION_FAILED$'):
                IngestionService().ingest_bytes(data=b'Evidence', filename=MARKER + '.txt', uploaded_by=self.admin)
        self.assertFalse(DocumentSource.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_bound_ingestion_requires_an_authorized_uploader_even_outside_http(self):
        service = IngestionService()
        with self.assertRaisesRegex(rag.RagProtectionError, '^RAG_AUTHORIZATION_REQUIRED$'):
            service.ingest_bytes(data=b'Evidence', filename='evidence.txt')
        self.assertFalse(DocumentSource.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_header_protection_failure_creates_no_raw_source_or_index(self):
        rag.bind_rag_protection(Mock(side_effect=RuntimeError(MARKER)))
        with self.assertRaisesRegex(rag.RagProtectionError, '^RAG_PROTECTION_FAILED$'):
            IngestionService().ingest_bytes(data=b'Evidence', filename=MARKER + '.txt', uploaded_by=self.admin)
        self.assertFalse(DocumentSource.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_parser_exception_message_is_not_persisted_in_bound_mode(self):
        pipeline = Mock()
        pipeline.run.side_effect = RuntimeError(MARKER)
        document = IngestionService(pipeline=pipeline).ingest_bytes(
            data=b'Evidence', filename='failure.txt', uploaded_by=self.admin)
        self.assertEqual(document.status, 'failed')
        self.assertEqual(document.error_message, 'RuntimeError: RAG_OPERATION_FAILED')
        self.assertNotIn(MARKER, document.error_message)
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_query_is_protected_before_embedding_and_retrieved_legacy_text_before_log_or_response(self):
        document = DocumentSource.objects.create(title='Synthetic existing index', filename='fixture.txt',
            source_hash='phase7-query-fixture', status='completed', visibility='staff')
        LegalKnowledgeEmbedding.objects.create(source_type='document',
            content_type=ContentType.objects.get_for_model(DocumentSource), object_id=document.pk,
            text='Evidence ' + MARKER, title='Title ' + MARKER, text_hash='fixture',
            embedding=[1.0] + [0.0] * 127, embedding_model='local-hash-v1', embedding_dimension=128,
            metadata={'filename': MARKER + '.txt', 'nested': {'notes': MARKER}})
        embedding = Mock()
        embedding.embed_text.return_value = [1.0] + [0.0] * 127
        embedding.embed_local_text.return_value = [1.0] + [0.0] * 127
        results = LegalRetrievalService(embedding_service=embedding).retrieve(
            query='Evidence ' + MARKER, top_k=1, filters={'notes': MARKER}, user=self.admin)
        self.assertEqual(len(results), 1)
        self.assertNotIn(MARKER, json.dumps(results))
        self.assertNotIn(MARKER, str(embedding.embed_text.call_args))
        self.assertNotIn(MARKER, str(embedding.embed_local_text.call_args_list))
        log = LegalRetrievalLog.objects.get()
        self.assertNotIn(MARKER, log.query + json.dumps(log.results) + json.dumps(log.filters))
        self.assertEqual(log.results, results)
        # Reading the synthetic old index protects the exit, not the stored history.
        self.assertIn(MARKER, LegalKnowledgeEmbedding.objects.get().text)

    def test_query_protection_failure_has_no_embedding_or_query_log(self):
        embedding = Mock()
        rag.bind_rag_protection(Mock(side_effect=RuntimeError(MARKER)))
        with self.assertRaisesRegex(rag.RagProtectionError, '^RAG_PROTECTION_FAILED$'):
            LegalRetrievalService(embedding_service=embedding).retrieve(query=MARKER, user=self.admin)
        embedding.embed_text.assert_not_called()
        embedding.embed_local_text.assert_not_called()
        self.assertFalse(LegalRetrievalLog.objects.exists())
