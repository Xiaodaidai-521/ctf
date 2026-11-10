"""New bound text exits; synthetic PostgreSQL data, no vendor API calls."""
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_assistant.service import MultiAgentChatService
from challenges.models import Category, Challenge
from data_security.adapters.django import rag
from data_security.contracts import Durability, ProtectionError
from audit.models import AuthenticatedAuditEntry
from legal_kb import serializers as legal_serializers
from legal_kb.models import (KbIngestionJob, LegalCase, LegalClause, LegalDocument,
                             LegalKnowledgeEmbedding, LegalRetrievalLog, LegalTemplate)
from legal_kb.services.chunking_service import ChunkingService
from legal_kb.services.hashing import sha256_text
from legal_kb.services.ingestion_service import LegalKbIngestionService
from legal_kb.services.platform_indexing_service import PlatformContentIndexingService
from legal_kb.services.rag_answer_service import RagAnswerService
from legal_kb.views import LegalDocumentViewSet
from learning_paths.models import KnowledgeConcept

from . import test_phase7_protection as protection_fixture
from .models import DocumentSource
from .serializers import DocumentSourceSerializer

MARKER = 'rag-private@example.invalid'
VISION_SPACE = 'volcano/doubao-embedding-vision-251215/1024/raw-v1'


@override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False,
                   EMBEDDING_PROVIDER='', EMBEDDING_MODEL='local-hash-v1', EMBEDDING_DIMENSION=128)
