from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from articles.models import Article
from legal_kb.models import LegalRetrievalLog
from legal_kb.serializers import LegalRetrievalLogSerializer
from learning_knowledge.models import CourseGrant
from learning_knowledge.policy import Scope, authorize
from learning_knowledge.services import search
from rag_ingestion.adapters.repository_legalkb import LegalKbChunkRepository
from rag_ingestion.interfaces import SupersededIngestionError
from rag_ingestion.models import DocumentSource
from rag_ingestion.services import IngestionService
from resources.models import Resource
from teaching_agent.tests.test_context_permissions import make_task_attempt
from .helpers import material, setup_case


class IntegrityTests(TestCase):
    def setUp(self):
        setup_case(self)
        self.pipeline = Mock()
        self.pipeline.run.return_value = SimpleNamespace(parser='synthetic', chunk_count=1, embedded_count=1)
        self.service = IngestionService(self.pipeline)

    def ingest(self, visibility, **kwargs):
        return self.service.ingest_bytes(data=b'SYNTHETIC DOCUMENT', filename='draft.txt',
                                         visibility=visibility, uploaded_by=self.admin, **kwargs)

    def test_t3_08_same_hash_tightens_even_without_reingestion(self):
        first = self.ingest('learner')
        token = first.ingestion_token
        duplicate = self.ingest('staff')
        self.assertEqual(first.pk, duplicate.pk)
        self.assertEqual(duplicate.visibility, 'staff')
        self.assertEqual(duplicate.ingestion_token, token)
        self.assertEqual(self.pipeline.run.call_count, 1)
        self.assertEqual(self.ingest('learner').visibility, 'staff')

    def test_t3_08_reingest_never_broadens_visibility_or_overwrites_owner(self):
        first = self.ingest('staff')
        second = self.service.ingest_bytes(data=b'SYNTHETIC DOCUMENT', filename='new.txt',
            visibility='learner', uploaded_by=self.teacher, metadata={'visibility': 'learner'}, reingest=True)
        self.assertEqual(second.visibility, 'staff')
        self.assertEqual(second.uploaded_by_id, self.admin.pk)
        self.assertNotEqual(first.ingestion_token, second.ingestion_token)
        self.assertEqual(self.pipeline.run.call_args.kwargs['base_metadata']['visibility'], 'staff')
        with self.assertRaises(ValidationError):
            self.ingest('unknown')

    def test_t3_08_old_worker_and_missing_token_cannot_replace_or_finish(self):
        old = self.ingest('staff')
        fresh = self.ingest('staff', reingest=True)
        for token in (old.ingestion_token, None):
            with self.subTest(token=token):
                with self.assertRaises(SupersededIngestionError):
                    LegalKbChunkRepository().replace(document_id=old.pk, source_type='document', embedded=[],
                                                     base_metadata={}, ingestion_token=token)
        result, updated = self.service._finish(old.pk, old.ingestion_token, status='failed', error_message='OLD')
        self.assertFalse(updated)
        self.assertEqual(result.status, fresh.status)
        self.assertEqual(result.error_message, '')

    def test_t3_15_error_and_historical_logs_never_replay_source_content(self):
        self.pipeline.run.side_effect = RuntimeError('SECRET DOCUMENT BODY')
        document = self.ingest('staff', title='SECRET TITLE')
        self.assertEqual(document.status, 'failed')
        self.assertEqual(document.error_message, 'RuntimeError')
        log = LegalRetrievalLog.objects.create(query='SECRET QUERY', results=[{'title': 'SECRET', 'text': 'SECRET BODY'}],
                                              filters={'raw': 'SECRET'}, user=self.admin)
        self.assertNotIn('SECRET', str(LegalRetrievalLogSerializer(log).data))

    def test_t3_06_cross_course_candidate_cache_cannot_reuse_old_body(self):
        from unittest.mock import patch
        revision = material(self, text='COURSE-ONE-PRIVATE')
        search(self.scope)
        task, attempt = make_task_attempt(self.student, suffix='other-course')
        CourseGrant.objects.create(user=self.student, catalog=task.catalog)
        with patch('learning_knowledge.services.cache.get', return_value=list(revision.chunks.values_list('pk', flat=True))):
            result = search(Scope(self.student, attempt.attempt_id))
        self.assertEqual(result['results'], [])
        self.assertNotIn('COURSE-ONE-PRIVATE', str(result))

    def test_t3_09_conflicting_source_classification_never_uses_weakest_acl(self):
        article = Article.objects.create(author=self.teacher, title='secret', content='same body', status='approved')
        public = material(self, text=article.content, source_type='article', source_id=article.pk)
        material(self, 'teacher_answer', text=article.content, source_type='article', source_id=article.pk)
        self.assertIsNone(authorize(public.pk, self.scope))
        self.assertEqual(search(self.scope)['results'], [])

    def test_t3_06_teacher_warm_cache_and_two_student_courses_are_isolated(self):
        from django.core.cache import cache
        from unittest.mock import patch

        cache.clear()
        scopes = [self.scope]
        revisions = [material(self, text='sharedword STUDENT-ONE')]
        for user, label in ((self.teacher, 'TEACHER-ONLY'), (self.other, 'STUDENT-TWO')):
            task, attempt = make_task_attempt(user, suffix=f'cache-{label.lower()}')
            CourseGrant.objects.create(user=user, catalog=task.catalog)
            revisions.append(material(SimpleNamespace(task=task, teacher=self.teacher), text=f'sharedword {label}'))
            scopes.append(Scope(user, attempt.attempt_id))
        keys = []
        # Warm the teacher's own course first, then both student courses using the same query.
        for index in (1, 0, 2):
            with patch('learning_knowledge.services.cache.get', wraps=cache.get) as cache_get:
                result = search(scopes[index], query='sharedword')
            keys.append(cache_get.call_args.args[0])
            self.assertEqual([item['excerpt'] for item in result['results']], [revisions[index].source_snapshot])
            self.assertEqual(cache.get(keys[-1]), list(revisions[index].chunks.values_list('pk', flat=True)))
        self.assertEqual(len(set(keys)), 3)
        candidate_ids = [revision.chunks.get().pk for revision in revisions]
        for scope, revision in zip(scopes, revisions):
            cached = search(scope, query='sharedword')
            self.assertEqual([item['excerpt'] for item in cached['results']], [revision.source_snapshot])
            with patch('learning_knowledge.services.cache.get', return_value=candidate_ids):
                poisoned = search(scope, query='sharedword')
            self.assertEqual([item['excerpt'] for item in poisoned['results']], [revision.source_snapshot])

    def test_grading_secret_not_in_ordinary_admin_resource_list(self):
        resource = Resource.objects.create(title='SECRET', description='SECRET', resource_type='document',
                                           category='m3', uploader=self.admin, status='approved')
        material(self, 'grading_secret', text='SECRET', source_type='resource', source_id=resource.pk)
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get('/api/resources/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('SECRET', str(response.data))
        self.assertEqual(client.get('/media/resources/secret.txt').status_code, 404)
