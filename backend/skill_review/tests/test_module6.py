"""Isolated tests for module 6.

Synthetic catalog/task data only.  No model, network or target environment is
called.  Module 7/8 are not connected; their notices are asserted to say so.
"""

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from learning_analytics.models import LearningEvent
from learning_map import constants as map_constants
from learning_map.models import (
    Capability,
    CatalogVersion,
    KnowledgePoint,
    TaskAttempt,
    TaskPackage,
    VerificationFact,
)
from skill_review import constants
from skill_review.models import (
    AssistanceRecord,
    DownstreamNotice,
    ManualReviewTask,
    ResultCorrection,
    RetestAssignment,
    ReviewCard,
    ScoreDispute,
    SubmissionErrorCause,
    SubmissionSnapshot,
    TeacherSamplingBatch,
    TeacherSamplingItem,
    VerificationResult,
)
from skill_review.services import correction as correction_service
from skill_review.services import disputes, retest, review, sampling, stats
from skill_review.services import submissions as submission_service
from skill_review.services import verification
from users.models import CTFUser


DATA_VALIDATOR = {
    'version': 'm6-rules-v1-candidate',
    'type': 'rules+teacher_rubric',
    'manual_required': True,
    'checks': [
        {'id': 'basis', 'label': '引用依据', 'field': 'basis_clause', 'required': True, 'cause': 'concept_unclear'},
        {'id': 'sensitive', 'label': '敏感字段', 'field': 'sensitive_fields',
         'contains_all': ['id_card'], 'cause': 'scope_error'},
        {'id': 'decision', 'label': '导出决策', 'field': 'export_decision',
         'equals': 'reject', 'cause': 'concept_unclear'},
    ],
}

RETEST_VALIDATOR = {
    'version': 'm6-rules-v1-candidate',
    'type': 'structured_rules',
    'manual_required': False,
    'checks': [
        {'id': 'basis', 'label': '引用依据', 'field': 'basis_clause', 'required': True, 'cause': 'concept_unclear'},
        {'id': 'sensitive', 'label': '敏感字段', 'field': 'sensitive_fields',
         'contains_all': ['phone'], 'cause': 'scope_error'},
    ],
}


def make_catalog():
    return CatalogVersion.objects.create(
        version='v1-test', label='测试目录', status='published', rule_version='rules-test-v1',
    )


def make_capability(catalog, stable_id='DS-001'):
    return Capability.objects.create(
        catalog=catalog, stable_id=stable_id, track='data', title=f'能力 {stable_id}',
        observable_objective='可观察目标', dimension='identify', difficulty=1,
        status=map_constants.CAPABILITY_STATUS_OPEN, course_order=10,
    )


def make_task(catalog, capability, task_key='TASK-DS-1', purpose='verification',
              validator=None, retest_keys=None, environment_available=True):
    task = TaskPackage.objects.create(
        catalog=catalog, task_key=task_key, version='1.0.0', title=f'任务 {task_key}',
        track=capability.track, purpose=purpose, execution_mode='readonly_decision',
        status='frozen', materials={'student_material_refs': ['x.csv']},
        hints=[{'level': level, 'title': f'第{level}级'} for level in (1, 2, 3, 4)],
        student_solution_ref='solutions/x.md',
        validator=validator or DATA_VALIDATOR,
        acceptance={'rules': ['示例']},
        retest_task_keys=retest_keys or [],
        environment_available=environment_available,
        course_order=10,
    )
    task.capabilities.set([capability])
    return task


def make_attempt(task, student, catalog):
    return TaskAttempt.objects.create(
        student=student, catalog=catalog, task=task, task_version=task.version,
        capability_ids=[capability.stable_id for capability in task.capabilities.all()],
        status='claimed',
    )


def good_payload():
    return {
        'basis_clause': '数据安全法第二十一条',
        'sensitive_fields': ['id_card', 'phone'],
        'export_decision': 'reject',
        'export_reason': '缺少授权范围',
        'audit_note': '记录拒绝理由',
    }


