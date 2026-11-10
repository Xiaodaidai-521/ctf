"""Remaining text exits and short index replacement transactions, synthetic PG only."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from asgiref.sync import async_to_sync
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TransactionTestCase, override_settings

from ai_assistant.models import ChallengeKnowledgePack
from ai_assistant.service import MultiAgentChatService, solve_challenge_hybrid_async
from challenges.models import Category, Challenge
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.django import rag
from data_security.tests.phase3_fixtures import configuration
from legal_kb.models import KbIngestionJob, LegalDocument, LegalKnowledgeEmbedding
from legal_kb.services.hashing import sha256_text
from legal_kb.services.ingestion_service import LegalKbIngestionService
from legal_kb.services.platform_indexing_service import PlatformContentIndexingService
from learning_paths.models import KnowledgeConcept

from . import test_phase7_protection as protection_fixture

MARKER = 'rag-private@example.invalid'
VISION_SPACE = 'volcano/doubao-embedding-vision-251215/1024/raw-v1'


@override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False,
                   EMBEDDING_PROVIDER='', EMBEDDING_MODEL='local-hash-v1', EMBEDDING_DIMENSION=128)
class TextClosureTests(TransactionTestCase):
    def setUp(self):
        protection_fixture.RagProtectionTests.setUp(self)
        rag.bind_rag_protection(self.components['protect_rag_value'])
        self.document = LegalDocument.objects.create(
            title='Synthetic law', document_type='law', source_hash='p7-text-closure-law',
            full_text='第一条 Evidence ' + MARKER + ' conclusion', created_by=self.admin)

    def engine(self):
        return SimpleNamespace(model='local-hash-v1',
            vector_space='local/local-hash-v1/128/raw-v1', retrieval_mode='deterministic',
            embed_text=Mock(return_value=[1.0] + [0.0] * 127),
            embed_local_text=Mock(return_value=[1.0] + [0.0] * 127))

    def test_legal_reviewer_protects_all_outgoing_context_and_normal_response(self):
        service = MultiAgentChatService()
        evidence = {'legal_items': [{'id': 1, 'title': MARKER, 'text': 'Evidence ' + MARKER,
                    'source_type': 'legal_document', 'score': 1.0, 'retrieval': 'deterministic'}],
                    'challenge_items': []}

        async def chat(agent_id, question, context):
            self.assertEqual(agent_id, 'legal_reviewer')
            self.assertNotIn(MARKER, question + json.dumps(context))
            self.assertIn('Evidence', context['agent_task_instruction'])
            self.assertNotIn('flag', context['challenge_info'])
            return {'content': 'Answer ' + MARKER + ' conclusion',
                    'provider': 'capture', 'model': 'synthetic-model'}

        with patch.object(service, 'build_legal_review_context', return_value=evidence), \
             patch.object(service, 'chat_with_agent', side_effect=chat) as provider:
            result = async_to_sync(service.run_legal_reviewer)(
                question='Question ' + MARKER,
                challenge_info={'id': 1, 'title': MARKER, 'description': 'Evidence ' + MARKER,
                                'hint': MARKER, 'flag': 'synthetic-not-for-model'},
                context={'context_summary': MARKER, 'extra': {'notes': MARKER}})
        provider.assert_called_once()
        self.assertNotIn(MARKER, json.dumps(result))
        self.assertIn('Answer', result['content'])
        self.assertIn('conclusion', result['content'])
        self.assertEqual(result['legal_evidence_count'], 1)

    def test_legal_reviewer_input_denial_does_not_call_or_fallback(self):
        service = MultiAgentChatService()
        rag.bind_rag_protection(Mock(side_effect=RuntimeError(MARKER)))
        with patch.object(service, 'build_legal_review_context', return_value={}), \
             patch.object(service, 'chat_with_agent', new_callable=AsyncMock) as provider, \
             patch.object(service, '_build_legal_review_fallback') as fallback:
            with self.assertRaises(rag.RagProtectionError):
                async_to_sync(service.run_legal_reviewer)(
                    question=MARKER, challenge_info=None, context={})
        provider.assert_not_called()
        fallback.assert_not_called()

    def test_legal_reviewer_output_denial_cannot_become_a_template_success(self):
        service = MultiAgentChatService()
        protect = rag._protect

        def deny_answer(value, **context):
            if isinstance(value, str) and value.startswith('Answer '):
                raise RuntimeError(MARKER)
            return protect(value, **context)

        rag.bind_rag_protection(deny_answer)
        with patch.object(service, 'build_legal_review_context', return_value={}), \
             patch.object(service, 'chat_with_agent', new_callable=AsyncMock,
                          return_value={'content': 'Answer ' + MARKER, 'provider': 'capture'}), \
             patch.object(service, '_build_legal_review_fallback') as fallback:
            with self.assertRaises(rag.RagProtectionError):
                async_to_sync(service.run_legal_reviewer)(
                    question='Synthetic question', challenge_info=None, context={})
        fallback.assert_not_called()

    def test_rag_excerpt_protection_precedes_truncation_without_content_binding(self):
        value = MultiAgentChatService()._safe_excerpt('A ' + MARKER + ' conclusion', 15)
        self.assertNotIn('rag-priv', value)
        self.assertTrue(value.startswith('A '))

    def test_bound_legacy_rank_requires_the_shared_query_context(self):
        queryset = Mock()
        with self.assertRaisesRegex(rag.RagProtectionError, '^RAG_QUERY_CONTEXT_REQUIRED$'):
            MultiAgentChatService()._rank_legal_embeddings(
                query_embedding=[1.0] + [0.0] * 1023, queryset=queryset, top_k=5)
        self.assertFalse(queryset.mock_calls)

    def test_formal_rag_binding_without_authenticated_chain_rejects_every_outlet(self):
        with configuration(providers=()) as (path, _, _, _, _):
            components = assemble(config_path=path)
            rag.bind_rag_protection(components['protect_rag_value'])
            with patch.object(components['audit'], 'record') as record:
                for outlet in ('rag', 'api', 'model', 'embedding'):
                    with self.subTest(outlet=outlet), self.assertRaises(rag.RagProtectionError):
                        rag.protect_rag('Synthetic evidence', object_ref='rag/test',
                                        object_version='v1', outlet=outlet)
            record.assert_not_called()

    def test_answer_cache_protects_new_writes_and_old_reads(self):
        service = MultiAgentChatService()
        value = {'answer': 'Answer ' + MARKER + ' conclusion',
                 'responses': [{'content': 'Evidence ' + MARKER, 'provider': 'capture'}],
                 'sources': [{'title': MARKER}]}
        service._set_cached_response_result('new', value)
        self.assertNotIn(MARKER, json.dumps(service._response_cache['new']['value']))
        service._response_cache['old'] = dict(service._response_cache['new'], value=value)
        result = service._get_cached_response_result('old')
        self.assertNotIn(MARKER, json.dumps(result))
        self.assertIn('Answer', result['answer'])
        self.assertIn('conclusion', result['answer'])
        self.assertIn(MARKER, value['answer'])

    def test_hybrid_final_response_is_protected_even_for_an_injected_answer_port(self):
        service = MultiAgentChatService()
        with patch('ai_assistant.service.get_multi_agent_service', return_value=service), \
             patch.object(service, 'build_knowledge_context', return_value={'items': [], 'context_text': ''}), \
             patch.object(service, 'run_legal_reviewer', new_callable=AsyncMock,
                          return_value={'content': 'Answer ' + MARKER + ' conclusion',
                                        'provider': 'capture', 'agent_id': 'legal_reviewer'}):
            result = async_to_sync(solve_challenge_hybrid_async)(
                question='Synthetic question', agent_ids=['legal_reviewer'], force_ai=True)
        self.assertNotIn(MARKER, json.dumps(result))
        self.assertIn('Answer', result['responses'][0]['content'])

    def test_legal_embedding_is_outside_the_replacement_transaction(self):
        old = LegalKnowledgeEmbedding.objects.create(
            source_type='legal_document', content_type=ContentType.objects.get_for_model(LegalDocument),
            object_id=self.document.pk, title='Old index', text='Old evidence', text_hash='p7-closure-old',
            embedding=[1.0], embedding_dimension=1, embedding_model='local-hash-v1')
        engine = self.engine()

        def embed(text):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(LegalKnowledgeEmbedding.objects.filter(pk=old.pk).exists())
            self.assertNotIn(MARKER, text)
            return [1.0] + [0.0] * 127

        engine.embed_text.side_effect = embed
        result = LegalKbIngestionService(engine).ingest_document(self.document, actor=self.admin)
        self.assertEqual(result.status, 'completed')
        self.assertFalse(LegalKnowledgeEmbedding.objects.filter(pk=old.pk).exists())
        self.assertGreater(result.embedded_chunks, 0)

    def test_platform_prepares_the_whole_batch_before_atomic_replacement(self):
        concepts = [KnowledgeConcept.objects.create(name='Concept ' + str(i), slug='p7-closure-' + str(i),
                    description='Evidence ' + MARKER, concept_type='tech',
                    difficulty_level=1, importance=0.5) for i in range(2)]
        old_ids = [LegalKnowledgeEmbedding.objects.create(
            source_type='knowledge_concept', content_type=ContentType.objects.get_for_model(KnowledgeConcept),
            object_id=item.pk, title='Old index', text='Old evidence', text_hash='p7-old-' + str(item.pk),
            embedding=[1.0], embedding_dimension=1, embedding_model='local-hash-v1').pk for item in concepts]
        engine = self.engine()
        calls = []

        def fail_second(text):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(LegalKnowledgeEmbedding.objects.filter(pk__in=old_ids).count(), 2)
            self.assertNotIn(MARKER, text)
            calls.append(text)
            if len(calls) == 2:
                raise RuntimeError(MARKER)
            return [1.0] + [0.0] * 127

        engine.embed_text.side_effect = fail_second
        with self.assertRaises(RuntimeError):
            PlatformContentIndexingService(engine).index_knowledge_concepts(actor=self.admin)
        self.assertEqual(len(calls), 2)
        self.assertEqual(list(LegalKnowledgeEmbedding.objects.order_by('pk').values_list('pk', flat=True)), old_ids)

    def test_legal_reviewer_challenge_filter_uses_the_owner_not_pack_primary_key(self):
        category = Category.objects.create(name='Synthetic closure')
        selected = Challenge.objects.create(title='Selected', category=category, description='qzx',
                    difficulty='easy', score=100, flag='synthetic-selected')
        other = Challenge.objects.create(title='Other', category=category, description='qzx',
                    difficulty='easy', score=100, flag='synthetic-other')
        selected_pack = ChallengeKnowledgePack.objects.create(pk=101, challenge=selected,
                    summary='Evidence', context_text='qzx')
        other_pack = ChallengeKnowledgePack.objects.create(pk=selected.pk, challenge=other,
                    summary='Evidence', context_text='qzx')
        for pack in (selected_pack, other_pack):
            LegalKnowledgeEmbedding.objects.create(
                source_type='challenge', content_type=ContentType.objects.get_for_model(ChallengeKnowledgePack),
                object_id=pack.pk, title='Synthetic pack', text='qzx', text_hash=sha256_text(str(pack.pk)),
                embedding=[0.0] * 128, embedding_dimension=128, embedding_model='local-hash-v1',
                embedding_vector=[1.0] + [0.0] * 1023,
                metadata={'kind': 'knowledge_pack', 'challenge_id': pack.challenge_id, 'vector_space': VISION_SPACE})
        engine = self.engine()
        engine.vector_space, engine.retrieval_mode = VISION_SPACE, 'semantic'
        engine.embed_text.return_value = [1.0] + [0.0] * 1023
        with patch.object(MultiAgentChatService, '_legal_embedding_service', return_value=engine):
            result = MultiAgentChatService().build_legal_review_context('qzx', {'id': selected.pk})
        self.assertEqual([row['object_id'] for row in result['challenge_items']], [selected_pack.pk])
