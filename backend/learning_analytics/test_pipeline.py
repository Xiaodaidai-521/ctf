from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import CTFUser

from .models import LearningAuditJob, LearningEffectSnapshot, LearningEvent
from .scheduler import run_analytics_job


class LearningPipelineTests(TestCase):
    def setUp(self):
        self.teacher = CTFUser.objects.create_user(username='teacher', password='Password123!', role='teacher')
        self.student = CTFUser.objects.create_user(username='student', password='Password123!', role='student')
        self.client = APIClient()

    def event_payload(self, event_id, event_type='page_heartbeat', offset=0):
        event_time = timezone.now() - timedelta(minutes=10 - offset)
        return {'eventId': event_id, 'eventType': event_type, 'eventTime': event_time.isoformat(), 'durationMs': 120000, 'clientSessionId': 'session-1', 'metadata': {'source': 'test'}}

    def test_event_batch_is_idempotent_and_rejects_invalid_duration(self):
        self.client.force_authenticate(self.student)
        response = self.client.post('/api/analytics/learning/events/batch/', {'events': [self.event_payload('evt-1')]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['accepted_count'], 1)
        duplicate = self.client.post('/api/analytics/learning/events/batch/', {'events': [self.event_payload('evt-1')]}, format='json')
        self.assertEqual(duplicate.data['results'][0]['status'], 'duplicate')
        invalid = self.event_payload('evt-2')
        invalid['durationMs'] = 'invalid'
        rejected = self.client.post('/api/analytics/learning/events/batch/', {'events': [invalid]}, format='json')
        self.assertEqual(rejected.data['results'][0]['code'], 'invalid_duration')
        self.assertEqual(LearningEvent.objects.filter(user=self.student).count(), 1)

    def test_job_builds_snapshot_and_same_scope_is_idempotent(self):
        now = timezone.now()
        LearningEvent.objects.create(event_id='event-a', user=self.student, event_type='page_heartbeat', event_time=now - timedelta(minutes=20), duration_ms=300000, client_session_id='one')
        LearningEvent.objects.create(event_id='event-b', user=self.student, event_type='exercise_submit', event_time=now - timedelta(minutes=15), duration_ms=60000, client_session_id='one', metadata={'success': True})
        first = run_analytics_job(job_type='manual', days=30, user_id=self.student.id)
        second = run_analytics_job(job_type='manual', days=30, user_id=self.student.id)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.status, 'completed')
        self.assertEqual(LearningAuditJob.objects.count(), 1)
        self.assertTrue(LearningEffectSnapshot.objects.filter(user=self.student).exists())

    def test_summary_reads_snapshot_without_triggering_rebuild(self):
        self.client.force_authenticate(self.teacher)
        empty = self.client.get(f'/api/analytics/learning/effect/?student_id={self.student.id}&days=30')
        self.assertEqual(empty.status_code, 200)
        self.assertIsNone(empty.data['snapshot'])
        self.assertEqual(LearningEffectSnapshot.objects.count(), 0)
        run_analytics_job(job_type='manual', days=30, user_id=self.student.id)
        populated = self.client.get(f'/api/analytics/learning/effect/?student_id={self.student.id}&days=30')
        self.assertEqual(populated.status_code, 200)
        self.assertIsNotNone(populated.data['snapshot'])
        self.assertIn('time_score', populated.data['snapshot']['dimensions'])
