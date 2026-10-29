import json

from django.test import TestCase
from rest_framework.test import APIClient

from evaluation_center.models import NonFormalAccount
from learning_map.models import KnowledgePoint, TaskAttempt
from skill_review.models import SubmissionSnapshot
from skill_review.services.submissions import create_submission
from skill_review.tests.test_module6 import make_catalog, make_capability, make_task, make_attempt, good_payload
from teaching_agent.models import TeachingRun, TutorRequest, ModelCallRecord
from users.models import CTFUser


class LearningAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = CTFUser.objects.create_user(username='123', role='student', email='PRIVATE@example.test')
        cls.other = CTFUser.objects.create_user(username='other', role='student')
        cls.teacher = CTFUser.objects.create_user(username='teacher', role='teacher')
        cls.admin = CTFUser.objects.create_user(username='admin', role='admin')
        cls.catalog = make_catalog()
        cls.capability = make_capability(cls.catalog)
        cls.point = KnowledgePoint.objects.create(catalog=cls.catalog, stable_id='POINT', track='data', name='Point')
        cls.capability.knowledge_points.add(cls.point)
        cls.task = make_task(cls.catalog, cls.capability)
        cls.attempt = make_attempt(cls.task, cls.student, cls.catalog)
        cls.submission, _ = create_submission(student=cls.student, attempt=cls.attempt,
                                              client_submission_id='real-submit', payload=good_payload())

    def setUp(self):
        self.client = APIClient()

    def test_anonymous_denied(self):
        for path in ('students/', 'learning/', 'runtime/', f'attempts/{self.attempt.attempt_id}/'):
            self.assertIn(self.client.get('/api/evaluation/' + path).status_code, (401, 403))

    def test_student_cannot_read_other_learning(self):
        self.client.force_authenticate(self.other)
        response = self.client.get('/api/evaluation/learning/', {'student_id': self.student.pk})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(f'/api/evaluation/attempts/{self.attempt.attempt_id}/').status_code, 403)

    def test_student_own_scope_and_teacher_endpoints(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get('/api/evaluation/learning/').data['rows'][0]['student_id'], self.student.pk)
        self.assertEqual(self.client.get(f'/api/evaluation/attempts/{self.attempt.attempt_id}/').status_code, 200)
        for path in ('students/', 'runtime/'):
            self.assertEqual(self.client.get('/api/evaluation/' + path).status_code, 403)
        self.assertEqual(self.client.get('/api/evaluation/learning/', {'mode': 'demo'}).status_code, 403)

    def test_teacher_and_admin_can_read_teaching_scope(self):
        for actor in (self.teacher, self.admin):
            self.client.force_authenticate(actor)
            response = self.client.get('/api/evaluation/learning/', {'student_id': self.student.pk, 'task_key': self.task.task_key,
                                                                     'knowledge_point_id': 'POINT', 'catalog_version': self.catalog.version})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['rows']), 1)
        self.assertEqual(self.client.get('/api/evaluation/learning/', {'task_key': 'absent'}).data['rows'], [])

    def test_only_teaching_fields_no_answers_or_identity_details(self):
        self.client.force_authenticate(self.teacher)
        responses = [self.client.get('/api/evaluation/students/'),
                     self.client.get(f'/api/evaluation/attempts/{self.attempt.attempt_id}/')]
        for response in responses:
            self.assertEqual(response.status_code, 200)
            text = json.dumps(response.data, ensure_ascii=False)
            for secret in ('PRIVATE@example.test', '数据安全法第二十一条', 'password', 'solutions/x.md'):
                self.assertNotIn(secret, text)

    def test_nonformal_students_excluded_from_all_formal_queries(self):
        self.client.force_authenticate(self.teacher)
        for source, student in [('demo', self.student), ('offline', self.other)]:
            NonFormalAccount.objects.create(student=student, source=source)
        self.assertEqual(self.client.get('/api/evaluation/students/').data['students'], [])
        self.assertEqual(self.client.get('/api/evaluation/learning/').data['rows'], [])
        self.assertEqual(self.client.get('/api/evaluation/learning/', {'student_id': self.student.pk}).status_code, 404)
        self.assertEqual(self.client.get(f'/api/evaluation/attempts/{self.attempt.attempt_id}/').status_code, 404)

    def test_explicit_demo_is_readonly_and_never_fallback(self):
        self.client.force_authenticate(self.teacher)
        before = (CTFUser.objects.count(), TaskAttempt.objects.count(), SubmissionSnapshot.objects.count())
        demo = self.client.get('/api/evaluation/learning/', {'mode': 'demo'})
        self.assertEqual(demo.data['source'], 'demo')
        self.assertTrue(all(row['source'] == 'demo' for row in demo.data['rows']))
        self.assertEqual(before, (CTFUser.objects.count(), TaskAttempt.objects.count(), SubmissionSnapshot.objects.count()))
        formal = self.client.get('/api/evaluation/learning/', {'student_id': self.other.pk})
        self.assertEqual(formal.data['status'], 'no_data')
        self.assertEqual(formal.data['rows'], [])
        self.assertEqual(formal.data['source'], 'formal')

    def test_unknown_or_invalid_query_rejected(self):
        self.client.force_authenticate(self.teacher)
        for params in ({'mode': 'anything'}, {'student_id': 'bad'}, {'role': 'admin'}, {'limit': 10000},
                       {'start': '2026-01-02T00:00:00Z', 'end': '2026-01-01T00:00:00Z'}):
            self.assertEqual(self.client.get('/api/evaluation/learning/', params).status_code, 400)

    def runtime_call(self):
        run = TeachingRun.objects.create(student=self.student, attempt=self.attempt, mode='data_security',
                                         task_version=self.task.version, catalog_version=self.catalog.version)
        request = TutorRequest.objects.create(request_id='req', idempotency_key='req', payload_hash='x' * 64,
                                               student=self.student, run=run, attempt=self.attempt,
                                               context_version=1, permission_version=1, status='degraded',
                                               response={'content': 'SECRET RESPONSE'})
        return ModelCallRecord.objects.create(request=request, call_id='call', status='failed', error_category='timeout',
                                               latency_ms=25, provider_request_id='SECRET CREDENTIAL')

    def test_runtime_unknown_costs_tokens_and_private_fields(self):
        self.runtime_call()
        self.client.force_authenticate(self.teacher)
        response = self.client.get('/api/evaluation/runtime/')
        self.assertEqual(response.status_code, 200)
        group = response.data['version_groups'][0]
        self.assertIsNone(group['costs'][0]['total']['numerator'])
        self.assertEqual(group['costs'][0]['total']['missing'], 1)
        self.assertIsNone(group['metrics']['input_tokens']['value'])
        self.assertEqual(group['metrics']['degraded_requests']['numerator'], 1)
        self.assertNotIn('SECRET', json.dumps(response.data))

    def test_runtime_excludes_demo_and_honors_filters(self):
        self.runtime_call()
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get('/api/evaluation/runtime/', {'task_key': 'missing'}).data['records'], [])
        NonFormalAccount.objects.create(student=self.student, source='offline')
        self.assertEqual(self.client.get('/api/evaluation/runtime/').data['records'], [])
