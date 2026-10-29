from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.utils import timezone

from audit.models import AuditEvent
from . import tests as fixtures
from .models import EnvironmentApproval
from .policy import REQUIRED_CHECKS


class LifecycleTests(fixtures.TrainingTestCase):
    start = fixtures.EvidenceTests.start
    verify = fixtures.EvidenceTests.verify

    def control(self, assignment, action):
        return self.client.post(self.url(assignment, 'control/'),
                                {'action': action, 'reason': 'fixture operation'}, format='json')

    def test_teacher_pause_resume_and_isolate(self):
        assignment = self.allocate()
        self.start(assignment)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.control(assignment, 'pause').data['state'], 'paused')
        self.client.force_authenticate(self.student)
        with patch('practical_training.verifiers.observe_challenge') as network:
            self.assertEqual(self.verify(assignment).status_code, 400)
        network.assert_not_called()
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.control(assignment, 'resume').data['state'], 'active')
        isolated = self.control(assignment, 'isolate')
        self.assertEqual(isolated.data['state'], 'isolated')
        self.assertEqual(isolated.data['physical_cleanup'], 'pending_operator')
        self.assertEqual(isolated.data['scope']['target'], '')
        self.assertEqual(self.control(assignment, 'resume').status_code, 400)
        self.assertTrue(EnvironmentApproval.objects.get(container=self.container).revoked)
        self.container.refresh_from_db()
        self.assertEqual(self.container.status, 'running')  # No fictitious Docker destruction.

    def test_student_cannot_use_teacher_controls_and_cross_student_reset_denied(self):
        assignment = self.allocate()
        for action in ('pause', 'resume', 'isolate'):
            self.assertEqual(self.control(assignment, action).status_code, 403)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.control(assignment, 'reset').status_code, 404)
        self.assertTrue(AuditEvent.objects.filter(detail__action='denied').exists())

    def test_owner_reset_closes_old_attempt_without_reusing_instance(self):
        assignment = self.allocate()
        reset = self.control(assignment, 'reset')
        self.assertEqual(reset.status_code, 200, reset.content)
        assignment.refresh_from_db()
        assignment.attempt.refresh_from_db()
        self.assertEqual(assignment.state, 'reset')
        self.assertEqual(assignment.attempt.status, 'abandoned')
        self.assertNotEqual(self.claim(), str(assignment.attempt.attempt_id))
        self.assertEqual(self.client.post(self.url(assignment, 'start/'), {}, format='json').status_code, 400)

    def test_expiry_dry_run_then_idempotent_platform_reclamation(self):
        assignment = self.allocate()
        assignment.expires_at = timezone.now() - timedelta(seconds=1)
        assignment.save(update_fields=['expires_at'])
        call_command('expire_practical_training', dry_run=True, stdout=StringIO())
        assignment.refresh_from_db()
        self.assertEqual(assignment.state, 'allocated')
        call_command('expire_practical_training', stdout=StringIO())
        call_command('expire_practical_training', stdout=StringIO())
        assignment.refresh_from_db()
        self.assertEqual(assignment.state, 'expired')
        self.assertEqual(assignment.physical_cleanup, 'pending_operator')
        self.assertEqual(AuditEvent.objects.filter(detail__action='assignment_expired').count(), 1)
        self.assertEqual(self.client.post(self.url(assignment, 'start/'), {}, format='json').status_code, 400)

    def test_expired_read_reconciles_even_without_scheduler(self):
        assignment = self.allocate()
        assignment.expires_at = timezone.now() - timedelta(seconds=1)
        assignment.save()
        response = self.client.get(self.url(assignment))
        self.assertEqual(response.data['state'], 'expired')
        self.assertEqual(response.data['scope']['target'], '')

    def test_global_mapping_pause_blocks_existing_assignments(self):
        assignment = self.allocate()
        self.client.force_authenticate(self.teacher)
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/control/',
                                    {'action': 'pause', 'reason': 'fixture containment'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.post(self.url(assignment, 'hints/'), {'level': 1}, format='json').status_code, 400)

    def test_paused_mapping_can_be_reviewed_without_resuming(self):
        self.client.force_authenticate(self.teacher)
        control_url = f'/api/practical-training/mappings/{self.mapping.pk}/control/'
        self.assertEqual(self.client.post(control_url, {'action': 'pause', 'reason': 'review update'},
                                         format='json').status_code, 200)
        self.task.materials = {**self.task.materials, 'knowledge': 'reviewed update'}
        self.task.save()
        self.assertEqual(self.client.post(control_url, {'action': 'resume', 'reason': 'unreviewed'},
                                         format='json').status_code, 400)
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/review/',
                                    {'review_ref': 'fixture:paused-review'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.mapping.refresh_from_db()
        self.assertTrue(self.mapping.paused)
        self.client.force_authenticate(self.student)
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': self.claim(), 'accepted_aup': fixtures.AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.post(control_url, {'action': 'resume', 'reason': 'review complete'},
                                         format='json').status_code, 200)
        self.client.force_authenticate(self.student)
        self.allocate()

    def test_overdue_unreconciled_assignment_keeps_resource_reservation(self):
        assignment = self.allocate()
        assignment.expires_at = timezone.now() - timedelta(seconds=1)
        assignment.save(update_fields=['expires_at'])
        attempt = fixtures.TaskAttempt.objects.create(student=self.student, task=self.task,
                    catalog=self.catalog, task_version=self.task.version, capability_ids=['M5-TEST'], status='claimed')
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': str(attempt.attempt_id), 'accepted_aup': fixtures.AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('已达到个人实训分配额度', str(response.data))

    def test_resource_and_duration_caps_are_validated(self):
        from .policy import configured_policy
        from rest_framework.exceptions import ValidationError
        for policy in ({'cpu_millis': 1001}, {'memory_mib': 0}, {'duration_seconds': 7201},
                       {'max_active_per_student': True}, {'egress': 'allow'}, {'deny_production': False},
                       {'allowed_egress': ['https://example.com']}):
            with self.settings(PRACTICAL_TRAINING_POLICY=policy), self.assertRaises(ValidationError):
                configured_policy()
        with self.settings(PRACTICAL_TRAINING_POLICY={'duration_seconds': 30}):
            assignment = self.allocate()
        self.assertLessEqual((assignment.expires_at - assignment.accepted_at).total_seconds(), 30)

    def test_declared_resource_limit_must_match_approved_instance(self):
        with self.settings(PRACTICAL_TRAINING_POLICY={'memory_mib': 128}):
            response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                        {'attempt_id': self.claim(), 'accepted_aup': fixtures.AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_quota_blocks_second_active_assignment(self):
        self.allocate()
        attempt = fixtures.TaskAttempt.objects.create(student=self.student, task=self.task,
                    catalog=self.catalog, task_version=self.task.version, capability_ids=['M5-TEST'], status='claimed')
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': str(attempt.attempt_id), 'accepted_aup': fixtures.AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_environment_attestation_is_teacher_only_complete_and_bound(self):
        data = {'evidence_ref': 'fixture:external-evidence-not-real', 'checks': {key: True for key in REQUIRED_CHECKS},
                'limits': {'cpu_millis': 1000, 'memory_mib': 768, 'pids': 256},
                'expires_at': self.container.expires_at.isoformat()}
        url = f'/api/practical-training/environments/{self.container.pk}/approve/'
        self.assertEqual(self.client.post(url, data, format='json').status_code, 403)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.post(url, {**data, 'checks': {}}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, data, format='json').status_code, 200)
        self.client.force_authenticate(self.student)
        self.container.container_id = 'changed-instance'
        self.container.save()
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': self.claim(), 'accepted_aup': fixtures.AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_audit_failure_rolls_back_teacher_control(self):
        assignment = self.allocate()
        self.client.force_authenticate(self.teacher)
        with patch('practical_training.lifecycle.audit', side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError):
                self.control(assignment, 'isolate')
        assignment.refresh_from_db()
        self.assertEqual(assignment.state, 'allocated')
        self.assertFalse(EnvironmentApproval.objects.get(container=self.container).revoked)

    def test_pending_physical_cleanup_keeps_resource_reservation(self):
        from .lifecycle import reconcile_cleanup
        assignment = self.allocate()
        self.control(assignment, 'reset')
        attempt_id = self.claim()
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': attempt_id, 'accepted_aup': fixtures.AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(reconcile_cleanup(student=self.student), 0)
        self.container.status = 'destroyed'
        self.container.destroyed_at = timezone.now()
        self.container.access_url = ''
        self.container.save()
        self.assertEqual(reconcile_cleanup(student=self.student), 1)
        assignment.refresh_from_db()
        self.assertEqual(assignment.physical_cleanup, 'confirmed_by_runtime')

    def test_challenge_alone_cannot_award_repair_capability(self):
        self.capability.dimension = 'repair'
        self.capability.save()
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': self.claim(), 'accepted_aup': fixtures.AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_correcting_legacy_challenge_key_requires_fresh_review(self):
        from importlib import import_module
        from django.apps import apps
        assignment = self.allocate()
        self.mapping.challenge_key = 'confidentialDocumentChallenge'
        self.mapping.save(update_fields=['challenge_key'])
        migration = import_module('practical_training.migrations.0003_correct_juice_challenge_key')
        migration.correct_key_and_require_review(apps, None)
        self.mapping.refresh_from_db()
        self.assertEqual(self.mapping.challenge_key, 'directoryListingChallenge')
        self.assertTrue(self.mapping.paused)
        self.assertIsNone(self.mapping.reviewed_by_id)
        self.assertIsNone(self.mapping.reviewed_at)
        self.assertEqual(self.mapping.review_hash, '')
        assignment.refresh_from_db()
        self.assertEqual(assignment.state, 'allocated')
        self.assertEqual(self.client.post(self.url(assignment, 'start/'), {}, format='json').status_code, 400)

    def test_course_review_hash_prevents_silent_material_change(self):
        self.task.materials = {**self.task.materials, 'knowledge': 'changed'}
        self.task.save()
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': self.claim(), 'accepted_aup': fixtures.AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)
        self.client.force_authenticate(self.teacher)
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/review/',
                                    {'review_ref': 'fixture:reviewed-changed-material'}, format='json')
        self.assertEqual(response.status_code, 200)
