"""Unauthorized explicit actors must fail before providers, files, or seed writes."""
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from challenges.models import Challenge
from legal_kb.models import KbIngestionJob, LegalDocument, LegalKnowledgeEmbedding
from legal_kb.services.embedding_service import EmbeddingService
from legal_kb.services.ingestion_service import LegalKbIngestionService
from legal_kb.services.platform_indexing_service import PlatformContentIndexingService


@override_settings(EMBEDDING_PROVIDER='')
class LegalActorAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.student = users.objects.create_user(username='audit-legal-student', role='student')
        cls.inactive = users.objects.create_user(username='audit-legal-inactive', role='teacher', is_active=False)
        cls.admin = users.objects.create_user(username='audit-legal-admin', role='admin')
        cls.document = LegalDocument.objects.create(title='Audit law', full_text='第一条 保存证据。', source_hash='f' * 64)

    def test_prepare_rejects_explicit_student_before_seed_or_indexing(self):
        with patch('legal_kb.management.commands.prepare_legal_kb.PlatformContentIndexingService') as indexer:
            with self.assertRaises(CommandError):
                call_command('prepare_legal_kb', actor=self.student.username,
                    seed_sql_exercises=True, platform_only=True, stdout=io.StringIO())
        indexer.assert_not_called()
        self.assertFalse(Challenge.objects.exists())

    def test_fetch_rejects_student_before_network_or_cache_creation(self):
        with TemporaryDirectory() as directory:
            cache = Path(directory) / 'must-not-exist'
            with patch('legal_kb.management.commands.fetch_official_laws.FlkClient') as client:
                with self.assertRaises(CommandError):
                    call_command('fetch_official_laws', actor=self.student.username,
                        cache_dir=str(cache), stdout=io.StringIO())
            client.assert_not_called()
            self.assertFalse(cache.exists())

    def test_ingestion_rejects_student_before_embedding_factory_or_job(self):
        with patch('legal_kb.services.ingestion_service.get_embedding_service') as factory:
            with self.assertRaises(ValueError):
                LegalKbIngestionService().ingest_document(self.document, actor=self.student)
        factory.assert_not_called()
        self.assertFalse(KbIngestionJob.objects.exists())

    def test_platform_index_rejects_student_before_embedding_factory(self):
        with patch('legal_kb.services.platform_indexing_service.get_embedding_service') as factory:
            with self.assertRaises(ValueError):
                PlatformContentIndexingService().index_all(actor=self.student)
        factory.assert_not_called()
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_inactive_teacher_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command('prepare_legal_kb', actor=self.inactive.username,
                platform_only=True, stdout=io.StringIO())
        with self.assertRaises(ValueError):
            LegalKbIngestionService(EmbeddingService(local_only=True)).ingest_document(
                self.document, actor=self.inactive)

    def test_authorized_offline_admin_can_index_with_explicit_local_vectors(self):
        job = LegalKbIngestionService(EmbeddingService(local_only=True)).ingest_document(
            self.document, actor=self.admin)
        self.assertEqual(job.status, 'completed')
        self.assertGreater(LegalKnowledgeEmbedding.objects.count(), 0)
