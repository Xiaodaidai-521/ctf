"""Synthetic PostgreSQL space isolation, not evidence of vendor semantic quality."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from ai_assistant.service import MultiAgentChatService
from data_security.adapters.django.rag import rag_protection_enabled
from legal_kb.models import LegalDocument, LegalKnowledgeEmbedding, LegalRetrievalLog
from legal_kb.services.embedding_service import EmbeddingService
from legal_kb.services.hashing import sha256_text
from legal_kb.services.ingestion_service import LegalKbIngestionService
from legal_kb.services.knowledge_retrieval_service import SafeKnowledgeRetrievalService
from legal_kb.services.platform_indexing_service import PlatformContentIndexingService
from legal_kb.services.retrieval_service import LegalRetrievalService
from learning_paths.models import KnowledgeConcept

from . import registry
from .adapters.embedder_legalkb import LegalKbEmbedder
from .adapters.repository_legalkb import LegalKbChunkRepository
from .interfaces import Chunk
from .models import DocumentSource
from .services import IngestionService

VISION_SPACE = 'volcano/doubao-embedding-vision-251215/1024/raw-v1'
OTHER_SPACE = 'qwen/text-embedding-v3/1024/raw-v1'
LOCAL_SPACE = 'local/local-hash-v1/128/raw-v1'


class EmbeddingFactoryTests(SimpleTestCase):
    def test_consumers_use_the_injected_factory_without_constructing_defaults(self):
        engine = object()
        factory = Mock(return_value=engine)
        with patch.object(registry, '_embedding_factory', factory):
            self.assertIs(LegalRetrievalService().embedding_service, engine)
            self.assertIs(LegalKbIngestionService().embedding_service, engine)
            self.assertIs(PlatformContentIndexingService().embedding_service, engine)
        self.assertEqual(factory.call_count, 3)

    def test_explicit_ports_work_without_a_default_factory(self):
        engine = object()
        with patch.object(registry, '_embedding_factory', None):
            self.assertIs(LegalRetrievalService(engine).embedding_service, engine)
            self.assertIs(LegalKbIngestionService(engine).embedding_service, engine)
            self.assertIs(PlatformContentIndexingService(engine).embedding_service, engine)
            with self.assertRaisesRegex(RuntimeError, '^RAG_NOT_CONFIGURED$'):
                registry.get_embedding_service()


@override_settings(EMBEDDING_PROVIDER='', EMBEDDING_MODEL='local-hash-v1', EMBEDDING_DIMENSION=128)
class VectorSpaceTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertFalse(rag_protection_enabled())
        self.admin = get_user_model().objects.create_user(username='p7-space-admin', role='admin', is_staff=True)
        self.content_type = ContentType.objects.get_for_model(DocumentSource)
        self.remote_query = [1.0] + [0.0] * 1023
        self.local_query = [0.0, 1.0] + [0.0] * 126
        self.engine = SimpleNamespace(
            model='doubao-embedding-vision-251215', vector_space=VISION_SPACE, retrieval_mode='semantic',
            embed_text=Mock(return_value=self.remote_query),
            embed_many=Mock(return_value=[self.remote_query]),
            embed_local_text=Mock(return_value=self.local_query))
        self.service = LegalRetrievalService(self.engine)

    def _row(self, name, space, *, vector_index=0, local_model='local-hash-v1', visibility='internal'):
        document = DocumentSource.objects.create(
            title=name, filename=name + '.txt', source_hash=sha256_text(name),
            status='completed', visibility=visibility)
        vector = [0.0] * 1024
        vector[vector_index] = 1.0
        metadata = {'visibility': visibility}
        if space is not None:
            metadata['vector_space'] = space
        return LegalKnowledgeEmbedding.objects.create(
            source_type='document', content_type=self.content_type, object_id=document.pk,
            chunk_index=0, title=name, text=name + ' evidence', text_hash=sha256_text(name + ' evidence'),
            embedding=self.local_query, embedding_vector=vector,
            embedding_model=local_model, embedding_dimension=128, metadata=metadata)

    def test_ann_excludes_other_and_unknown_spaces_without_modifying_them(self):
        foreign = self._row('foreign', OTHER_SPACE)
        unknown = self._row('unknown', None)
        matching = self._row('matching', VISION_SPACE)
        before = [(row.pk, row.text, row.metadata, row.embedding, list(row.embedding_vector), row.updated_at)
                  for row in LegalKnowledgeEmbedding.objects.order_by('id')]
        with CaptureQueriesContext(connection) as queries:
            results = self.service.retrieve(query='qzx', top_k=10, user=self.admin)
        self.assertEqual([item['id'] for item in results], [matching.pk])
        self.assertEqual(results[0]['retrieval'], 'semantic')
        self.assertEqual(results[0]['vector_space'], VISION_SPACE)
        vector_sql = [entry['sql'] for entry in queries if '<=>' in entry['sql']]
        self.assertTrue(vector_sql)
        self.assertTrue(all('vector_space' in sql for sql in vector_sql))
        after = [(row.pk, row.text, row.metadata, row.embedding, list(row.embedding_vector), row.updated_at)
                 for row in LegalKnowledgeEmbedding.objects.order_by('id')]
        self.assertEqual(after, before)
        self.assertEqual(LegalKnowledgeEmbedding.objects.filter(pk__in=(foreign.pk, unknown.pk)).count(), 2)
        self.assertEqual(LegalRetrievalLog.objects.get().results, results)

    def test_space_filter_does_not_bypass_document_visibility(self):
        internal = self._row('internal', VISION_SPACE, vector_index=1)
        staff = self._row('staff', VISION_SPACE, visibility='staff')
        teacher = get_user_model().objects.create_user(username='p7-space-teacher', role='teacher')
        admin_results = self.service.retrieve(query='qzx', top_k=10, user=self.admin)
        teacher_results = self.service.retrieve(query='qzx', top_k=10, user=teacher)
        self.assertEqual(admin_results[0]['id'], staff.pk)
        self.assertEqual([item['id'] for item in teacher_results], [internal.pk])

    def test_portable_result_uses_local_space_not_the_remote_query_space(self):
        row = self._row('portable', OTHER_SPACE)
        results = self.service.retrieve(query='qzx', top_k=10, user=self.admin)
        self.assertEqual([item['id'] for item in results], [row.pk])
        self.assertEqual(results[0]['retrieval'], 'deterministic')
        self.assertEqual(results[0]['vector_space'], LOCAL_SPACE)
        row.refresh_from_db()
        self.assertEqual(row.metadata['vector_space'], OTHER_SPACE)
        self.engine.embed_text.assert_called_once_with('qzx')
        self.engine.embed_local_text.assert_called_once_with('qzx')

    def test_unknown_portable_algorithm_is_not_compared_as_local_hash(self):
        self._row('unknown-local', None, local_model='unknown-algorithm')
        self.assertEqual(self.service.retrieve(query='qzx', top_k=10, user=self.admin), [])

    def test_unknown_space_can_return_lexical_evidence_without_a_semantic_label(self):
        row = self._row('rarephrase', None, local_model='unknown-algorithm')
        results = self.service.retrieve(query='rarephrase', top_k=10, user=self.admin)
        self.assertEqual([item['id'] for item in results], [row.pk])
        self.assertEqual(results[0]['retrieval'], 'lexical')
        self.assertEqual(results[0]['vector_space'], '')

    def test_legacy_explicit_port_still_uses_ann_but_is_labelled_unknown(self):
        farther = self._row('farther', None, vector_index=1)
        nearest = self._row('nearest', None)
        legacy = SimpleNamespace(
            model='fake-1024', embed_text=self.engine.embed_text,
            embed_local_text=self.engine.embed_local_text)
        with CaptureQueriesContext(connection) as queries:
            results = LegalRetrievalService(legacy).retrieve(query='q', top_k=10, user=self.admin)
        self.assertEqual(results[0]['id'], nearest.pk)
        self.assertIn(farther.pk, [item['id'] for item in results])
        self.assertTrue(any('<=>' in entry['sql'] for entry in queries))
        self.assertTrue(all(item['retrieval'] == 'unknown' for item in results))

    def test_repository_uses_port_space_not_caller_metadata(self):
        document = DocumentSource.objects.create(
            title='new', filename='new.txt', source_hash=sha256_text('new'), status='running')
        chunks = [Chunk(text='synthetic evidence', order=1,
                        metadata={'vector_space': OTHER_SPACE, 'retrieval_mode': 'forged'})]
        embedded = LegalKbEmbedder(self.engine).embed(chunks)
        LegalKbChunkRepository().replace(
            document_id=document.pk, source_type='document', embedded=embedded,
            base_metadata={'title': 'new', 'vector_space': OTHER_SPACE})
        row = LegalKnowledgeEmbedding.objects.get()
        self.assertEqual(row.metadata['vector_space'], VISION_SPACE)
        self.assertEqual(row.metadata['retrieval_mode'], 'semantic')
        self.assertEqual(row.metadata['vector_model'], self.engine.model)
        self.assertEqual(len(row.embedding_vector), 1024)
        self.assertEqual(len(row.embedding), 128)

    def test_all_text_writers_persist_local_space_and_facade_preserves_mode(self):
        text = 'rarephrase synthetic evidence'
        document = IngestionService().ingest_bytes(
            data=text.encode(), filename='local.txt', uploaded_by=self.admin)
        self.assertEqual(document.status, 'completed')
        law = LegalDocument.objects.create(
            title='Synthetic law', document_type='law', source_hash=sha256_text(text),
            full_text='第一条 ' + text, created_by=self.admin)
        LegalKbIngestionService().ingest_document(law, actor=self.admin)
        KnowledgeConcept.objects.create(
            name='Synthetic concept', slug='p7-space-concept', description=text,
            concept_type='tech', difficulty_level=1, importance=0.5)
        PlatformContentIndexingService().index_knowledge_concepts(actor=self.admin)
        rows = list(LegalKnowledgeEmbedding.objects.all())
        self.assertEqual({row.source_type for row in rows}, {'document', 'legal_clause', 'knowledge_concept'})
        self.assertTrue(all(row.metadata['vector_space'] == LOCAL_SPACE for row in rows))
        self.assertTrue(all(row.metadata['retrieval_mode'] == 'deterministic' for row in rows))
        items = SafeKnowledgeRetrievalService().retrieve(query=text, user=self.admin)
        self.assertTrue(items)
        self.assertNotIn('document', {item['source_type'] for item in items})
        self.assertTrue(all(item['retrieval'] == 'deterministic' for item in items))
        self.assertTrue(all(item['vector_space'] == LOCAL_SPACE for item in items))
        service = MultiAgentChatService()
        with patch.object(service, 'search_simple_knowledge', return_value={'items': []}), \
             patch.object(service, '_semantic_knowledge_items', return_value=items):
            package = service.build_knowledge_context(text)
        self.assertEqual(package['semantic_count'], len(items))  # Preserved legacy channel count.
        self.assertEqual(package['retrieval_counts']['semantic'], 0)
        self.assertEqual(package['retrieval_counts']['deterministic'], len(items))
        self.assertIn('本地确定性匹配（非语义模型）', package['context_text'])
        supplement = service._format_semantic_supplement(items, 'Synthetic pack context')
        self.assertIn('补充语义检索证据', supplement)  # Existing header remains compatible.
        self.assertIn('本地确定性匹配（非语义模型）', supplement)
