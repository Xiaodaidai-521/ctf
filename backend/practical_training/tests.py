from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from challenges.models import Category, Challenge, ChallengeContainer
from learning_map.models import Capability, CatalogVersion, TaskAttempt, TaskPackage
from practical_training.curriculum import HINTS, MATERIAL, REPAIR_MATERIAL
from practical_training.models import ChallengeMapping, EnvironmentApproval, LabAssignment
from practical_training.policy import AUP_VERSION, REQUIRED_CHECKS, DEFAULT_POLICY, environment_binding
from practical_training.services import CHALLENGE_VERIFIER, REPAIR_VERIFIER, mapping_hash
from users.models import CTFUser


@override_settings(PRACTICAL_TRAINING_ENABLED=True)
class TrainingTestCase(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='m5-student', role='student')
        self.other = CTFUser.objects.create_user(username='m5-other', role='student')
        self.teacher = CTFUser.objects.create_user(username='m5-teacher', role='teacher')
        self.catalog = CatalogVersion.objects.create(version='m5-test-v1', label='Fixture catalog', status='published')
        self.capability = Capability.objects.create(
            catalog=self.catalog, stable_id='M5-TEST', track='network', title='资料授权',
            observable_objective='检查资料访问边界', dimension='operate', status='open',
        )
        self.challenge = Challenge.objects.create(
            title='Juice Shop', category=Category.objects.create(name='Web'), difficulty='easy',
            score=0, flag='', submission_mode='practice', docker_image=settings.JUICE_SHOP_IMAGE,
        )
        self.task = self.make_task('m5-original', 'verification', CHALLENGE_VERIFIER, MATERIAL)
        self.repair_task = self.make_task('m5-repair', 'retest', REPAIR_VERIFIER, REPAIR_MATERIAL)
        self.task.retest_task_keys = [self.repair_task.task_key]
        self.task.save()
        self.mapping = ChallengeMapping.objects.create(
            task=self.task, repair_task=self.repair_task, reviewed_by=self.teacher,
            reviewed_at=timezone.now(), review_ref='fixture:course-review',
        )
        self.mapping.review_hash = mapping_hash(self.mapping)
        self.mapping.save(update_fields=['review_hash'])
        self.container = ChallengeContainer.objects.create(
            user=self.student, challenge=self.challenge, container_id='m5-fixture-container',
            docker_container_name='m5-fixture', status='running', port=settings.JUICE_SHOP_PORT_MIN,
            access_url=f'http://lab.example.test:{settings.JUICE_SHOP_PORT_MIN}/',
            started_at=timezone.now(), expires_at=timezone.now() + timedelta(hours=2),
            runtime_metadata={'profile': 'juice-shop'},
        )
        EnvironmentApproval.objects.create(
            container=self.container, reviewed_by=self.teacher, evidence_ref='fixture:NOT-LIVE-ISOLATION',
            checks={**{key: True for key in REQUIRED_CHECKS}, 'binding': environment_binding(self.container),
                    'limits': {key: DEFAULT_POLICY[key] for key in ('cpu_millis', 'memory_mib', 'pids')}},
            expires_at=self.container.expires_at,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def make_task(self, key, purpose, version, materials):
        task = TaskPackage.objects.create(
            catalog=self.catalog, task_key=key, version='1.0.0', title=key, track='network',
            purpose=purpose, execution_mode='isolated_challenge', status='frozen', challenge=self.challenge,
            materials=materials, hints=HINTS, validator={'type': 'server_verifier', 'version': version},
            acceptance={'server_evidence': True, 'scope': materials['scope']},
        )
        task.capabilities.set([self.capability])
        return task

    def claim(self):
        response = self.client.post(f'/api/learning-map/tasks/{self.task.pk}/claim/',
                                    {'version': self.catalog.version}, format='json')
        self.assertIn(response.status_code, (200, 201), response.content)
        return response.data['attempt_id']

    def allocate(self):
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': self.claim(), 'accepted_aup': AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        return LabAssignment.objects.get(assignment_id=response.data['assignment_id'])

    def url(self, assignment, action=''):
        return f'/api/practical-training/assignments/{assignment.assignment_id}/{action}'


class EvidenceTests(TrainingTestCase):
    def start(self, assignment):
        with patch('practical_training.verifiers.observe_challenge', return_value={'solved': False}):
            response = self.client.post(self.url(assignment, 'start/'), {}, format='json')
        self.assertEqual(response.status_code, 200, response.content)

    def verify(self, assignment, solved=True, key='server-test'):
        with patch('practical_training.verifiers.observe_challenge', return_value={'solved': solved}):
            return self.client.post(self.url(assignment, 'verify/'), {'key': key}, format='json')

    def test_server_evidence_is_bound_and_delivered_to_module_six_and_one(self):
        from learning_map.models import VerificationFact
        from skill_review.models import VerificationResult
        assignment = self.allocate()
        self.start(assignment)
        response = self.verify(assignment)
        self.assertEqual(response.status_code, 201, response.content)
        result = VerificationResult.objects.get(result_id=response.data['result_id'])
        self.assertEqual(result.overall_status, 'passed')
        self.assertEqual(result.attempt_id, assignment.attempt_id)
        self.assertEqual(result.verifier_version, CHALLENGE_VERIFIER)
        self.assertTrue(VerificationFact.objects.filter(attempt_id=assignment.attempt.attempt_id).exists())
        self.assertTrue(result.module1_fact_ids)

    def test_self_report_and_direct_module_six_json_cannot_pass(self):
        from skill_review.models import VerificationResult
        assignment = self.allocate()
        response = self.client.post(self.url(assignment, 'self-report/'), {}, format='json')
        self.assertFalse(response.data['verified'])
        self.assertFalse(VerificationResult.objects.exists())
        forged = self.client.post(self.url(assignment, 'verify/'), {'key': 'forged', 'solved': True}, format='json')
        self.assertEqual(forged.status_code, 400)
        direct = self.client.post(f'/api/skill-review/attempts/{assignment.attempt.attempt_id}/submit/',
                                  {'client_submission_id': 'self-only', 'payload': {'passed': True}}, format='json')
        self.assertEqual(direct.status_code, 201, direct.content)
        self.assertEqual(VerificationResult.objects.get().overall_status, 'verification_failed')

    def test_retry_does_not_reexecute_or_duplicate_handoff(self):
        from learning_map.models import VerificationFact
        assignment = self.allocate()
        self.start(assignment)
        first = self.verify(assignment)
        count = VerificationFact.objects.count()
        with patch('practical_training.verifiers.observe_challenge', side_effect=AssertionError('reexecuted')):
            retry = self.client.post(self.url(assignment, 'verify/'), {'key': 'server-test'}, format='json')
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(first.data['evidence_id'], retry.data['evidence_id'])
        self.assertEqual(VerificationFact.objects.count(), count)

    def test_same_key_different_content_rejected(self):
        from practical_training.evidence import persist_evidence
        from practical_training.models import ServerEvidence
        from rest_framework.exceptions import ValidationError
        assignment = self.allocate()
        self.start(assignment)
        self.verify(assignment)
        row = ServerEvidence.objects.get()
        with self.assertRaises(ValidationError):
            persist_evidence(assignment=assignment, attempt=assignment.attempt, key=row.key,
                             request_hash=row.request_hash, source=row.source, observation={'solved': False},
                             version=row.verifier_version, status='failed')
        self.assertEqual(ServerEvidence.objects.count(), 1)

    def test_unsolved_and_fault_are_not_passes(self):
        from practical_training.verifiers import VerifierUnavailable
        from skill_review.models import VerificationResult
        assignment = self.allocate()
        self.start(assignment)
        with patch('practical_training.verifiers.observe_challenge', side_effect=VerifierUnavailable('timeout')):
            response = self.client.post(self.url(assignment, 'verify/'), {'key': 'timeout'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(VerificationResult.objects.get().overall_status, 'verification_failed')
        self.assertEqual(response.data['status'], 'error')

    def test_unsolved_challenge_is_failed(self):
        assignment = self.allocate()
        self.start(assignment)
        response = self.verify(assignment, solved=False)
        self.assertEqual(response.data['status'], 'failed')

    def test_preexisting_solution_cannot_be_attributed_to_new_attempt(self):
        assignment = self.allocate()
        with patch('practical_training.verifiers.observe_challenge', return_value={'solved': True}):
            response = self.client.post(self.url(assignment, 'start/'), {}, format='json')
        self.assertEqual(response.status_code, 400)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.baseline_observed_at)

    def test_cross_student_evidence_and_verification_denied(self):
        assignment = self.allocate()
        self.start(assignment)
        verified = self.verify(assignment)
        self.client.force_authenticate(self.other)
        for suffix in ('start/', 'verify/', 'self-report/'):
            data = {'key': 'cross-user'} if suffix == 'verify/' else {}
            self.assertEqual(self.client.post(self.url(assignment, suffix), data, format='json').status_code, 404)
        self.assertEqual(self.client.get(self.url(assignment, f"evidence/{verified.data['evidence_id']}/")).status_code, 404)

    def test_changed_task_version_denied_before_network(self):
        assignment = self.allocate()
        self.task.version = 'changed'
        self.task.save()
        with patch('practical_training.verifiers.observe_challenge') as network:
            response = self.client.post(self.url(assignment, 'start/'), {}, format='json')
        self.assertEqual(response.status_code, 400)
        network.assert_not_called()


GOOD_POLICY = {'default': 'deny', 'rules': {'public': 'public', 'internal': 'tenant', 'private': 'owner'}}


class RepairTests(TrainingTestCase):
    start = EvidenceTests.start
    verify = EvidenceTests.verify

    def verified_assignment(self):
        assignment = self.allocate()
        self.start(assignment)
        response = self.verify(assignment)
        self.assertEqual(response.status_code, 201)
        return assignment

    def submit_repair(self, assignment, policy=None, key='claim-1'):
        return self.client.post(self.url(assignment, 'repair/'),
                                {'key': key, 'explanation': '服务端读取前须验证身份、租户和资源权限。',
                                 'policy': policy or GOOD_POLICY}, format='json')

    def check_repair(self, assignment, claim_id):
        return self.client.post(self.url(assignment, f'repair/{claim_id}/verify/'), {'key': 'repair-check'}, format='json')

    def test_unreviewed_claim_never_counts_as_completed(self):
        from practical_training.models import RepairClaim
        assignment = self.verified_assignment()
        response = self.submit_repair(assignment)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(response.data['completed'])
        claim = RepairClaim.objects.get()
        self.assertIsNone(claim.evidence_id)
        self.assertIsNone(claim.retest.completed_submission_id)
        self.assertFalse(claim.attempt.verification_results.exists())

    def test_independent_reexecution_delivers_retest_link(self):
        from learning_map.models import VerificationFact
        from practical_training.models import RepairClaim
        assignment = self.verified_assignment()
        claim = self.submit_repair(assignment)
        with patch('practical_training.verifiers.verify_policy', wraps=__import__(
            'practical_training.verifiers', fromlist=['verify_policy']).verify_policy) as runner:
            checked = self.check_repair(assignment, claim.data['claim_id'])
        self.assertEqual(checked.status_code, 201, checked.content)
        runner.assert_called_once_with(GOOD_POLICY)
        claim = RepairClaim.objects.get()
        self.assertTrue(claim.completed)
        self.assertEqual(claim.retest.outcome, 'passed')
        self.assertEqual(claim.retest.started_attempt_id, claim.attempt_id)
        self.assertTrue(VerificationFact.objects.filter(attempt_id=claim.attempt.attempt_id,
                                                        retest_of_attempt_id=assignment.attempt.attempt_id).exists())

    def test_bad_fix_fails_and_deny_all_is_not_a_fix(self):
        from practical_training.verifiers import verify_policy
        for policy in ({'default': 'allow', 'rules': {'public': 'public', 'internal': 'public', 'private': 'public'}},
                       {'default': 'deny', 'rules': {'public': 'deny', 'internal': 'deny', 'private': 'deny'}}):
            self.assertFalse(verify_policy(policy)['passed'])
        assignment = self.verified_assignment()
        submitted = self.submit_repair(assignment, {'default': 'deny', 'rules': {'public': 'deny', 'internal': 'deny', 'private': 'deny'}})
        checked = self.check_repair(assignment, submitted.data['claim_id'])
        self.assertEqual(checked.data['status'], 'failed')
        from practical_training.models import RepairClaim
        self.assertFalse(RepairClaim.objects.get().completed)
        self.assertEqual(RepairClaim.objects.get().retest.outcome, 'failed')

    def test_no_verified_problem_cannot_generate_repair(self):
        assignment = self.allocate()
        self.assertEqual(self.submit_repair(assignment).status_code, 400)

    def test_same_key_changed_claim_and_cross_student_rejected(self):
        assignment = self.verified_assignment()
        claim = self.submit_repair(assignment)
        self.assertEqual(self.submit_repair(assignment).status_code, 200)
        changed = {**GOOD_POLICY, 'default': 'allow'}
        self.assertEqual(self.submit_repair(assignment, changed).status_code, 400)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.submit_repair(assignment).status_code, 404)
        self.assertEqual(self.check_repair(assignment, claim.data['claim_id']).status_code, 404)
        self.assertEqual(self.client.get(self.url(assignment, 'repair/')).status_code, 404)

    def test_repair_result_retry_is_idempotent(self):
        assignment = self.verified_assignment()
        claim = self.submit_repair(assignment)
        checked = self.check_repair(assignment, claim.data['claim_id'])
        with patch('practical_training.verifiers.verify_policy', side_effect=AssertionError('must not rerun')):
            retry = self.check_repair(assignment, claim.data['claim_id'])
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data['evidence_id'], checked.data['evidence_id'])

    def test_arbitrary_code_or_target_not_accepted(self):
        assignment = self.verified_assignment()
        self.assertEqual(self.submit_repair(assignment, {'code': 'print(1)'}).status_code, 400)


