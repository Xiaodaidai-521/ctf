"""Offline regression coverage for chunking and versioned embedding lifecycle."""

import io
import math
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from learning_knowledge.models import Material
from learning_map.models import CatalogVersion
from rag_ingestion.models import DocumentSource

from .models import KbIngestionJob, LegalDocument, LegalKnowledgeEmbedding, LegalRetrievalLog
from .services.chunking_service import ChunkingService
from .services.embedding_service import EmbeddingService, EmbeddingUnavailableError, cosine_similarity
from .services.ingestion_service import LegalKbIngestionService
from .services.platform_indexing_service import PlatformContentIndexingService
from .services.retrieval_service import LegalRetrievalService


class BoundaryChunkingTests(SimpleTestCase):
    def test_boundaries_and_overlap_preserve_context(self):
        text = '甲' * 21 + '。' + '乙' * 20 + '。' + '丙' * 21 + '。' + '丁' * 20 + '。'
        chunks = ChunkingService.split_plain_text(text, max_chars=50, overlap=8)
        self.assertEqual(chunks[0].text, text[:43])
        rebuilt = chunks[0].text
        for left, right in zip(chunks, chunks[1:]):
            self.assertEqual(left.text[-8:], right.text[:8])
            rebuilt += right.text[8:]
        self.assertEqual(rebuilt, text)
        self.assertTrue(all(len(chunk.text) <= 50 for chunk in chunks))
        self.assertEqual(chunks, ChunkingService.split_plain_text(text, max_chars=50, overlap=8))

    def test_no_boundary_and_extreme_overlap_terminate(self):
        for maximum, overlap in [(1, 0), (17, 0), (17, 16)]:
            text = ''.join(chr(0x4e00 + index) for index in range(70))
            chunks = ChunkingService.split_plain_text(text, max_chars=maximum, overlap=overlap)
            rebuilt = chunks[0].text + ''.join(chunk.text[overlap:] for chunk in chunks[1:])
            self.assertEqual(rebuilt, text)
            self.assertTrue(all(0 < len(chunk.text) <= maximum for chunk in chunks))

    def test_empty_and_invalid_window(self):
        self.assertEqual(ChunkingService.split_plain_text(' \n'), [])
        for maximum, overlap in [(0, 0), (10, -1), (10, 10)]:
            with self.assertRaises(ValueError):
                ChunkingService.split_plain_text('body', max_chars=maximum, overlap=overlap)

    def test_legal_article_citations_are_preserved(self):
        text = '第一章\n第一条 甲。\n第二条 乙。'
        chunks = ChunkingService.split_legal_text(text, max_chars=8, overlap=2)
        self.assertEqual([chunk.clause_key for chunk in chunks], ['第一条', '第二条'])
        self.assertEqual(chunks[0].chapter, '第一章')
        ordinary = '句子。' * 30
        self.assertEqual(
            ChunkingService.split_legal_text(ordinary, max_chars=20, overlap=4),
            ChunkingService.split_plain_text(ordinary, max_chars=20, overlap=4),
        )


