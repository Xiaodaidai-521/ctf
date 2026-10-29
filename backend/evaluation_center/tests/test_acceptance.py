"""Fixed phase-one acceptance: real local flows, explicit external dependencies.

All identities/materials below are synthetic in Django's isolated test database.
Injected provider errors are fault tests, not claims of real supplier validation.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from django.db import DatabaseError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from evaluation_center.operations import change_todo, create_todo, todo_payload
from evaluation_center.projections import attempt_detail, query_learning
from learning_map.models import TaskAttempt, VerificationFact
from skill_review import constants
from skill_review.models import ManualReviewTask, SubmissionSnapshot
from skill_review.services import retest, submissions
from skill_review.tests.test_module6 import good_payload, make_capability, make_catalog, make_task, RETEST_VALIDATOR
from teaching_agent.api_tutoring import ProviderQuotaExhausted, ProviderRateLimited
from teaching_agent.models import HintCard, ModelCallRecord
from users.models import CTFUser


@override_settings(KNOWLEDGE_RAG_SEMANTIC_ENABLED=False, AGENT_RUNTIME_SEMANTIC_RETRIEVAL=False,
                   TUTOR_AGENT_ROUTER_ENABLED=False, TUTOR_SPECIALISTS_ENABLED=False,
                   TUTOR_CONTEXT_ENABLED=False, TUTORING_TOTAL_WAIT_SECONDS=0.05)
class FixedAcceptanceTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='accept-student', role='student')
        self.teacher = CTFUser.objects.create_user(username='accept-teacher', role='teacher')
        self.catalog = make_catalog()
        self.capability = make_capability(self.catalog)
        self.task = make_task(self.catalog, self.capability, retest_keys=['ACCEPT-NEW-SCENE'])
        self.retest_task = make_task(self.catalog, self.capability, task_key='ACCEPT-NEW-SCENE',
                                    purpose='retest', validator=RETEST_VALIDATOR)
        HintCard.objects.create(task=self.task, level=1, title='审核提示', content='先核对授权范围。',
                                material_ref='synthetic/hint.md', version='v1')
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def claim(self):
        response = self.client.post(f'/api/learning-map/tasks/{self.task.pk}/claim/',
                                    {'version': self.catalog.version}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        return TaskAttempt.objects.get(attempt_id=response.data['attempt_id'])

    def flow(self, fault):
        async def timeout(**kwargs):
            await asyncio.sleep(1)
            return {'content': 'late synthetic reply', 'hint_level': 1}

        failures = {'disconnect': ConnectionError('synthetic disconnect'),
                    'timeout': timeout, 'rate_limit': ProviderRateLimited('synthetic 429'),
                    'quota': ProviderQuotaExhausted('synthetic quota'),
                    'all_off': AssertionError('model must stay disabled')}
        with override_settings(LEARNING_MAP_AI_ENABLED=fault != 'all_off'), patch(
                'teaching_agent.api_tutoring._default_provider_call', new_callable=AsyncMock) as provider:
            provider.side_effect = failures[fault]
            attempt = self.claim()
            response = self.client.post('/api/teaching/runs/', {'attempt_id': str(attempt.attempt_id)}, format='json')
            self.assertEqual(response.status_code, 201, response.content)
            run_id = response.data['run_id']
            practice = self.client.post(f'/api/teaching/runs/{run_id}/actions/',
                                        {'action_id': 'read', 'action_type': 'readonly_observation',
                                         'payload': {'observed': True}}, format='json')
            self.assertEqual(practice.status_code, 201, practice.content)
            if fault != 'all_off':
                help_response = self.client.post(f'/api/teaching/runs/{run_id}/tutor/',
                                                 {'request_id': fault, 'message': '请给范围线索', 'hint_level': 1}, format='json')
                self.assertEqual(help_response.status_code, 201, help_response.content)
                self.assertEqual(help_response.data['status'], 'degraded')
                call = ModelCallRecord.objects.get(request__request_id=fault)
                self.assertLess(call.latency_ms, 10000)
                self.assertIsNone(call.cost_amount)
                self.assertIsNone(call.input_tokens)
            response = self.client.post(f'/api/skill-review/attempts/{attempt.attempt_id}/submit/',
                                        {'client_submission_id': 'fixed-original', 'payload': good_payload()}, format='json')
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(response.data['program_status'], 'passed')
            self.assertEqual(response.data['overall_status'], 'pending_manual')
            submission = SubmissionSnapshot.objects.get(client_submission_id='fixed-original')
            original = submission.results.get(is_current=True)
            self.assertFalse((original.manual_result or {}).get('total_score'))
            review = ManualReviewTask.objects.get(submission=submission)
            self.client.force_authenticate(self.teacher)
            claim = self.client.post(f'/api/skill-review/teacher/manual-tasks/{review.review_id}/claim/', {}, format='json')
            self.assertEqual(claim.status_code, 200, claim.content)
            reviewed = self.client.post(f'/api/skill-review/teacher/manual-tasks/{review.review_id}/review/',
                                        {'scores': {key: {'score': 2, 'evidence': '合成依据', 'reason': '符合固定量表'}
                                                    for key, _ in constants.RUBRIC_ITEMS},
                                         'decision': 'pass', 'remarks': '量表复核'}, format='json')
            self.assertEqual(reviewed.status_code, 200, reviewed.content)
            todo = create_todo(actor=self.teacher, attempt=attempt)
            todo = change_todo(todo.todo_id, actor=self.teacher, revision=todo.revision, action='claim')
            todo = change_todo(todo.todo_id, actor=self.teacher, revision=todo.revision, action='handle', summary='安排新场景复测')
            assignment, _ = retest.schedule_retest(submission, actor=self.teacher)
            self.client.force_authenticate(self.student)
            claimed = self.client.post(f'/api/skill-review/retests/{assignment.assignment_id}/claim/', {}, format='json')
            self.assertEqual(claimed.status_code, 201, claimed.content)
            completed = self.client.post(f"/api/skill-review/attempts/{claimed.data['attempt_id']}/submit/",
                                         {'client_submission_id': 'fixed-retest', 'payload': good_payload()}, format='json')
            self.assertEqual(completed.status_code, 201, completed.content)
            self.assertEqual(completed.data['overall_status'], 'passed')
            todo = change_todo(todo.todo_id, actor=self.teacher, revision=todo.revision,
                               action='verify', retest_id=assignment.assignment_id)
            self.assertEqual(todo_payload(todo)['status'], 'verified')
            self.assertEqual(SubmissionSnapshot.objects.count(), 2)
            self.assertTrue(VerificationFact.objects.filter(attempt_id=attempt.attempt_id).exists())
            original.refresh_from_db()
            self.assertEqual(original.overall_status, 'passed')
            if fault == 'all_off':
                provider.assert_not_awaited()
                self.assertEqual(ModelCallRecord.objects.count(), 0)

    def test_06_07_10_disconnect_core_teacher_and_retest(self):
        self.flow('disconnect')

    def test_06_07_10_timeout_core_teacher_and_retest(self):
        self.flow('timeout')

    def test_06_07_10_rate_limit_core_teacher_and_retest(self):
        self.flow('rate_limit')

    def test_06_07_10_quota_core_teacher_and_retest(self):
        self.flow('quota')

    def test_06_07_10_all_models_off_core_teacher_and_retest(self):
        self.flow('all_off')

    def test_05_source_save_rollback_retry_and_idempotency(self):
        attempt = self.claim()
        with patch('skill_review.services.submissions.events.emit_event', side_effect=DatabaseError('synthetic save failure')):
            with self.assertRaises(DatabaseError):
                submissions.create_submission(student=self.student, attempt=attempt, client_submission_id='retry', payload=good_payload())
        self.assertFalse(SubmissionSnapshot.objects.exists())
        self.assertFalse(VerificationFact.objects.exists())
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'claimed')
        for _ in range(2):
            submissions.create_submission(student=self.student, attempt=attempt, client_submission_id='retry', payload=good_payload())
        self.assertEqual(SubmissionSnapshot.objects.count(), 1)
        detail = attempt_detail(attempt)
        self.assertEqual(detail['overall_status'], 'pending_manual')
        self.assertEqual(detail['submission_count'], 1)

    def test_05_todo_save_error_is_retryable_without_false_success(self):
        todo = create_todo(actor=self.teacher, attempt=self.claim())
        self.client.force_authenticate(self.teacher)
        path = f'/api/evaluation/todos/{todo.todo_id}/'
        with patch('evaluation_center.operations.TodoAction.objects.create', side_effect=DatabaseError('synthetic save failure')):
            response = self.client.post(path, {'revision': 1, 'action': 'claim'}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['code'], 'save_pending_retry')
        todo.refresh_from_db()
        self.assertIsNone(todo.owner_id)
        response = self.client.post(path, {'revision': 1, 'action': 'claim'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)

    def test_03_08_10_network_isolation_and_actual_execution_remain_unverified(self):
        self.task.track = 'network'
        self.task.validator = {'type': 'server_verifier', 'version': 'missing-m5-v1'}
        self.task.save(update_fields=['track', 'validator'])
        attempt = self.claim()
        submissions.create_submission(student=self.student, attempt=attempt, client_submission_id='network-contract',
                                      payload={'passed': True, 'source': 'browser', 'isolation_verified': True})
        detail = attempt_detail(attempt)
        self.assertNotEqual(detail['overall_status'], 'passed')
        data = query_learning(student_id=self.student.pk)
        self.assertEqual(data['source_status']['module5'], 'not_connected')
        self.assertEqual(data['source_status']['execution'], 'not_started')
        self.assertEqual(data['source_status']['actual_protection'], 'not_evaluated')
