from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import patch
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import APIException
from export_risk.models import ExecutionAuthorizationRecord, RiskDecision, DeliveryRecord
from export_quota.models import QuotaReservation
from learning_analytics.models import LearningEvent
from learning_map.models import TaskAttempt, VerificationFact
from skill_review.models import ManualReviewTask, SubmissionSnapshot
from skill_review.services.review import upsert_review_card
from skill_review.services.retest import claim_retest
from data_lab.catalog import TASK_A, TASK_B
from data_lab.common import Conflict, cas_lab
from data_lab.models import LabAttempt, Scan, ReviewLedger
from data_lab.services import start_scan
from data_lab.submissions import submit, deliver, submission_dto
from .base import LabTestCase
from .flows import complete_evidence


class AcceptanceTests(LabTestCase):
    def no_ai_flow(self, failure):
        with ExitStack() as stack:
            sentinels = [stack.enter_context(patch(target, side_effect=failure)) for target in (
                'export_risk.decisions.service.prepare_execution',
                'export_risk.decisions.service.claim', 'export_risk.decisions.service.consume',
                'requests.sessions.Session.request', 'socket.socket.connect',
                'ai_assistant.service.MultiAgentChatService.chat_with_agent',
                'ai_assistant.service.MultiAgentChatService.tutoring_session',
                'legal_kb.services.embedding_service.EmbeddingService.embed_text',
                'legal_kb.services.embedding_service.EmbeddingService.embed_many',
                'legal_kb.services.retrieval_service.LegalRetrievalService.retrieve',
                'mainline1.semantic.run_semantic')]
            claim = self.client.post(f'/api/data-lab/cases/{TASK_A}/claim/',
                                    {'version': self.catalog.version}, format='json')
            self.assertEqual(claim.status_code, 200, claim.data)
            data = complete_evidence(self)
            evidence = submit(self.student, self.lab.attempt.attempt_id, data)
            self.assertEqual(evidence.status, 'delivered', evidence.failure_code)
            self.assertEqual(evidence.module6.results.get().program_status, 'passed')
            card, assignment = upsert_review_card(student=self.student, submission=evidence.module6,
                complete=True, now=timezone.now() - timedelta(days=3), data={
                    'original_task_summary': '合成客户表', 'error_evidence': '原覆盖缺口',
                    'judgment_at_time': '候选不等于确定', 'correct_basis': '业务事实与依据卡',
                    'next_verification': '独立日志场景', 'student_reflection': '补录不改变原召回'})
            self.assertEqual(assignment.selected_task.task_key, TASK_B)
            retest, created = claim_retest(assignment, self.student)
            self.assertTrue(created)
            opened = self.client.post(f'/api/data-lab/attempts/{retest.attempt_id}/', {}, format='json')
            self.assertEqual(opened.status_code, 200, opened.data)
            lab = LabAttempt.objects.get(attempt=retest)
            retest_data = complete_evidence(self, lab)
            second = submit(self.student, retest.attempt_id, retest_data)
            self.assertEqual(second.status, 'delivered')
            result = second.module6.results.get()
            self.assertEqual(result.program_status, 'passed', result.program_result)
            self.assertEqual(result.independence, 'independent')
            self.assertEqual(result.manual_status, 'pending')
            self.assertEqual(result.rubric_version, second.snapshot['versions']['rubric_version'])
            facts = VerificationFact.objects.filter(attempt_id=retest.attempt_id)
            self.assertEqual(facts.count(), 1)
            self.assertEqual(facts.get().retest_of_attempt_id, self.lab.attempt.attempt_id)
            assignment.refresh_from_db()
            self.assertEqual(assignment.completed_submission_id, second.module6_id)
            self.assertEqual(ManualReviewTask.objects.count(), 2)
            for guard in sentinels:
                guard.assert_not_called()
        # Recovery must not replay any worker or overwrite evidence.
        with patch('data_lab.services.run_worker', side_effect=AssertionError('replayed worker')) as worker:
            digest = second.content_digest
            self.assertEqual(deliver(second).content_digest, digest)
            worker.assert_not_called()
        self.assertEqual(SubmissionSnapshot.objects.count(), 2)
        for model in (ExecutionAuthorizationRecord, RiskDecision, DeliveryRecord, QuotaReservation):
            self.assertEqual(model.objects.count(), 0)
        self.assertTrue(all(len(value) <= 64 for value in LearningEvent.objects.values_list('event_id', flat=True)))

    def test_disconnected_full_flow(self):
        self.no_ai_flow(ConnectionError('disconnected'))

    def test_timeout_full_flow(self):
        self.no_ai_flow(TimeoutError('timeout'))

    def test_rate_limit_full_flow(self):
        failure = APIException('429 upstream rate limit')
        failure.status_code = 429
        self.no_ai_flow(failure)

    def test_quota_exhausted_full_flow(self):
        self.no_ai_flow(RuntimeError('model quota exhausted'))

    def test_all_models_disabled_full_flow(self):
        self.no_ai_flow(AssertionError('all generation, embedding, retrieval/ranking disabled'))

    def test_lost_scan_finalization_recovers_without_replaying_same_key(self):
        self.basis()
        original_emit = __import__('data_lab.services', fromlist=['emit']).emit
        def fail_finalization(lab, action, *args, **kwargs):
            if action == 'scan_completed':
                raise IntegrityError('event store unavailable')
            return original_emit(lab, action, *args, **kwargs)
        data = {'fixture_id': 'customer-v1', 'idempotency_key': 'interrupted'}
        with patch('data_lab.services.emit', side_effect=fail_finalization), self.assertRaises(IntegrityError):
            start_scan(self.student, self.lab.attempt.attempt_id, data)
        scan = Scan.objects.get()
        self.assertEqual(scan.status, 'running')
        self.assertEqual(ReviewLedger.objects.count(), 0)
        Scan.objects.filter(pk=scan.pk).update(created_at=timezone.now() - timedelta(seconds=31))
        with patch('data_lab.services.run_worker', side_effect=AssertionError('same-key replay')) as worker:
            recovered = start_scan(self.student, self.lab.attempt.attempt_id, data)
            self.assertEqual(recovered.status, 'failed')
            worker.assert_not_called()
        new = start_scan(self.student, self.lab.attempt.attempt_id, {**data, 'idempotency_key': 'new'})
        self.assertEqual(new.status, 'completed')

    def test_stale_compare_and_swap_loses_no_update(self):
        first = LabAttempt.objects.get(pk=self.lab.pk)
        stale = LabAttempt.objects.get(pk=self.lab.pk)
        cas_lab(first)
        with self.assertRaises(Conflict):
            cas_lab(stale)

    def test_missing_or_corrupt_evidence_is_not_knowledge_failure(self):
        data = complete_evidence(self)
        with patch('skill_review.services.events.emit_event', side_effect=IntegrityError('offline')):
            evidence = submit(self.student, self.lab.attempt.attempt_id, data)
        evidence.snapshot = {}
        evidence.save(update_fields=['snapshot'])
        recovered = deliver(evidence)
        self.assertEqual(recovered.status, 'verification_failed')
        self.assertEqual(SubmissionSnapshot.objects.count(), 0)
        self.assertEqual(VerificationFact.objects.count(), 0)
        self.assertNotEqual(submission_dto(recovered)['program_status'], 'passed')

    def test_withdrawal_prevents_help_replays_and_material_reads(self):
        data = complete_evidence(self)
        response = self.client.post(f'/api/data-lab/attempts/{self.lab.attempt.attempt_id}/help/',
            {'level': 1, 'source': 'card', 'idempotency_key': 'h'}, format='json')
        self.assertEqual(response.status_code, 200)
        case = self.cases[TASK_A]
        case.withdrawn = True
        case.save()
        for url in (f"replays/{data['replay_ids'][0]}/", f'attempts/{self.lab.attempt.attempt_id}/',
                    f'attempts/{self.lab.attempt.attempt_id}/analysis/'):
            response = self.client.get('/api/data-lab/' + url)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response['Cache-Control'], 'no-store, private')
        self.assertEqual(Scan.objects.count(), 1)