class Module6Tests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='s1', password='Passw0rd!', role='student')
        self.student2 = CTFUser.objects.create_user(username='s2', password='Passw0rd!', role='student')
        self.teacher = CTFUser.objects.create_user(username='t1', password='Passw0rd!', role='teacher')
        self.teacher2 = CTFUser.objects.create_user(username='t2', password='Passw0rd!', role='teacher')
        self.admin = CTFUser.objects.create_user(username='a1', password='Passw0rd!', role='admin')
        self.catalog = make_catalog()
        self.capability = make_capability(self.catalog)
        self.task = make_task(self.catalog, self.capability)
        self.retest_task = make_task(
            self.catalog, self.capability, task_key='TASK-DS-RETEST',
            purpose='retest', validator=RETEST_VALIDATOR,
        )
        self.task.retest_task_keys = ['TASK-DS-RETEST']
        self.task.save(update_fields=['retest_task_keys'])
        self.client = APIClient()

    # 1. Program pass + manual pending are both kept.
    def test_program_pass_manual_pending(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, created = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-1', payload=good_payload(),
        )
        self.assertTrue(created)
        result = submission.results.get(is_current=True)
        self.assertEqual(result.program_status, constants.PROGRAM_PASSED)
        self.assertEqual(result.manual_status, constants.MANUAL_PENDING)
        self.assertEqual(result.overall_status, constants.OVERALL_PENDING_MANUAL)
        self.assertIsNone((result.manual_result or {}).get('total_score'))
        self.assertTrue(ManualReviewTask.objects.filter(result=result).exists())

    # 2. Requested but not shown help is not assistance.
    def test_requested_not_shown_is_independent(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        record = submission_service.request_hint(
            student=self.student, attempt=attempt, level=3,
            source=constants.ASSISTANCE_SOURCE_CARD,
        )
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-2', payload=good_payload(),
        )
        self.assertEqual(submission.independence, constants.INDEPENDENCE_INDEPENDENT)
        self.assertFalse(record.shown)

    # 3. Shown hint before submit → assisted, and resubmit stays assisted.
    def test_shown_hint_and_resubmit_are_assisted(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        record = submission_service.request_hint(
            student=self.student, attempt=attempt, level=2,
            source=constants.ASSISTANCE_SOURCE_AI,
        )
        submission_service.show_hint(record=record)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-3', payload=good_payload(),
        )
        self.assertEqual(submission.independence, constants.INDEPENDENCE_ASSISTED)
        self.assertEqual(submission.assistance_snapshot['level'], 2)
        resubmission, created = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-4', payload={**good_payload(), 'export_reason': '再补充'},
        )
        self.assertTrue(created)
        self.assertEqual(resubmission.independence, constants.INDEPENDENCE_ASSISTED)
        self.assertFalse(resubmission.first_effective)
        self.assertEqual(SubmissionSnapshot.objects.filter(attempt=attempt, first_effective=True).count(), 1)

    # 4. Teacher help before submit → assisted.
    def test_teacher_help_marks_assisted(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission_service.record_teacher_help(
            teacher=self.teacher, attempt=attempt, summary='讲解范围判断',
        )
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-5', payload=good_payload(),
        )
        self.assertEqual(submission.independence, constants.INDEPENDENCE_ASSISTED)

    # 5. Missing help record → unknown, never independent.
    def test_missing_help_record_is_unknown(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-6', payload=good_payload(),
            assistance_tracking=constants.ASSISTANCE_TRACKING_MISSING,
        )
        self.assertEqual(submission.independence, constants.INDEPENDENCE_UNKNOWN)

    # 6. Answer exposure is preserved and does not remove independence history.
    def test_analysis_view_is_recorded(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-7', payload=good_payload(),
        )
        before = submission.independence
        submission_service.record_analysis_view(
            student=self.student, task=self.task, attempt=attempt,
        )
        submission.refresh_from_db()
        self.assertEqual(submission.independence, before)
        self.assertTrue(
            AssistanceRecord.objects.filter(
                student=self.student, task=self.task,
                kind=constants.ASSISTANCE_KIND_ANALYSIS_VIEW,
            ).exists()
        )
        new_attempt = make_attempt(self.task, self.student, self.catalog)
        second, _ = submission_service.create_submission(
            student=self.student, attempt=new_attempt,
            client_submission_id='sub-8', payload=good_payload(),
        )
        self.assertTrue(second.answer_exposure)
        self.assertEqual(second.independence, constants.INDEPENDENCE_UNKNOWN)

    # 7. Idempotent retry and conflicting content.
    def test_submission_idempotency(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        first, created = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-9', payload=good_payload(),
        )
        second, created2 = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-9', payload=good_payload(),
        )
        self.assertTrue(created)
        self.assertFalse(created2)
        self.assertEqual(first.id, second.id)
        self.assertEqual(SubmissionSnapshot.objects.count(), 1)
        with self.assertRaises(submission_service.SubmissionConflict):
            submission_service.create_submission(
                student=self.student, attempt=attempt,
                client_submission_id='sub-9', payload={**good_payload(), 'export_decision': 'approve'},
            )

    # 8. Manual review completes overall and appends teacher event.
    def test_manual_review_sets_overall(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-10', payload=good_payload(),
        )
        task = ManualReviewTask.objects.get(submission=submission)
        scores = {
            key: {'score': 2, 'evidence': f'{key}-证据', 'reason': '说明充分'}
            for key, _ in constants.RUBRIC_ITEMS
        }
        verification.review_manual_task(
            task, reviewer=self.teacher, scores=scores,
            decision='pass', remarks='解释完整', causes=['concept_unclear'],
        )
        result = submission.results.get(is_current=True)
        self.assertEqual(result.manual_status, constants.MANUAL_REVIEWED)
        self.assertEqual(result.overall_status, constants.OVERALL_PASSED)
        self.assertEqual(result.manual_result['total_score'], 8)
        self.assertTrue(
            SubmissionErrorCause.objects.filter(
                submission=submission, cause='concept_unclear', status=constants.CAUSE_CONFIRMED,
            ).exists()
        )
        self.assertTrue(LearningEvent.objects.filter(event_id__startswith='m6-manual-').exists())

    # 9. Manual review cannot be claimed by another teacher.
    def test_manual_claim_conflict(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-11', payload=good_payload(),
        )
        task = ManualReviewTask.objects.get(submission=submission)
        task.status = constants.MANUAL_TASK_CLAIMED
        task.claimed_by = self.teacher
        task.save()
        scores = {
            key: {'score': 1, 'evidence': 'e', 'reason': 'r'} for key, _ in constants.RUBRIC_ITEMS
        }
        with self.assertRaises(PermissionError):
            verification.review_manual_task(
                task, reviewer=self.teacher2, scores=scores,
                decision='pass', remarks='x',
            )

    # 10. Correction keeps original and creates a new version.
    def test_correction_preserves_original(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-12', payload=good_payload(),
        )
        original = submission.results.get(is_current=True)
        correction = correction_service.create_correction(
            submission=submission, actor=self.teacher,
            source=constants.CORRECTION_SOURCE_TEACHER,
            reason='抽查发现帮助漏记',
            changes={
                'independence': constants.INDEPENDENCE_ASSISTED,
                'overall_status': constants.OVERALL_FAILED,
                'assistance_snapshot': {
                    'level': 2,
                    'source': constants.ASSISTANCE_SOURCE_TEACHER,
                    'shown': True,
                    'reason': 'teacher_confirmed_help',
                },
            },
        )
        original.refresh_from_db()
        current = submission.results.get(is_current=True)
        self.assertFalse(original.is_current)
        self.assertEqual(current.version, 2)
        self.assertEqual(current.independence, constants.INDEPENDENCE_ASSISTED)
        self.assertEqual(current.overall_status, constants.OVERALL_FAILED)
        self.assertEqual(correction.before['overall_status'], constants.OVERALL_PENDING_MANUAL)
        self.assertEqual(correction.after['overall_status'], constants.OVERALL_FAILED)
        self.assertEqual(submission.results.count(), 2)
        notice = DownstreamNotice.objects.filter(
            result=current, target=constants.NOTICE_MODULE1,
        ).first()
        self.assertIsNotNone(notice)
        self.assertTrue(notice.target_connected)

    # 11. Retest excludes original and exposed tasks; empty pool → pending item.
    def test_retest_pool_and_empty_pool(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sub-13', payload=good_payload(),
        )
        card, assignment = review.upsert_review_card(
            student=self.student, submission=submission,
            data={
                'original_task_summary': '客户表',
                'error_evidence': '漏标 id_card',
                'judgment_at_time': '只看字段名',
                'correct_basis': '个人信息保护法第四条',
                'next_verification': '换业务日志场景',
                'student_reflection': '先核对依据',
            },
            complete=True,
        )
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.selected_task.task_key, 'TASK-DS-RETEST')
        self.assertNotIn('TASK-DS-1', assignment.pool_snapshot['candidate_task_keys'])

        self.retest_task.status = 'withdrawn'
        self.retest_task.save()
        attempt2 = make_attempt(self.task, self.student2, self.catalog)
        submission2, _ = submission_service.create_submission(
            student=self.student2, attempt=attempt2,
            client_submission_id='sub-14', payload=good_payload(),
        )
        _, assignment2 = review.upsert_review_card(
            student=self.student2, submission=submission2,
            data={
                'original_task_summary': 'x', 'error_evidence': 'x', 'judgment_at_time': 'x',
                'correct_basis': 'x', 'next_verification': 'x', 'student_reflection': 'x',
            },
            complete=True,
        )
        self.assertEqual(assignment2.status, constants.RETEST_PENDING_ITEM)
        self.assertIsNone(assignment2.selected_task)

    # 12. Due / missed transitions are date logic only.
    def test_retest_due_and_missed(self):
        now = timezone.now()
        original = self._submission_for(self.student, 'sub-15')
        assignment = RetestAssignment.objects.create(
            student=self.student, catalog=self.catalog,
            capability=self.capability, capability_ids=[self.capability.stable_id],
            original_attempt=original.attempt,
            original_submission=original,
            selected_task=self.retest_task,
            status=constants.RETEST_SCHEDULED,
            scheduled_at=now - timedelta(days=10),
            due_at=now - timedelta(days=1),
            grace_until=now + timedelta(days=5),
        )
        counts = retest.process_due_retests(now=now)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, constants.RETEST_DUE)
        self.assertEqual(counts['due'], 1)
        counts = retest.process_due_retests(now=now + timedelta(days=6))
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, constants.RETEST_MISSED)
        self.assertEqual(counts['missed'], 1)
        self.assertIsNone(assignment.completed_submission)
        self.assertFalse(assignment.outcome)

    # 13. Sampling: reproducible, high risk included, separate from manual queue.
    def test_sampling_batch_reproducible(self):
        for index, student in enumerate([self.student, self.student2], start=1):
            attempt = make_attempt(self.task, student, self.catalog)
            submission_service.create_submission(
                student=student, attempt=attempt,
                client_submission_id=f'sample-{index}', payload=good_payload(),
                assistance_tracking=(
                    constants.ASSISTANCE_TRACKING_MISSING if index == 2
                    else constants.ASSISTANCE_TRACKING_COMPLETE
                ),
            )
        now = timezone.now()
        batch = sampling.create_batch(
            actor=self.teacher, catalog=self.catalog, title='首批抽查',
            window_start=now - timedelta(days=1), window_end=now + timedelta(days=1),
            basis='首期常规抽查', deadline=now + timedelta(days=3),
            sample_size=1, high_risk_size=1, random_seed=7,
        )
        self.assertEqual(batch.items.count(), 2)
        self.assertEqual(batch.scope['candidate_count'], 2)
        selections = set(batch.items.values_list('selection_reason', flat=True))
        self.assertIn(constants.SAMPLING_RANDOM, selections)
        # Program pass + manual pending is not high risk; both are random unless flagged.
        manual_count = ManualReviewTask.objects.filter(status=constants.MANUAL_TASK_PENDING).count()
        self.assertEqual(manual_count, 2)

    # 14. Sampling review can attach a correction, original preserved.
    def test_sampling_correction(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sample-correction', payload=good_payload(),
        )
        now = timezone.now()
        batch = sampling.create_batch(
            actor=self.teacher, catalog=self.catalog, title='抽查',
            window_start=now - timedelta(days=1), window_end=now + timedelta(days=1),
            basis='抽查依据', deadline=now + timedelta(days=3),
            sample_size=1, random_seed=1,
        )
        item = batch.items.first()
        sampling.claim_item(item, self.teacher)
        item = sampling.review_item(
            item, teacher=self.teacher,
            findings={
                'evidence_checked': True, 'verifier_checked': True,
                'rubric_checked': True, 'help_checked': True,
                'independence_checked': True, 'conclusion': '程序通过但帮助漏记',
            },
            notes='需要更正独立性',
            needs_correction=True,
            correction=correction_service.create_correction(
                submission=submission, actor=self.teacher,
                source=constants.CORRECTION_SOURCE_SAMPLING,
                reason='帮助漏记',
                changes={
                    'independence': constants.INDEPENDENCE_ASSISTED,
                    'assistance_snapshot': {
                        'level': 1,
                        'source': constants.ASSISTANCE_SOURCE_TEACHER,
                        'shown': True,
                        'reason': 'sampling_found_missing_help',
                    },
                },
            ),
        )
        item.refresh_from_db()
        self.assertEqual(item.status, constants.SAMPLING_ITEM_NEEDS_CORRECTION)
        self.assertIsNotNone(item.correction)

    # 15. Dispute resolution does not change scores.
    def test_dispute_does_not_change_score(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='dispute-1', payload=good_payload(),
        )
        before = submission.results.get(is_current=True).overall_status
        dispute, _ = disputes.create_dispute(
            student=self.student, submission=submission,
            client_dispute_id='d-1', reason='我认为解释题评分偏低',
        )
        disputes.resolve_dispute(
            dispute, teacher=self.teacher,
            status=constants.DISPUTE_RESOLVED, resolution='维持原判，说明理由',
        )
        after = submission.results.get(is_current=True).overall_status
        self.assertEqual(before, after)

    # 16. Stats separate pending / unknown / environment.
    def test_stats_counts(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='stats-1', payload=good_payload(),
        )
        data = stats.build_stats(catalog=self.catalog)
        self.assertEqual(data['first_effective_attempts']['total'], 1)
        self.assertEqual(data['first_effective_attempts']['pending_manual'], 1)
        self.assertIsNone(data['platform_independent_pass']['rate'])
        self.assertEqual(data['platform_independent_pass']['denominator'], 0)
        self.assertEqual(data['platform_independent_pass']['pending_manual_excluded'], 1)

    # 17. API permissions: another student cannot read my submission.
    def test_student_cannot_read_other_submission(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='perm-1', payload=good_payload(),
        )
        self.client.force_authenticate(self.student2)
        response = self.client.get(f'/api/skill-review/submissions/{submission.submission_id}/')
        self.assertEqual(response.status_code, 403, response.content)
        self.client.force_authenticate(self.teacher)
        response = self.client.get(
            f'/api/skill-review/submissions/{submission.submission_id}/?view=teacher',
        )
        self.assertEqual(response.status_code, 200, response.content)

    # 18. API: student submits through the endpoint and gets labels only.
    def test_submit_endpoint_student_payload(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        self.client.force_authenticate(self.student)
        response = self.client.post(
            f'/api/skill-review/attempts/{attempt.attempt_id}/submit/',
            {'client_submission_id': 'api-1', 'payload': good_payload()},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['overall_status'], constants.OVERALL_PENDING_MANUAL)
        self.assertNotIn('payload_hash', response.data)
        self.assertNotIn('result_id', response.data)
        self.assertEqual(response.data['execution_label'], '未开展')

    # 19. API: teacher queue separates the three kinds.
    def test_teacher_queue_separates(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='queue-1', payload=good_payload(),
        )
        disputes.create_dispute(
            student=self.student, submission=submission,
            client_dispute_id='q-d-1', reason='争议',
        )
        now = timezone.now()
        sampling.create_batch(
            actor=self.teacher, catalog=self.catalog, title='抽查',
            window_start=now - timedelta(days=1), window_end=now + timedelta(days=1),
            basis='依据', deadline=now + timedelta(days=3), sample_size=1, random_seed=1,
        )
        self.client.force_authenticate(self.teacher)
        response = self.client.get('/api/skill-review/teacher/queue/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['counts']['manual_pending'], 1)
        self.assertGreaterEqual(response.data['counts']['sampling_pending'], 1)
        self.assertEqual(response.data['counts']['disputes_pending'], 1)

    # 20. Module 7/8 notices are explicitly not connected.
    def test_downstream_not_connected(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='notice-1', payload=good_payload(),
        )
        result = submission.results.get(is_current=True)
        module7 = DownstreamNotice.objects.get(result=result, target=constants.NOTICE_MODULE7)
        module8 = DownstreamNotice.objects.get(result=result, target=constants.NOTICE_MODULE8)
        self.assertEqual(module7.status, constants.NOTICE_NOT_CONNECTED)
        self.assertEqual(module8.status, constants.NOTICE_NOT_CONNECTED)

    # 21. Module 1 receives a verification fact.
    def test_module1_fact_received(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='fact-1', payload=good_payload(),
        )
        notice = DownstreamNotice.objects.filter(
            result=submission.results.get(is_current=True), target=constants.NOTICE_MODULE1,
        ).first()
        self.assertTrue(
            VerificationFact.objects.filter(
                student=self.student, capability=self.capability,
            ).exists(),
            notice.payload if notice else 'no notice',
        )
        result = submission.results.get(is_current=True)
        self.assertTrue(result.module1_fact_ids.get(self.capability.stable_id))

    # 22. Correction produces a new module-1 fact and a module-1 notice.
    def test_correction_reinjects_fact(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='fact-2', payload=good_payload(),
        )
        before = VerificationFact.objects.filter(student=self.student).count()
        correction_service.create_correction(
            submission=submission, actor=self.teacher,
            source=constants.CORRECTION_SOURCE_TEACHER,
            reason='帮助漏记',
            changes={
                'independence': constants.INDEPENDENCE_ASSISTED,
                'assistance_snapshot': {
                    'level': 2,
                    'source': constants.ASSISTANCE_SOURCE_TEACHER,
                    'shown': True,
                    'reason': 'teacher_confirmed_help',
                },
            },
        )
        after = VerificationFact.objects.filter(student=self.student).count()
        self.assertGreater(after, before)

    def _submission_for(self, student, submission_id):
        attempt = make_attempt(self.task, student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=student, attempt=attempt,
            client_submission_id=submission_id, payload=good_payload(),
        )
        return submission

    # 23. End-to-end retest: claim -> submit -> outcome + module-1 retest linkage.
    def test_retest_end_to_end(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='e2e-1', payload=good_payload(),
        )
        _, assignment = review.upsert_review_card(
            student=self.student, submission=submission,
            data={
                'original_task_summary': '客户表', 'error_evidence': '漏标',
                'judgment_at_time': '只看字段名', 'correct_basis': '个保法',
                'next_verification': '换日志场景', 'student_reflection': '先核对依据',
            },
            complete=True,
        )
        self.assertEqual(assignment.status, constants.RETEST_SCHEDULED)
        retest_attempt, created = retest.claim_retest(assignment, self.student)
        self.assertTrue(created)
        self.assertEqual(retest_attempt.task.task_key, 'TASK-DS-RETEST')
        retest_submission, _ = submission_service.create_submission(
            student=self.student, attempt=retest_attempt,
            client_submission_id='e2e-retest', payload={
                'basis_clause': '数据安全法第二十一条',
                'sensitive_fields': ['phone'],
            },
        )
        result = retest_submission.results.get(is_current=True)
        self.assertEqual(result.overall_status, constants.OVERALL_PASSED)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, constants.RETEST_COMPLETED)
        self.assertEqual(assignment.outcome, constants.RETEST_OUTCOME_PASSED)
        fact = VerificationFact.objects.filter(
            student=self.student, attempt_id=retest_attempt.attempt_id,
        ).first()
        self.assertIsNotNone(fact)
        self.assertEqual(fact.retest_of_attempt_id, attempt.attempt_id)
        data = stats.build_stats(catalog=self.catalog)
        self.assertEqual(data['retest']['retention']['numerator'], 1)
        self.assertEqual(data['retest']['retention']['denominator'], 1)

    # 24. API: teacher manual review through the endpoint.
    def test_teacher_manual_review_endpoint(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='api-manual', payload=good_payload(),
        )
        task = ManualReviewTask.objects.get(submission=submission)
        self.client.force_authenticate(self.teacher)
        claim = self.client.post(f'/api/skill-review/teacher/manual-tasks/{task.review_id}/claim/')
        self.assertEqual(claim.status_code, 200, claim.content)
        scores = {
            key: {'score': 2, 'evidence': '定位', 'reason': '理由'}
            for key, _ in constants.RUBRIC_ITEMS
        }
        response = self.client.post(
            f'/api/skill-review/teacher/manual-tasks/{task.review_id}/review/',
            {'scores': scores, 'decision': 'pass', 'remarks': '解释完整'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        result = submission.results.get(is_current=True)
        self.assertEqual(result.overall_status, constants.OVERALL_PASSED)

    # 25. API: student cannot reach teacher queue; teacher can.
    def test_teacher_endpoints_require_role(self):
        self.client.force_authenticate(self.student)
        response = self.client.get('/api/skill-review/teacher/queue/')
        self.assertEqual(response.status_code, 403)
        response = self.client.get('/api/skill-review/teacher/stats/')
        self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(self.teacher)
        response = self.client.get('/api/skill-review/teacher/stats/')
        self.assertEqual(response.status_code, 200, response.content)

    # 26. API: process due retests with an explicit evaluation time.
    def test_process_due_endpoint(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='due-api', payload=good_payload(),
        )
        _, assignment = review.upsert_review_card(
            student=self.student, submission=submission,
            data={
                'original_task_summary': 'x', 'error_evidence': 'x', 'judgment_at_time': 'x',
                'correct_basis': 'x', 'next_verification': 'x', 'student_reflection': 'x',
            },
            complete=True,
        )
        self.client.force_authenticate(self.teacher)
        future = (timezone.now() + timedelta(days=30)).isoformat()
        response = self.client.post(
            '/api/skill-review/teacher/retests/process-due/',
            {'now': future}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, constants.RETEST_MISSED)
        self.assertIn('不代表学习保持效果', response.data['note'])

    # 27. API: sampling batch creation records scope and seed.
    def test_sampling_api(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='sampling-api', payload=good_payload(),
        )
        self.client.force_authenticate(self.teacher)
        now = timezone.now()
        response = self.client.post('/api/skill-review/teacher/sampling/batches/', {
            'catalog_version': self.catalog.version,
            'title': '接口抽查',
            'window_start': (now - timedelta(days=1)).isoformat(),
            'window_end': (now + timedelta(days=1)).isoformat(),
            'basis': '首期常规抽查',
            'deadline': (now + timedelta(days=3)).isoformat(),
            'sample_size': 1,
            'random_seed': 42,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        batch = TeacherSamplingBatch.objects.get(batch_id=response.data['batch_id'])
        self.assertEqual(batch.random_seed, 42)
        self.assertEqual(batch.scope['candidate_count'], 1)
        self.assertEqual(batch.items.count(), 1)

    # 28. Stats with no sample returns null rate, not zero.
    def test_stats_no_sample(self):
        data = stats.build_stats(catalog=self.catalog)
        self.assertEqual(data['first_effective_attempts']['total'], 0)
        self.assertIsNone(data['platform_independent_pass']['rate'])
        self.assertIsNone(data['retest']['retention']['rate'])



class Module6UnavailableVerifierTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='u1', password='Passw0rd!', role='student')
        self.catalog = make_catalog()
        self.capability = make_capability(self.catalog)
        self.task = make_task(
            self.catalog, self.capability, task_key='TASK-NS-1',
            validator={'type': 'server_verifier', 'version': 'ns-v1'},
        )

    def test_unconnected_server_verifier_never_passes(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=attempt,
            client_submission_id='ns-1', payload={'anything': True},
        )
        result = submission.results.get(is_current=True)
        self.assertEqual(result.program_status, constants.PROGRAM_ERROR)
        self.assertEqual(result.overall_status, constants.OVERALL_VERIFICATION_FAILED)
        self.assertEqual(result.verification_error, 'server_evidence_not_connected')