class TextExitTests(TestCase):
    def setUp(self):
        # Reuse the explicit synthetic binding, not its already-passed test methods.
        protection_fixture.RagProtectionTests.setUp(self)
        self.document = LegalDocument.objects.create(
            title='Title ' + MARKER, document_type='law', source_hash='p7-text-law',
            full_text='第一条 Evidence ' + MARKER + ' conclusion',
            metadata={'notes': MARKER}, created_by=self.admin)

    def test_legal_and_platform_text_are_protected_before_their_chunkers(self):
        engine = Mock(model='synthetic-local', vector_space='local/local-hash-v1/128/raw-v1',
                      retrieval_mode='deterministic')
        engine.embed_text.return_value = [1.0] + [0.0] * 127
        engine.embed_local_text.return_value = [1.0] + [0.0] * 127
        real_legal = ChunkingService.split_legal_text
        real_plain = ChunkingService.split_plain_text

        def legal(text):
            self.assertNotIn(MARKER, text)
            self.assertIn('Evidence', text)
            return real_legal(text)

        def plain(text):
            self.assertNotIn(MARKER, text)
            return real_plain(text)

        with patch.object(ChunkingService, 'split_legal_text', side_effect=legal), \
             patch.object(ChunkingService, 'split_plain_text', side_effect=plain):
            job = LegalKbIngestionService(engine).ingest_document(self.document, actor=self.admin)
            KnowledgeConcept.objects.create(
                name='Concept ' + MARKER, slug='p7-text-concept', description='Evidence ' + MARKER,
                concept_type='tech', difficulty_level=1, importance=0.5)
            outcome = PlatformContentIndexingService(engine).index_knowledge_concepts(actor=self.admin)
        self.assertEqual(job.status, 'completed')
        self.assertEqual(outcome.indexed_objects, 1)
        for row in LegalKnowledgeEmbedding.objects.all():
            self.assertNotIn(MARKER, row.title + row.text + json.dumps(row.metadata))
        self.assertNotIn(MARKER, str(engine.embed_text.call_args_list))
        self.document.refresh_from_db()
        self.assertIn(MARKER, self.document.full_text)  # No rewrite of the source owner.

    def test_bound_non_http_writers_require_the_existing_admin_permission(self):
        teacher = get_user_model().objects.create_user(username='p7-text-teacher', role='teacher')
        for actor in (None, teacher):
            with self.subTest(actor=actor):
                engine = Mock()
                with self.assertRaisesRegex(rag.RagProtectionError, '^RAG_AUTHORIZATION_REQUIRED$'):
                    LegalKbIngestionService(engine).ingest_document(self.document, actor=actor)
                with self.assertRaisesRegex(rag.RagProtectionError, '^RAG_AUTHORIZATION_REQUIRED$'):
                    PlatformContentIndexingService(engine).index_knowledge_concepts(actor=actor)
                engine.embed_text.assert_not_called()
        self.assertFalse(KbIngestionJob.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_pre_chunk_denial_keeps_existing_index_and_safe_job_error(self):
        row = LegalKnowledgeEmbedding.objects.create(
            source_type='legal_document', content_type=ContentType.objects.get_for_model(LegalDocument),
            object_id=self.document.pk, title='Old index', text='Old evidence', text_hash='old-text',
            embedding=[1.0], embedding_dimension=1, embedding_model='local-hash-v1')
        rag.bind_rag_protection(Mock(side_effect=RuntimeError(MARKER)))
        engine = Mock()
        with patch.object(ChunkingService, 'split_legal_text') as chunker:
            with self.assertRaises(rag.RagProtectionError):
                LegalKbIngestionService(engine).ingest_document(self.document, actor=self.admin)
        chunker.assert_not_called()
        engine.embed_text.assert_not_called()
        self.assertEqual(LegalKnowledgeEmbedding.objects.get().pk, row.pk)
        self.assertNotIn(MARKER, KbIngestionJob.objects.get().error_message)

    def test_all_browse_serializers_protect_without_rewriting_the_sources(self):
        clause = LegalClause.objects.create(document=self.document, clause_key='one',
            text='Evidence ' + MARKER + ' conclusion', text_hash='p7-clause', title=MARKER)
        case = LegalCase.objects.create(title=MARKER, summary=MARKER, facts=MARKER,
            decision=MARKER, source_hash='p7-case', metadata={'nested': [MARKER]})
        template = LegalTemplate.objects.create(title=MARKER, content='Evidence ' + MARKER,
            variables=[MARKER], metadata={'notes': MARKER})
        source = DocumentSource.objects.create(title=MARKER, filename=MARKER + '.txt',
            source_hash='p7-source', error_message=MARKER)
        embedding = LegalKnowledgeEmbedding.objects.create(
            source_type='legal_clause', content_type=ContentType.objects.get_for_model(LegalClause),
            object_id=clause.pk, title=MARKER, text='Evidence ' + MARKER, text_hash='p7-embedding',
            embedding=[1.0], embedding_model='local-hash-v1', embedding_dimension=1,
            metadata={'filename': MARKER})
        job = KbIngestionJob.objects.create(document=self.document, error_message=MARKER,
            source_payload={'notes': MARKER}, job_type='legal_document')
        log = LegalRetrievalLog.objects.create(query=MARKER, top_k=1, filters={'notes': MARKER},
            results=[{'text': MARKER}], latency_ms=0)
        pairs = (
            (legal_serializers.LegalDocumentSerializer, self.document),
            (legal_serializers.LegalClauseSerializer, clause),
            (legal_serializers.LegalCaseSerializer, case),
            (legal_serializers.LegalTemplateSerializer, template),
            (legal_serializers.LegalKnowledgeEmbeddingSerializer, embedding),
            (legal_serializers.KbIngestionJobSerializer, job),
            (legal_serializers.LegalRetrievalLogSerializer, log),
            (DocumentSourceSerializer, source),
        )
        for serializer, instance in pairs:
            with self.subTest(serializer=serializer.__name__):
                data = serializer(instance).data
                self.assertEqual(data['id'], instance.pk)
                self.assertNotIn(MARKER, json.dumps(data))
        data = legal_serializers.LegalDocumentSerializer(self.document).data
        self.assertIn('Evidence', data['full_text'])
        self.assertIn('conclusion', data['full_text'])
        self.document.refresh_from_db()
        source.refresh_from_db()
        self.assertIn(MARKER, self.document.full_text)
        self.assertIn(MARKER, source.filename)

    def test_browse_denial_is_a_closed_http_response(self):
        rag.bind_rag_protection(Mock(side_effect=RuntimeError(MARKER)))
        request = APIRequestFactory().get('/api/legal-kb/documents/')
        force_authenticate(request, user=self.admin)
        response = LegalDocumentViewSet.as_view({'get': 'retrieve'})(request, pk=self.document.pk)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(MARKER, json.dumps(response.data))
        self.assertNotIn('full_text', response.data)

    def test_legal_review_shares_one_protected_query_and_filters_the_space_and_object(self):
        category = Category.objects.create(name='Synthetic category')
        selected = Challenge.objects.create(title='Selected', category=category, description='qzx',
                                            difficulty='easy', score=100, flag='synthetic-selected')
        other = Challenge.objects.create(title='Other', category=category, description='qzx',
                                         difficulty='easy', score=100, flag='synthetic-other')
        for source_type, item, space in (
                ('legal_document', self.document, VISION_SPACE),
                ('challenge', selected, VISION_SPACE),
                ('challenge', other, VISION_SPACE),
                ('legal_document', self.document, 'qwen/text-embedding-v3/1024/raw-v1')):
            LegalKnowledgeEmbedding.objects.create(
                source_type=source_type, content_type=ContentType.objects.get_for_model(item),
                object_id=item.pk, chunk_index=1 if space != VISION_SPACE else 0,
                title='Title ' + MARKER, text='Evidence ' + MARKER,
                text_hash=sha256_text(source_type + str(item.pk) + space),
                embedding=[0.0] * 128, embedding_dimension=128, embedding_model='local-hash-v1',
                embedding_vector=[1.0] + [0.0] * 1023, metadata={'vector_space': space})
        engine = SimpleNamespace(model='doubao-embedding-vision-251215', vector_space=VISION_SPACE,
            retrieval_mode='semantic', embed_text=Mock(return_value=[1.0] + [0.0] * 1023),
            embed_local_text=Mock(return_value=[0.0] * 128))
        service = MultiAgentChatService()
        with patch.object(service, '_legal_embedding_service', return_value=engine):
            results = service.build_legal_review_context('qzx ' + MARKER, {'id': selected.pk}, top_k=5)
        self.assertEqual(len(results['legal_items']), 1)
        self.assertEqual([item['object_id'] for item in results['challenge_items']], [selected.pk])
        self.assertNotIn(MARKER, json.dumps(results))
        engine.embed_text.assert_called_once()
        self.assertNotIn(MARKER, str(engine.embed_text.call_args))
        self.assertEqual(LegalRetrievalLog.objects.count(), 2)
        self.assertTrue(all(item['retrieval'] == 'semantic' for item in results['legal_items']))

    def test_knowledge_cache_and_context_protect_old_and_new_values(self):
        service = MultiAgentChatService()
        value = {'items': [{'title': MARKER, 'summary': 'Evidence ' + MARKER}],
                 'context_text': 'Evidence ' + MARKER + ' conclusion'}
        service._set_cached_knowledge_result('new', value)
        self.assertNotIn(MARKER, json.dumps(service._knowledge_cache['new']['value']))
        service._knowledge_cache['old'] = dict(service._knowledge_cache['new'], value=value)
        self.assertNotIn(MARKER, json.dumps(service._get_cached_knowledge_result('old')))
        with patch.object(service, 'search_simple_knowledge', return_value=value), \
             patch.object(service, '_semantic_knowledge_items', return_value=[]):
            result = service.build_knowledge_context('query')
        self.assertNotIn(MARKER, json.dumps(result))
        self.assertIn('Evidence', result['context_text'])

    def test_synthesis_protects_before_provider_and_after_provider_response(self):
        captured = []
        provider = Mock(name='capture-provider')
        provider.name = 'capture-provider'
        provider.is_available.return_value = True

        async def chat(messages):
            captured.extend(message.content for message in messages)
            self.assertNotIn(MARKER, '\n'.join(captured))
            return SimpleNamespace(content='Answer ' + MARKER + ' conclusion',
                                   provider='capture-provider', model='synthetic-model')

        provider.chat = chat
        manager = Mock(_instances={'capture-provider': provider})
        manager.get_provider_for_agent.return_value = provider
        manager.get_provider.return_value = None
        retrieval = Mock()
        retrieval.retrieve.return_value = [{'id': 1, 'source_type': 'legal_clause', 'title': MARKER,
            'text': 'Evidence ' + MARKER, 'score': 1.0, 'metadata': {'notes': MARKER}}]
        with override_settings(LEGAL_KB_RAG_USE_LLM=True), \
             patch('legal_kb.services.rag_answer_service.get_manager', return_value=manager):
            result = RagAnswerService(retrieval).answer(query='Query ' + MARKER, include_raw=True)
        self.assertTrue(captured)
        self.assertNotIn(MARKER, json.dumps(result))
        self.assertIn('Answer', result['answer'])
        self.assertIn('conclusion', result['answer'])

    def test_authenticated_chain_receipt_is_obtained_before_text_release(self):
        receipts = []
        record = self.components['audit'].record

        def capture(event, durability):
            receipt = record(event, durability)
            receipts.append(receipt)
            return receipt

        with patch.object(self.components['audit'], 'record', side_effect=capture):
            value = rag.protect_rag('Evidence ' + MARKER, object_ref='rag/test', object_version='v1')
        self.assertNotIn(MARKER, value)
        self.assertTrue(receipts)
        self.assertTrue(all(receipt.durability is Durability.LEDGER_CONFIRMED and
                            receipt.chain_version == 'ds.audit.v2' for receipt in receipts))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), len(receipts))
        self.assertNotIsInstance(self.components['audit'].sink.verify('ds.audit.v2'), ProtectionError)

    def test_legacy_ledger_receipt_cannot_satisfy_the_authenticated_release(self):
        record = self.components['audit'].record

        def downgraded(event, durability):
            receipt = record(event, durability)
            return replace(receipt, chain_version='v1') if durability is Durability.LEDGER_CONFIRMED else receipt

        with patch.object(self.components['audit'], 'record', side_effect=downgraded):
            with self.assertRaisesRegex(rag.RagProtectionError, '^RAG_PROTECTION_FAILED$'):
                rag.protect_rag('Evidence ' + MARKER, object_ref='rag/test', object_version='v1')