class EmbeddingConfigurationTests(SimpleTestCase):
    @override_settings(EMBEDDING_PROVIDER='', EMBEDDING_API_KEY='')
    def test_missing_provider_is_lazy_but_embedding_fails_loudly(self):
        service = EmbeddingService()
        self.assertEqual(service.embed_many([]), [])
        with self.assertLogs('legal_kb.services.embedding_service', level='ERROR') as logs:
            with self.assertRaises(EmbeddingUnavailableError):
                service.embed_text('private-material-sentinel')
        self.assertNotIn('private-material-sentinel', '\n'.join(logs.output))

    @override_settings(EMBEDDING_PROVIDER='local')
    def test_local_provider_is_explicit_nonsemantic_opt_in(self):
        service = EmbeddingService()
        with self.assertLogs('legal_kb.services.embedding_service', level='WARNING'):
            vector = service.embed_text('offline fixture')
        self.assertEqual(len(vector), 128)
        self.assertEqual(service.model, 'local-hash-v1')
        self.assertAlmostEqual(cosine_similarity(vector, vector), 1.0)

    @override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='secret', EMBEDDING_DIMENSION=3)
    def test_remote_error_never_hashes_and_redacts_sdk_exception(self):
        service = EmbeddingService()
        with patch.object(service, '_remote_embed_many', side_effect=RuntimeError('SECRET-BODY api_key=secret')):
            with patch.object(service, '_local_embed_text') as local:
                with self.assertLogs('legal_kb.services.embedding_service', level='ERROR') as logs:
                    with self.assertRaises(EmbeddingUnavailableError) as error:
                        service.embed_text('SECRET-BODY')
        local.assert_not_called()
        self.assertNotIn('SECRET-BODY', str(error.exception) + '\n'.join(logs.output))
        self.assertNotIn('api_key', str(error.exception) + '\n'.join(logs.output))

    @override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='secret', EMBEDDING_DIMENSION=3)
    def test_remote_vectors_are_normalized_and_shape_validated(self):
        service = EmbeddingService()
        with patch.object(service, '_remote_embed_many', return_value=[[3, 4, 0]]):
            self.assertEqual(service.embed_text('q'), [0.6, 0.8, 0.0])
        for bad in ([[1, 2]], [[1, math.nan, 0]], [[math.inf, 0, 0]], []):
            with patch.object(service, '_remote_embed_many', return_value=bad):
                with self.assertRaises(EmbeddingUnavailableError):
                    service.embed_text('q')

    @override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='secret', EMBEDDING_DIMENSION=3)
    def test_response_indexes_must_be_a_complete_permutation(self):
        service = EmbeddingService()
        client = Mock()
        with patch.object(service, '_remote_client', return_value=client):
            client.embeddings.create.return_value = SimpleNamespace(data=[
                SimpleNamespace(index=1, embedding=[0, 1, 0]),
                SimpleNamespace(index=0, embedding=[1, 0, 0]),
            ])
            self.assertEqual(service.embed_many(['first', 'second']), [[1, 0, 0], [0, 1, 0]])
            for indexes in [(0, 0), (1, 2), (-1, 0)]:
                client.embeddings.create.return_value = SimpleNamespace(data=[
                    SimpleNamespace(index=index, embedding=[1, 0, 0]) for index in indexes
                ])
                with self.assertRaises(EmbeddingUnavailableError):
                    service.embed_many(['first', 'second'])

    @override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='secret', EMBEDDING_DIMENSION=128)
    def test_explicit_128_dimension_is_not_silently_promoted(self):
        self.assertEqual(EmbeddingService().dimension, 128)

    @override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='secret', EMBEDDING_DIMENSION=1024)
    def test_pgvector_is_a_copy_only_for_supported_dimension(self):
        service = EmbeddingService()
        with patch('django.db.connection.vendor', 'postgresql'):
            fields = service.storage_fields([1] + [0] * 1023)
            self.assertEqual(fields['embedding_vector'], fields['embedding'])
            small = EmbeddingService(dimension=3).storage_fields([1, 0, 0])
            self.assertIsNone(small['embedding_vector'])

    @override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='secret', EMBEDDING_DIMENSION=3)
    def test_version_covers_space_not_credentials(self):
        baseline = EmbeddingService().index_version
        for config in [
            {'EMBEDDING_MODEL': 'other-model'}, {'EMBEDDING_DIMENSION': 4},
            {'EMBEDDING_BASE_URL': 'https://another-provider.invalid/v1'},
            {'EMBEDDING_INDEX_REVISION': 'weights-2'}, {'EMBEDDING_PROVIDER': 'volcano'},
        ]:
            with self.settings(**config):
                self.assertNotEqual(EmbeddingService().index_version, baseline)
        with self.settings(EMBEDDING_API_KEY='rotated'):
            self.assertEqual(EmbeddingService().index_version, baseline)