class RegistrationTests(TestCase):
    def test_candidate_registration_never_fabricates_signoff(self):
        from io import StringIO
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from learning_map.models import CatalogVersion, Capability, TaskPackage
        from users.models import CTFUser
        from data_lab.models import CasePackage
        teacher = CTFUser.objects.create_user(username='d4-installer', role='teacher')
        catalog = CatalogVersion.objects.create(version='d4-install-test', label='安装测试', status='draft')
        Capability.objects.create(catalog=catalog, stable_id='DS-005', track='data_security', title='测试能力')
        for _ in range(2):
            call_command('register_data_lab', catalog=catalog.version, owner=teacher.pk,
                         capability=['DS-005'], stdout=StringIO())
        cases = CasePackage.objects.filter(task__catalog=catalog)
        self.assertEqual(cases.count(), 2)
        for case in cases:
            self.assertEqual(case.status, 'draft')
            self.assertEqual(case.task.status, 'draft')
            self.assertEqual(case.author_review, {})
            self.assertEqual(case.second_review, {})
            self.assertFalse(case.task.requires_milestone_i)
        other = CatalogVersion.objects.create(version='d4-other-draft', label='其他目录', status='draft')
        Capability.objects.create(catalog=other, stable_id='DS-005', track='data_security', title='其他能力')
        with self.assertRaisesMessage(CommandError, '该任务键/版本已属于其他目录'):
            call_command('register_data_lab', catalog=other.version, owner=teacher.pk,
                         capability=['DS-005'], stdout=StringIO())
        self.assertFalse(TaskPackage.objects.filter(catalog=other).exists())
        self.assertEqual(CasePackage.objects.count(), 2)
        case = cases.get(task__task_key=TASK_A)
        case.author_review = {'actor_id': teacher.pk, 'at': 'test'}
        case.save(update_fields=['author_review'])
        with self.assertRaisesMessage(CommandError, '既有案例已签收或不再是草案'):
            call_command('register_data_lab', catalog=catalog.version, owner=teacher.pk,
                         capability=['DS-005'], stdout=StringIO())
        case.refresh_from_db()
        self.assertEqual(case.author_review, {'actor_id': teacher.pk, 'at': 'test'})
        catalog.status = 'published'
        catalog.save(update_fields=['status'])
        with self.assertRaises(CommandError):
            call_command('register_data_lab', catalog=catalog.version, owner=teacher.pk,
                         capability=['DS-005'], stdout=StringIO())
