"""Focused tests for automated and hybrid exercise fact input."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLedgerEntry
from challenges.container_audit import record_container_audit, record_flag_submission_audit
from challenges.models import Category, Challenge, ChallengeContainer
from submissions.models import Submission

from .models import LegalFactSnapshot
from .services.fact_redactor import redact_manual_notes


User = get_user_model()


class ExerciseFactSnapshotApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='fact-admin', password='pass12345', role='admin', is_staff=True
        )
        self.teacher = User.objects.create_user(
            username='fact-teacher', password='pass12345', role='teacher'
        )
        self.student = User.objects.create_user(
            username='fact-student', password='pass12345', role='student'
        )
        category = Category.objects.create(name='Fact Web')
        self.challenge = Challenge.objects.create(
            title='Fact SQL Lab',
            description='Authorized lab',
            category=category,
            difficulty='easy',
            score=100,
            flag='flag{correct}',
            docker_image='ctf/sql-fact:latest',
        )
        started = timezone.now() - timedelta(minutes=10)
        self.container = ChallengeContainer.objects.create(
            user=self.student,
            challenge=self.challenge,
            container_id='fact-session-1',
            docker_container_name='fact-container-1',
            status='running',
            port=18080,
            started_at=started,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        record_container_audit(
            action='start_succeeded',
            result='success',
            container=self.container,
            network='ctf-network',
            cpu_limit=0.5,
            memory_limit='512m',
        )
        self.submission = Submission.objects.create(
            user=self.student,
            challenge=self.challenge,
            flag='flag{wrong}',
            ip_address='127.0.0.1',
            user_agent='test',
        )

    def test_teacher_cannot_preview_automated_facts(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post(
            '/api/legal/exercise-facts/preview/',
            {'container_id': self.container.id},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_preview_is_read_only_and_contains_no_sensitive_payload(self):
        self.client.force_authenticate(self.admin)
        before_snapshots = LegalFactSnapshot.objects.count()
        response = self.client.post(
            '/api/legal/exercise-facts/preview/',
            {'container_id': self.container.id},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LegalFactSnapshot.objects.count(), before_snapshots)
        self.assertEqual(response.data['facts']['container_id'], self.container.id)
        self.assertEqual(response.data['facts']['flag_submission_count'], 1)
        serialized = str(response.data).lower()
        self.assertNotIn('127.0.0.1', serialized)
        self.assertNotIn('flag{wrong}', serialized)

    def test_confirm_creates_hybrid_snapshot_and_pending_task(self):
        self.client.force_authenticate(self.admin)
        preview = self.client.post(
            '/api/legal/exercise-facts/preview/',
            {'container_id': self.container.id},
            format='json',
        ).data
        response = self.client.post(
            '/api/legal/exercise-facts/confirm/',
            {
                'container_id': self.container.id,
                'preview_hash': preview['preview_hash'],
                'manual_notes': '授权课程，token=secret flag{hidden}',
                'title': '事实快照审查',
                'run_analysis': False,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        snapshot = LegalFactSnapshot.objects.get(pk=response.data['id'])
        self.assertEqual(snapshot.source_kind, 'hybrid')
        self.assertIn('[REDACTED]', snapshot.manual_notes)
        self.assertNotIn('secret', snapshot.manual_notes)
        self.assertNotIn('hidden', snapshot.manual_notes)
        self.assertEqual(snapshot.analysis_task.status, 'pending')
        self.assertEqual(snapshot.analysis_task.metadata['fact_snapshot_id'], snapshot.id)
        self.assertNotIn(snapshot.snapshot_hash, snapshot.analysis_task.input_text)
        self.assertTrue(AuditLedgerEntry.objects.filter(
            event_category='exercise_fact_snapshot', object_id=str(snapshot.id)
        ).exists())

    def test_changed_preview_is_rejected(self):
        self.client.force_authenticate(self.admin)
        preview = self.client.post(
            '/api/legal/exercise-facts/preview/',
            {'container_id': self.container.id},
            format='json',
        ).data
        record_container_audit(
            action='status_checked', result='running', container=self.container
        )
        response = self.client.post(
            '/api/legal/exercise-facts/confirm/',
            {
                'container_id': self.container.id,
                'preview_hash': preview['preview_hash'],
                'run_analysis': False,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'FACT_PREVIEW_CHANGED')
        self.assertEqual(LegalFactSnapshot.objects.count(), 0)

    def test_manual_redaction_has_length_and_secret_guards(self):
        value = redact_manual_notes('password=hunter2 flag{private}')
        self.assertNotIn('hunter2', value)
        self.assertNotIn('private', value)

    def test_flag_audit_does_not_hide_recorded_resource_limits(self):
        record_flag_submission_audit(submission=self.submission, container=self.container)
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            '/api/legal/exercise-facts/preview/',
            {'container_id': self.container.id},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['facts']['has_cpu_limit'])
        self.assertTrue(response.data['facts']['has_memory_limit'])
        self.assertNotIn('missing_resource_limit', response.data['warnings'])