@override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='test-key', EMBEDDING_DIMENSION=3)
class VersionedIndexTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='index-admin', role='admin', is_staff=True)
        self.teacher = get_user_model().objects.create_user(username='index-teacher', role='teacher')
        self.service = EmbeddingService()
        self.document_ct = ContentType.objects.get_for_model(DocumentSource)

    def make_row(self, text='unrelated', *, visibility='learner', versioned=True, chunk_index=0, source=None, **extra):
        source = source or DocumentSource.objects.create(
            title='fixture', filename='fixture.txt', source_hash=f'hash-{DocumentSource.objects.count()}',
            status='completed', visibility=visibility,
        )
        fields = self.service.storage_fields([1, 0, 0]) if versioned else {
            'embedding': [1, 0, 0], 'embedding_model': 'legacy-model', 'embedding_dimension': 3,
        }
        fields.update(extra)
        return LegalKnowledgeEmbedding.objects.create(
            source_type='document', content_type=self.document_ct, object_id=source.pk,
            chunk_index=chunk_index, title='fixture', text=text, text_hash='fixture-hash', **fields,
        )

    def register(self, row):
        catalog, _ = CatalogVersion.objects.get_or_create(version='index-test', defaults={'label': 'fixture'})
        return Material.objects.create(
            catalog=catalog, owner=self.admin, material_class='lesson',
            source_type=row.source_type, source_object_id=row.object_id,
        )

    def test_canonical_remote_json_works_on_sqlite_without_local_hash(self):
        row = self.make_row()
        self.assertEqual(row.embedding, [1.0, 0.0, 0.0])
        self.assertIsNone(row.embedding_vector)
        with patch.object(self.service, '_remote_embed_many', return_value=[[2, 0, 0]]):
            with patch.object(self.service, 'embed_local_text') as local:
                results = LegalRetrievalService(self.service).retrieve(query='distinctquery', user=self.admin)
        self.assertEqual([item['id'] for item in results], [row.pk])
        local.assert_not_called()

    def test_old_models_versions_dimensions_and_malformed_vectors_are_not_compared(self):
        current = self.make_row()
        for extra in [
            {'index_version': ''}, {'embedding_model': 'other'}, {'embedding_dimension': 9},
            {'embedding': [1, 0]}, {'embedding': ['not-a-number', 0, 0]},
        ]:
            self.make_row(**extra)
        with patch.object(self.service, '_remote_embed_many', return_value=[[1, 0, 0]]):
            results = LegalRetrievalService(self.service).retrieve(query='distinctquery', user=self.admin)
        self.assertEqual([item['id'] for item in results], [current.pk])
        self.assertEqual(self.service.compatible_queryset(LegalKnowledgeEmbedding.objects.all()).count(), 3)

    @override_settings(EMBEDDING_PROVIDER='', EMBEDDING_API_KEY='')
    def test_no_provider_retrieval_is_lexical_only_with_redacted_log(self):
        row = self.make_row(text='privacy consent', versioned=False)
        with self.assertLogs('legal_kb.services.retrieval_service', level='WARNING'):
            results = LegalRetrievalService().retrieve(query='consent', user=self.admin)
        self.assertEqual([item['id'] for item in results], [row.pk])
        log = LegalRetrievalLog.objects.get()
        self.assertNotIn('consent', log.query)
        self.assertEqual(log.results, [{'id': row.pk, 'source_type': 'document'}])

    def test_no_compatible_index_uses_lexical_only_without_provider_call(self):
        row = self.make_row(text='privacy consent', versioned=False)
        with patch.object(self.service, '_remote_embed_many') as remote:
            results = LegalRetrievalService(self.service).retrieve(query='privacy', user=self.admin)
        remote.assert_not_called()
        self.assertEqual([item['id'] for item in results], [row.pk])

    def test_remote_failure_keeps_lexical_rest_shape(self):
        row = self.make_row(text='privacy consent')
        with patch.object(self.service, '_remote_embed_many', side_effect=RuntimeError('PRIVATE')):
            results = LegalRetrievalService(self.service).retrieve(query='privacy', user=self.admin)
        self.assertEqual(results[0]['id'], row.pk)
        self.assertIn('rrf_score', results[0])

    def test_visibility_is_applied_before_any_query_embedding(self):
        self.make_row(visibility='staff')
        registered = self.make_row()
        self.register(registered)
        with patch.object(self.service, '_remote_embed_many') as remote:
            results = LegalRetrievalService(self.service).retrieve(query='private', user=self.teacher)
        self.assertEqual(results, [])
        remote.assert_not_called()

    def test_legal_ingestion_stores_versioned_canonical_vector(self):
        document = LegalDocument.objects.create(title='law', source_hash='law', full_text='第一条 privacy consent。')
        with patch.object(self.service, '_remote_embed_many', return_value=[[3, 4, 0]]):
            LegalKbIngestionService(self.service).ingest_document(document, actor=self.admin)
        row = LegalKnowledgeEmbedding.objects.get()
        self.assertEqual(row.embedding, [0.6, 0.8, 0])
        self.assertEqual(row.index_version, self.service.index_version)
        self.assertEqual(row.metadata['chunking_version'], ChunkingService.VERSION)

    def test_registered_legal_ingestion_is_blocked_before_provider(self):
        with self.settings(EMBEDDING_PROVIDER='local'):
            document = LegalDocument.objects.create(title='law', source_hash='law', full_text='第一条 registered secret。')
            LegalKbIngestionService().ingest_document(document, actor=self.admin)
        row = LegalKnowledgeEmbedding.objects.get()
        self.register(row)
        with patch.object(self.service, '_remote_embed_many') as remote:
            with self.assertRaises(ValueError):
                LegalKbIngestionService(self.service).ingest_document(document, actor=self.admin)
        remote.assert_not_called()
        self.assertTrue(LegalKnowledgeEmbedding.objects.filter(pk=row.pk).exists())
        self.assertTrue(KbIngestionJob.objects.filter(status='failed').exists())

    def test_platform_remote_index_excludes_registered_and_challenge_before_render(self):
        from articles.models import Article
        from challenges.models import Category, Challenge

        category = Category.objects.create(name='index-fixture')
        Challenge.objects.create(title='secret challenge', description='CHALLENGE-SECRET', category=category,
                                 difficulty='easy', score=10, flag='secret-flag')
        article = Article.objects.create(title='secret', content='SECRET', author=self.admin, status='approved')
        catalog = CatalogVersion.objects.create(version='platform-index', label='fixture')
        Material.objects.create(catalog=catalog, owner=self.admin, material_class='lesson',
                                source_type='article', source_object_id=article.pk)
        indexer = PlatformContentIndexingService(self.service)
        with patch.object(indexer, '_build_challenge_text') as render_challenge:
            with patch.object(self.service, '_remote_embed_many') as remote:
                result = indexer.index_articles(actor=self.admin)
                challenges = indexer.index_challenges(actor=self.admin)
        self.assertEqual(result.embedded_chunks, 0)
        self.assertEqual(challenges.embedded_chunks, 0)
        remote.assert_not_called()
        render_challenge.assert_not_called()

    def test_rebuild_dry_run_does_not_send_text_or_write(self):
        row = self.make_row(text='PRIVATE-BODY', versioned=False)
        output = io.StringIO()
        with patch('legal_kb.services.embedding_service.EmbeddingService._remote_embed_many') as remote:
            call_command('rebuild_legal_kb', actor=self.admin.username, dry_run=True, stdout=output)
        remote.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.index_version, '')
        self.assertNotIn('PRIVATE-BODY', output.getvalue())

    def test_rebuild_filters_live_visibility_and_registration_and_challenge(self):
        allowed = self.make_row(text='allowed', versioned=False)
        blocked = self.make_row(text='STAFF-SECRET', versioned=False, visibility='staff')
        registered = self.make_row(text='COURSE-SECRET', versioned=False)
        self.register(registered)
        challenge = self.make_row(text='CHALLENGE-SECRET', versioned=False)
        challenge.source_type = 'challenge'
        challenge.save(update_fields=['source_type'])
        output = io.StringIO()
        with patch('legal_kb.services.embedding_service.EmbeddingService._remote_embed_many', return_value=[[0, 2, 0]]) as remote:
            call_command('rebuild_legal_kb', actor=self.teacher.username, stdout=output)
        remote.assert_called_once_with(['allowed'])
        allowed.refresh_from_db()
        self.assertEqual(allowed.index_version, self.service.index_version)
        self.assertEqual(allowed.embedding, [0, 1, 0])
        for row in [blocked, registered, challenge]:
            row.refresh_from_db()
            self.assertEqual(row.index_version, '')
        self.assertNotIn('SECRET', output.getvalue())

    def test_rebuild_failure_preserves_entire_source_index(self):
        first = self.make_row(versioned=False)
        self.make_row(versioned=False, chunk_index=1, source=first.content_object)
        with patch('legal_kb.services.embedding_service.EmbeddingService._remote_embed_many', side_effect=RuntimeError('SECRET')):
            with self.assertRaises(CommandError) as error:
                call_command('rebuild_legal_kb', actor=self.admin.username, stdout=io.StringIO())
        self.assertNotIn('SECRET', str(error.exception))
        self.assertEqual(LegalKnowledgeEmbedding.objects.filter(index_version='').count(), 2)

    def test_rebuild_rechecks_visibility_after_source_lock(self):
        from .services.visibility import apply_embedding_visibility

        row = self.make_row(text='NEWLY-RESTRICTED', versioned=False)
        calls = 0

        def tightening_visibility(queryset, user):
            nonlocal calls
            calls += 1
            if calls == 2:
                DocumentSource.objects.filter(pk=row.object_id).update(visibility='staff')
            return apply_embedding_visibility(queryset, user)

        with patch('legal_kb.management.commands.rebuild_legal_kb.apply_embedding_visibility', side_effect=tightening_visibility):
            with patch('legal_kb.services.embedding_service.EmbeddingService._remote_embed_many') as remote:
                call_command('rebuild_legal_kb', actor=self.teacher.username, stdout=io.StringIO())
        remote.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.index_version, '')

    def test_rebuild_refuses_duplicate_chunk_generations(self):
        first = self.make_row(versioned=False)
        self.make_row(versioned=False, source=first.content_object, embedding_model='another-legacy-model')
        with patch('legal_kb.services.embedding_service.EmbeddingService._remote_embed_many') as remote:
            with self.assertRaises(CommandError):
                call_command('rebuild_legal_kb', actor=self.admin.username, stdout=io.StringIO())
        remote.assert_not_called()
        self.assertEqual(LegalKnowledgeEmbedding.objects.filter(index_version='').count(), 2)

    def test_rebuild_is_repeatable_and_rejects_missing_actor(self):
        row = self.make_row(versioned=False)
        with patch('legal_kb.services.embedding_service.EmbeddingService._remote_embed_many', return_value=[[1, 0, 0]]):
            for _ in range(2):
                call_command('rebuild_legal_kb', actor=self.admin.username, stdout=io.StringIO())
        self.assertEqual(LegalKnowledgeEmbedding.objects.count(), 1)
        row.refresh_from_db()
        self.assertEqual(row.index_version, self.service.index_version)
        with self.assertRaises(CommandError):
            call_command('rebuild_legal_kb', actor='missing', stdout=io.StringIO())
