"""Write-role coverage for document uploads, retries, and CLI ingestion."""

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from legal_kb.models import LegalKnowledgeEmbedding
from .models import DocumentSource
from .services import IngestionService


@override_settings(EMBEDDING_PROVIDER='local', RAG_INGESTION_USE_LANGCHAIN=False)
class DocumentWritePermissionTests(TestCase):
    url = '/api/rag-ingestion/documents/'
    body = b'# Teaching fixture\nOnly inspect systems within an authorized scope.'

    def setUp(self):
        users = get_user_model()
        self.student = users.objects.create_user(username='upload-student', role='student')
        self.teacher = users.objects.create_user(username='upload-teacher', role='teacher')
        self.admin = users.objects.create_user(username='upload-admin', role='admin')
        self.client = APIClient()

    def upload(self, actor, **data):
        self.client.force_authenticate(actor)
        return self.client.post(self.url, {
            'file': SimpleUploadedFile('lesson.md', self.body, content_type='text/markdown'),
            **data,
        }, format='multipart')

    def test_student_upload_and_reingest_are_denied_before_pipeline(self):
        with patch('rag_ingestion.views.UploadIngestionService') as service:
            for reingest in ('false', 'true'):
                with self.subTest(reingest=reingest):
                    self.assertEqual(self.upload(self.student, reingest=reingest).status_code, 403)
        service.assert_not_called()
        self.assertFalse(DocumentSource.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_teacher_upload_returns_completed_job_and_reingest_success(self):
        first = self.upload(self.teacher)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data['status'], 'completed')
        source = DocumentSource.objects.get(pk=first.data['id'])
        self.assertEqual(source.uploaded_by, self.teacher)
        self.assertGreater(source.embedded_count, 0)
        token = source.ingestion_token
        second = self.upload(self.teacher, reingest='true')
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(first.data['id'], second.data['id'])
        source.refresh_from_db()
        self.assertNotEqual(source.ingestion_token, token)
        self.assertEqual(LegalKnowledgeEmbedding.objects.count(), source.embedded_count)

    def test_admin_role_without_staff_can_upload(self):
        response = self.upload(self.admin)
        self.assertEqual(response.status_code, 201, response.data)

    def test_global_job_listing_remains_staff_only(self):
        for actor in (self.student, self.teacher, self.admin):
            with self.subTest(role=actor.role):
                self.client.force_authenticate(actor)
                self.assertEqual(self.client.get(self.url).status_code, 403)
        self.admin.is_staff = True
        self.admin.save(update_fields=['is_staff'])
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_no_document_update_delete_or_job_action_api(self):
        source = DocumentSource.objects.create(title='fixture', source_hash='a' * 64)
        self.client.force_authenticate(self.student)
        for method, url in (
            ('patch', self.url), ('delete', self.url),
            ('post', f'{self.url}{source.pk}/reingest/'),
            ('post', '/api/rag-ingestion/jobs/'),
        ):
            with self.subTest(method=method, url=url):
                self.assertIn(getattr(self.client, method)(url, {}, format='json').status_code, (403, 404, 405))
        self.assertEqual(DocumentSource.objects.count(), 1)
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_teacher_cannot_deduplicate_or_reingest_staff_source(self):
        self.assertEqual(self.upload(self.admin, visibility='staff').status_code, 201)
        source = DocumentSource.objects.get()
        original = (source.title, source.ingestion_token, source.visibility, source.uploaded_by_id)
        with patch('rag_ingestion.pipeline.IngestionPipeline.run') as pipeline:
            for reingest in ('false', 'true'):
                with self.subTest(reingest=reingest):
                    response = self.upload(self.teacher, visibility='learner', reingest=reingest)
                    self.assertEqual(response.status_code, 403, response.data)
        pipeline.assert_not_called()
        source.refresh_from_db()
        self.assertEqual((source.title, source.ingestion_token, source.visibility, source.uploaded_by_id), original)

    def test_teacher_reingest_cannot_widen_source_visibility(self):
        self.assertEqual(self.upload(self.teacher, visibility='internal').status_code, 201)
        response = self.upload(self.teacher, visibility='learner', reingest='true')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['visibility'], 'internal')

    def test_service_denies_explicit_student_and_inactive_teacher_before_writes(self):
        self.teacher.is_active = False
        self.teacher.save(update_fields=['is_active'])
        with patch('rag_ingestion.pipeline.IngestionPipeline.run') as pipeline:
            for actor in (self.student, self.teacher):
                with self.subTest(role=actor.role), self.assertRaises(PermissionDenied):
                    IngestionService().ingest_bytes(data=self.body, filename='lesson.md', uploaded_by=actor)
        pipeline.assert_not_called()
        self.assertFalse(DocumentSource.objects.exists())

    def test_ingest_documents_command_denies_student_and_accepts_teacher(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / 'lesson.md'
            path.write_bytes(self.body)
            with self.assertRaises(CommandError):
                call_command('ingest_documents', str(path), actor=self.student.username, stdout=io.StringIO())
            self.assertFalse(DocumentSource.objects.exists())
            call_command('ingest_documents', str(path), actor=self.teacher.username, stdout=io.StringIO())
        source = DocumentSource.objects.get()
        self.assertEqual(source.status, 'completed')
        self.assertEqual(source.uploaded_by, self.teacher)

    def test_anonymous_upload_is_denied_before_ingestion(self):
        with patch('rag_ingestion.views.UploadIngestionService') as service:
            self.assertIn(self.upload(None).status_code, (401, 403))
        service.assert_not_called()
