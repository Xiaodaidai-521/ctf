from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase
from rest_framework.test import APIClient

from evaluation_center.models import NonFormalAccount, ProjectionReceipt, TeacherTodo, TodoAction
from evaluation_center.operations import (
    OperationsError, change_todo, consume_notices, create_todo, sync_todos, todo_payload,
)
from learning_analytics.models import LearningAdjustmentProposal
from skill_review.models import DownstreamNotice, ScoreDispute, TeacherSamplingBatch, TeacherSamplingItem
from skill_review.services import correction, retest, submissions
from skill_review.tests.test_module6 import (
    DATA_VALIDATOR, RETEST_VALIDATOR, good_payload, make_attempt, make_capability, make_catalog, make_task,
)
from teaching_agent.models import TeacherTicket, TeachingRun
from users.models import CTFUser


class OperationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = CTFUser.objects.create_user(username='op-teacher', role='teacher')
        cls.other = CTFUser.objects.create_user(username='op-other', role='teacher')
        cls.student = CTFUser.objects.create_user(username='op-student', role='student')
        cls.student2 = CTFUser.objects.create_user(username='op-student2', role='student')
        cls.admin = CTFUser.objects.create_user(username='op-admin', role='admin')
        cls.catalog = make_catalog()
        cls.capability = make_capability(cls.catalog)
        cls.task = make_task(cls.catalog, cls.capability, validator=RETEST_VALIDATOR, retest_keys=['NEW-SCENE'])
        cls.new_task = make_task(cls.catalog, cls.capability, task_key='NEW-SCENE', purpose='retest', validator=RETEST_VALIDATOR)
        cls.attempt = make_attempt(cls.task, cls.student, cls.catalog)
        cls.submission, _ = submissions.create_submission(student=cls.student, attempt=cls.attempt,
                                                          client_submission_id='op-original', payload=good_payload())

    def make_todo(self):
        return create_todo(actor=self.teacher, attempt=self.attempt)

    def change(self, todo, action, **kwargs):
        return change_todo(todo.todo_id, actor=kwargs.pop('actor', self.teacher), revision=todo.revision, action=action, **kwargs)

    def handled(self):
        todo = self.change(self.make_todo(), 'claim')
        return self.change(todo, 'handle', summary='安排新场景无提示复测')

    def retested(self, todo):
        assignment, _ = retest.schedule_retest(self.submission, actor=self.teacher)
        attempt, _ = retest.claim_retest(assignment, self.student)
        submission, _ = submissions.create_submission(student=self.student, attempt=attempt,
                                                       client_submission_id='op-retest', payload=good_payload())
        assignment.refresh_from_db()
        return self.change(todo, 'verify', retest_id=assignment.assignment_id), assignment, submission

    def test_claim_revision_conflict(self):
        todo = self.make_todo()
        changed = self.change(todo, 'claim')
        self.assertEqual(changed.revision, 2)
        with self.assertRaises(OperationsError) as raised:
            change_todo(todo.todo_id, actor=self.other, revision=1, action='claim')
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(changed.actions.count(), 2)

    def test_transfer_history_and_ownership(self):
        todo = self.change(self.make_todo(), 'claim')
        with self.assertRaises(OperationsError):
            self.change(todo, 'handle', actor=self.other, summary='not mine')
        todo = self.change(todo, 'transfer', assignee_id=self.other.pk, summary='转课程负责人')
        payload = todo_payload(todo)
        self.assertEqual(payload['owner_id'], self.other.pk)
        self.assertEqual(payload['actions'][-1]['old_owner_id'], self.teacher.pk)
        self.assertEqual(payload['actions'][-1]['new_owner_id'], self.other.pk)
        with self.assertRaises(OperationsError):
            self.change(todo, 'handle', summary='old owner')

    def test_transfer_to_student_denied(self):
        todo = self.change(self.make_todo(), 'claim')
        with self.assertRaises(OperationsError):
            self.change(todo, 'transfer', assignee_id=self.student.pk, summary='invalid')

    def test_no_evidence_cannot_click_improved(self):
        todo = self.handled()
        todo = self.change(todo, 'verify')
        self.assertEqual(todo.status, 'pending_verification')
        self.assertFalse(todo.proof['verified'])

    def test_real_new_scenario_retest_verifies(self):
        todo, assignment, submission = self.retested(self.handled())
        self.assertEqual(todo.status, 'verified')
        self.assertEqual(todo.proof['retest']['current_result']['result_id'], str(submission.results.get(is_current=True).result_id))

    def test_retest_before_intervention_does_not_prove_effect(self):
        todo = self.handled()
        todo, assignment, _ = self.retested(todo)
        todo = self.change(todo, 'handle', summary='另一次干预，必须重新验证')
        todo = self.change(todo, 'verify')
        self.assertEqual(todo.status, 'pending_verification')
        self.assertFalse(todo.proof['after_intervention'])

    def test_unrelated_retest_denied(self):
        attempt = make_attempt(self.task, self.student2, self.catalog)
        other, _ = submissions.create_submission(student=self.student2, attempt=attempt, client_submission_id='other', payload=good_payload())
        assignment, _ = retest.schedule_retest(other, actor=self.teacher)
        with self.assertRaises(OperationsError):
            self.change(self.handled(), 'verify', retest_id=assignment.assignment_id)

    def test_proposal_author_and_student_binding(self):
        proposal = LearningAdjustmentProposal.objects.create(teacher=self.other, student=self.student, title='提案')
        with self.assertRaises(OperationsError):
            create_todo(actor=self.teacher, attempt=self.attempt, proposal=proposal)
        todo = create_todo(actor=self.other, attempt=self.attempt, proposal=proposal)
        self.assertEqual(todo.proposal_id, proposal.pk)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, 'draft')

    def test_student_and_demo_cannot_create_todo(self):
        with self.assertRaises(OperationsError):
            create_todo(actor=self.student, attempt=self.attempt)
        NonFormalAccount.objects.create(student=self.student, source='demo')
        with self.assertRaises(OperationsError):
            self.make_todo()

    def test_audit_failure_rolls_back_claim(self):
        todo = self.make_todo()
        with patch('evaluation_center.operations.TodoAction.objects.create', side_effect=DatabaseError('save failed')):
            with self.assertRaises(DatabaseError):
                self.change(todo, 'claim')
        todo.refresh_from_db()
        self.assertEqual(todo.revision, 1)
        self.assertIsNone(todo.owner_id)
        todo = self.change(todo, 'claim')
        self.assertEqual(todo.revision, 2)
        self.assertEqual(TodoAction.objects.filter(todo=todo).count(), 2)

    def test_queues_separate_idempotent_with_sampling_metadata(self):
        open_task = make_task(self.catalog, self.capability, task_key='OPEN', validator=DATA_VALIDATOR)
        attempt = make_attempt(open_task, self.student, self.catalog)
        submission, _ = submissions.create_submission(student=self.student, attempt=attempt, client_submission_id='open', payload=good_payload())
        run = TeachingRun.objects.create(student=self.student, attempt=attempt, mode='data_security', task_version='1.0.0', catalog_version=self.catalog.version)
        TeacherTicket.objects.create(run=run, attempt=attempt, student=self.student)
        ScoreDispute.objects.create(student=self.student, submission=submission, client_dispute_id='d', reason='复核', result=submission.results.get(is_current=True))
        batch = TeacherSamplingBatch.objects.create(title='抽查', catalog=self.catalog, window_start=submission.created_at,
                                                    window_end=submission.created_at, deadline=submission.created_at,
                                                    sample_size=1, basis='事前随机', created_by=self.teacher)
        sample = TeacherSamplingItem.objects.create(batch=batch, submission=submission, selection_reason='random', status='needs_correction')
        items = sync_todos(actor=self.teacher)
        self.assertEqual({item.kind for item in items}, {'help', 'manual_review', 'sampling', 'dispute'})
        again = sync_todos(actor=self.teacher)
        self.assertEqual({item.pk for item in items}, {item.pk for item in again})
        self.assertEqual(TeacherTodo.objects.count(), 4)
        sampled = next(item for item in items if item.kind == 'sampling')
        self.assertEqual(sampled.source_snapshot['sample_size'], 1)
        self.assertEqual(sampled.source_snapshot['source_status'], 'needs_correction')
        sample.status = 'completed'
        sample.save(update_fields=['status'])
        self.assertEqual(todo_payload(sampled)['source_current_status'], 'completed')
        self.assertEqual(sampled.source_snapshot['source_status'], 'needs_correction')

    def test_correction_receipt_reopens_retest_and_preserves_original(self):
        todo, assignment, submission = self.retested(self.handled())
        original_id = todo.original_result_id
        consume_notices(actor=self.teacher)
        fixed = correction.create_correction(submission=submission, actor=self.teacher, source='teacher_review',
                                              reason='复核未通过', changes={'overall_status': 'failed'})
        consume_notices(actor=self.teacher)
        todo.refresh_from_db()
        self.assertEqual(todo.status, 'pending_verification')
        self.assertEqual(todo.original_result_id, original_id)
        receipt = ProjectionReceipt.objects.get(payload__correction_id=str(fixed.correction_id))
        self.assertEqual(receipt.payload['original_result_id'], str(fixed.original_result.result_id))
        self.assertEqual(receipt.payload['current_result_id'], str(fixed.corrected_result.result_id))
        count = ProjectionReceipt.objects.count()
        revision = todo.revision
        consume_notices(actor=self.teacher)
        todo.refresh_from_db()
        self.assertEqual(ProjectionReceipt.objects.count(), count)
        self.assertEqual(todo.revision, revision)
        self.assertTrue(all(row['student_id'] == self.student.pk for row in receipt.payload['projections']))

    def test_late_notice_uses_current_version_not_old_outcome(self):
        fixed = correction.create_correction(submission=self.submission, actor=self.teacher, source='teacher_review', reason='复核', changes={'overall_status': 'failed'})
        receipts = consume_notices(actor=self.teacher)
        self.assertTrue(receipts)
        self.assertTrue(all(row.payload['current_result_id'] == str(fixed.corrected_result.result_id) for row in receipts))

    def test_receipt_failure_rolls_back_reopening_and_sources_unchanged(self):
        todo, assignment, submission = self.retested(self.handled())
        consume_notices(actor=self.teacher)
        correction.create_correction(submission=submission, actor=self.teacher, source='teacher_review', reason='复核', changes={'overall_status': 'failed'})
        notices = list(DownstreamNotice.objects.values())
        before = ProjectionReceipt.objects.count()
        with patch('evaluation_center.operations.ProjectionReceipt.objects.create', side_effect=DatabaseError('save failed')):
            with self.assertRaises(DatabaseError):
                consume_notices(actor=self.teacher)
        todo.refresh_from_db()
        self.assertEqual(todo.status, 'verified')
        self.assertEqual(todo_payload(todo)['status'], 'pending_verification')
        self.assertEqual(ProjectionReceipt.objects.count(), before)
        consume_notices(actor=self.teacher)
        self.assertEqual(list(DownstreamNotice.objects.values()), notices)

    def test_http_create_sync_and_nonformal_receipt_exclusion(self):
        client = APIClient()
        client.force_authenticate(self.teacher)
        response = client.post('/api/evaluation/todos/', {'attempt_id': str(self.attempt.attempt_id), 'kind': 'evidence'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(client.get('/api/evaluation/todos/').data['groups']['evidence']), 1)
        self.assertEqual(client.post('/api/evaluation/todos/sync/', {}, format='json').status_code, 200)
        self.assertEqual(client.post('/api/evaluation/receipts/', {}, format='json').status_code, 200)
        self.assertTrue(client.get('/api/evaluation/receipts/').data['receipts'])
        NonFormalAccount.objects.create(student=self.student, source='offline')
        self.assertFalse(client.get('/api/evaluation/receipts/').data['receipts'])
        self.assertFalse(client.get('/api/evaluation/todos/').data['groups']['evidence'])

    def test_http_claim_conflict_is_409_and_student_is_denied(self):
        todo = self.make_todo()
        client = APIClient()
        client.force_authenticate(self.student)
        self.assertEqual(client.get('/api/evaluation/todos/').status_code, 403)
        client.force_authenticate(self.teacher)
        path = f'/api/evaluation/todos/{todo.todo_id}/'
        self.assertEqual(client.post(path, {'revision': 1, 'action': 'claim'}, format='json').status_code, 200)
        response = client.post(path, {'revision': 1, 'action': 'claim'}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'revision_conflict')
        self.assertEqual(client.post(path, {'revision': 2, 'action': 'handle', 'improved': True}, format='json').status_code, 400)
