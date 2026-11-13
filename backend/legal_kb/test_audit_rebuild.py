"""Rebuild uses the current protected factory and separate local/semantic spaces."""
import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from learning_knowledge.models import Material
from learning_map.models import CatalogVersion
from rag_ingestion.models import DocumentSource
from .models import LegalKnowledgeEmbedding
from .services.embedding_service import EmbeddingService


@override_settings(EMBEDDING_PROVIDER='')
class RebuildAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_user(username='rebuild-audit-admin', role='admin')
        cls.student = users.objects.create_user(username='rebuild-audit-student', role='student')

    def row(self, title='Audit source', source=None, **options):
        source = source or DocumentSource.objects.create(
            title=title, filename='source.txt', source_hash=title, visibility='internal', status='completed')
        return LegalKnowledgeEmbedding.objects.create(source_type='document',
            content_type=ContentType.objects.get_for_model(DocumentSource), object_id=source.pk,
            title=title, text='Audit body', text_hash='a' * 64, embedding=[99],
            embedding_model='old-model', metadata={'source_note': 'preserve'}, **options)

    def run_command(self, **options):
        return call_command('rebuild_legal_kb', actor=self.admin.username, stdout=io.StringIO(), **options)

    def test_dry_run_never_embeds_or_changes_rows(self):
        row = self.row()
        before = LegalKnowledgeEmbedding.objects.get(pk=row.pk).__dict__.copy()
        before.pop('_state')
        with patch('legal_kb.services.embedding_service.EmbeddingService.embed_many') as embed:
            self.run_command(dry_run=True)
        embed.assert_not_called()
        after = LegalKnowledgeEmbedding.objects.get(pk=row.pk).__dict__.copy()
        after.pop('_state')
        self.assertEqual(before, after)

    def test_local_rebuild_records_the_current_vector_space_and_is_repeatable(self):
        row = self.row()
        self.run_command()
        self.run_command()
        row.refresh_from_db()
        self.assertEqual(row.embedding_model, 'local-hash-v1')
        self.assertEqual(row.embedding_dimension, 128)
        self.assertEqual(row.embedding, EmbeddingService(local_only=True).embed_text(row.text))
        self.assertIsNone(row.embedding_vector)
        self.assertEqual(row.metadata['vector_space'], EmbeddingService.LOCAL_VECTOR_SPACE)
        self.assertEqual(row.metadata['source_note'], 'preserve')
        self.assertEqual(LegalKnowledgeEmbedding.objects.count(), 1)

    def test_reserved_material_and_challenge_are_excluded(self):
        allowed = self.row('Allowed')
        reserved = self.row('Reserved')
        challenge = self.row('Challenge')
        challenge.source_type = 'challenge'
        challenge.save(update_fields=['source_type'])
        catalog = CatalogVersion.objects.create(version='rebuild-audit', label='Audit')
        Material.objects.create(catalog=catalog, owner=self.admin, material_class='teacher_answer',
            source_type='document', source_object_id=reserved.object_id)
        self.run_command()
        allowed.refresh_from_db()
        self.assertEqual(allowed.embedding_model, 'local-hash-v1')
        for row in (reserved, challenge):
            row.refresh_from_db()
            self.assertEqual(row.embedding_model, 'old-model')

    def test_provider_failure_rolls_back_all_chunks_of_the_source(self):
        first = self.row()
        self.row('Second chunk', source=first.content_object, chunk_index=1)
        with patch('legal_kb.services.embedding_service.EmbeddingService.embed_many',
                   side_effect=RuntimeError('PRIVATE-PROVIDER-DETAIL')):
            with self.assertRaises(CommandError) as error:
                self.run_command()
        self.assertNotIn('PRIVATE-PROVIDER-DETAIL', str(error.exception))
        self.assertEqual(LegalKnowledgeEmbedding.objects.filter(embedding_model='old-model').count(), 2)

    def test_student_is_rejected_before_factory_or_provider(self):
        with patch('legal_kb.services.embedding_service.EmbeddingService.embed_many') as embed:
            with self.assertRaises(CommandError):
                call_command('rebuild_legal_kb', actor=self.student.username, stdout=io.StringIO())
        embed.assert_not_called()

    @override_settings(EMBEDDING_PROVIDER='qwen', EMBEDDING_DIMENSION=1024)
    def test_remote_rebuild_preserves_local_vectors_and_records_semantic_space(self):
        row = self.row()
        remote_vector = [1.0] + [0.0] * 1023
        with patch('legal_kb.services.embedding_service.EmbeddingService.embed_many',
                   return_value=[remote_vector]):
            self.run_command()
        row.refresh_from_db()
        self.assertEqual(row.embedding, EmbeddingService(local_only=True).embed_text(row.text))
        self.assertEqual(row.embedding_model, 'local-hash-v1')
        self.assertEqual(row.embedding_dimension, 128)
        self.assertEqual(row.metadata['vector_space'], 'qwen/text-embedding-v3/1024/raw-v1')
        self.assertEqual(row.metadata['retrieval_mode'], 'semantic')
        self.assertEqual(list(row.embedding_vector), remote_vector)

    def test_missing_batch_vector_rolls_back_the_entire_source(self):
        first = self.row()
        self.row('Second chunk', source=first.content_object, chunk_index=1)
        with patch('legal_kb.services.embedding_service.EmbeddingService.embed_many', return_value=[[1.0]]):
            with self.assertRaises(CommandError):
                self.run_command()
        self.assertEqual(LegalKnowledgeEmbedding.objects.filter(embedding_model='old-model').count(), 2)

    def test_invalid_vector_is_rejected_without_changing_the_index(self):
        row = self.row()
        for vector in ([0.0], [float('nan')] * 128, [True] * 128):
            with self.subTest(vector_kind=type(vector[0]).__name__, dimension=len(vector)):
                with patch('legal_kb.services.embedding_service.EmbeddingService.embed_many',
                           return_value=[vector]):
                    with self.assertRaises(CommandError):
                        self.run_command()
                row.refresh_from_db()
                self.assertEqual(row.embedding_model, 'old-model')

    def test_protected_mode_rejects_teacher_before_constructing_the_factory(self):
        teacher = get_user_model().objects.create_user(username='rebuild-audit-teacher', role='teacher')
        with patch('legal_kb.management.commands.rebuild_legal_kb.rag_protection_enabled', return_value=True):
            with patch('legal_kb.management.commands.rebuild_legal_kb.get_embedding_service') as factory:
                with self.assertRaises(CommandError):
                    call_command('rebuild_legal_kb', actor=teacher.username, stdout=io.StringIO())
        factory.assert_not_called()