class MappingTests(TrainingTestCase):
    def test_claim_records_module_one_binding_scope_and_limits(self):
        assignment = self.allocate()
        self.assertEqual(assignment.attempt.task_id, self.task.pk)
        self.assertEqual(assignment.scope['port'], self.container.port)
        self.assertEqual(assignment.scope['aup_version'], AUP_VERSION)
        self.assertEqual(assignment.policy['egress'], 'deny')
        self.assertLessEqual(assignment.expires_at, self.container.expires_at)
        self.assertEqual(assignment.task_snapshot['capability_ids'], ['M5-TEST'])

    def test_allocation_retry_returns_same_record(self):
        assignment = self.allocate()
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': str(assignment.attempt.attempt_id), 'accepted_aup': AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LabAssignment.objects.count(), 1)

    def test_aup_and_client_supplied_target_rejected(self):
        attempt = self.claim()
        for data in ({'attempt_id': attempt}, {'attempt_id': attempt, 'accepted_aup': 'yes'},
                     {'attempt_id': attempt, 'accepted_aup': AUP_VERSION, 'target': 'http://production/'}):
            response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/', data, format='json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(LabAssignment.objects.count(), 0)

    def test_cross_student_list_read_write_and_attempt_binding_denied(self):
        assignment = self.allocate()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url(assignment)).status_code, 404)
        self.assertEqual(self.client.get('/api/practical-training/assignments/').data, [])
        self.assertEqual(self.client.post(self.url(assignment, 'hints/'), {'level': 1}, format='json').status_code, 404)
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': str(assignment.attempt.attempt_id), 'accepted_aup': AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_unreviewed_mapping_is_not_open(self):
        self.mapping.reviewed_at = None
        self.mapping.save()
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': self.claim(), 'accepted_aup': AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)

    @override_settings(PRACTICAL_TRAINING_ENABLED=False)
    def test_real_lab_closed_by_default(self):
        response = self.client.post(f'/api/practical-training/mappings/{self.mapping.pk}/claim/',
                                    {'attempt_id': self.claim(), 'accepted_aup': AUP_VERSION}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_hints_requested_and_delivered_separately(self):
        from skill_review.models import AssistanceRecord
        assignment = self.allocate()
        response = self.client.post(self.url(assignment, 'hints/'), {'level': 2}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        record = AssistanceRecord.objects.get(record_id=response.data['record_id'])
        self.assertFalse(record.shown)
        displayed = self.client.post(self.url(assignment, f'hints/{record.record_id}/display/'), {}, format='json')
        self.assertEqual(displayed.status_code, 200)
        self.assertIn('content', displayed.data)
        record.refresh_from_db()
        self.assertTrue(record.shown)

    def test_event_failure_rolls_back_allocation(self):
        self.claim()
        with patch('practical_training.services.audit', side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError):
                self.allocate()
        self.assertFalse(LabAssignment.objects.exists())

    def test_seed_is_idempotent_and_does_not_publish(self):
        call_command('seed_practical_training', catalog=self.catalog.version, capability=self.capability.stable_id)
        call_command('seed_practical_training', catalog=self.catalog.version, capability=self.capability.stable_id)
        candidate = TaskPackage.objects.get(task_key='M5-JUICE-DOCUMENT')
        self.assertEqual(candidate.status, 'draft')
        self.assertFalse(candidate.environment_available)
        self.assertEqual(ChallengeMapping.objects.count(), 2)
