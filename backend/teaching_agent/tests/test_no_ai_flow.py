from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from learning_map import constants as map_constants
from learning_map.models import Capability, CatalogVersion, TaskAttempt, TaskPackage, VerificationFact
from skill_review import constants as review_constants
from skill_review.models import RetestAssignment, SubmissionSnapshot
from teaching_agent.models import ModelCallRecord, PracticeAction
from users.models import CTFUser


VALIDATOR = {
    'version': 'm2-static-v1',
    'type': 'structured_rules',
    'manual_required': False,
    'checks': [
        {'id': 'basis', 'field': 'basis_clause', 'required': True},
        {'id': 'decision', 'field': 'decision', 'equals': 'reject'},
    ],
}
RETEST_VALIDATOR = {
    'version': 'm2-static-v1',
    'type': 'structured_rules',
    'manual_required': False,
    'checks': [{'id': 'basis', 'field': 'basis_clause', 'required': True}],
}


@override_settings(
    LEARNING_MAP_AI_ENABLED=False,
    KNOWLEDGE_RAG_SEMANTIC_ENABLED=False,
    AGENT_RUNTIME_SEMANTIC_RETRIEVAL=False,
    TUTOR_AGENT_ROUTER_ENABLED=False,
    TUTOR_SPECIALISTS_ENABLED=False,
    TUTOR_CONTEXT_ENABLED=False,
)
class NoAICoreFlowTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='m2-no-ai', password='test', role='student')
        self.catalog = CatalogVersion.objects.create(
            version='m2-no-ai-v1', label='No AI catalog', status=map_constants.CATALOG_STATUS_PUBLISHED,
        )
        self.capability = Capability.objects.create(
            catalog=self.catalog,
            stable_id='M2-NO-AI',
            track=map_constants.TRACK_DATA,
            title='No-AI capability',
            observable_objective='Complete deterministic verification.',
            dimension=map_constants.DIMENSION_IDENTIFY,
            status=map_constants.CAPABILITY_STATUS_OPEN,
        )
        self.task = self._task('M2-NO-AI-TASK', map_constants.PURPOSE_VERIFICATION, VALIDATOR)
        self.retest_task = self._task('M2-NO-AI-RETEST', map_constants.PURPOSE_RETEST, RETEST_VALIDATOR)
        self.task.retest_task_keys = [self.retest_task.task_key]
        self.task.save(update_fields=['retest_task_keys'])
        # Module 3 requires an explicit course grant and reviewed material reference,
        # not an arbitrary path in TaskPackage JSON.
        from types import SimpleNamespace
        from learning_knowledge.models import CourseGrant
        from learning_knowledge.tests.helpers import material
        CourseGrant.objects.create(user=self.student, catalog=self.catalog)
        self.material_revision = material(SimpleNamespace(task=self.task, teacher=self.student))
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def _task(self, key, purpose, validator):
        task = TaskPackage.objects.create(
            catalog=self.catalog,
            task_key=key,
            version='1.0.0',
            title=key,
            track=map_constants.TRACK_DATA,
            purpose=purpose,
            execution_mode=map_constants.EXECUTION_READONLY,
            status=map_constants.TASK_STATUS_FROZEN,
            materials={'student_material_refs': ['synthetic/data.csv'], 'withdrawn': False},
            hints=[{'level': level, 'title': f'Hint {level}'} for level in range(1, 5)],
            student_solution_ref='student/static-analysis.md',
            validator=validator,
            acceptance={'rules': ['Submit a justified decision.']},
        )
        task.capabilities.set([self.capability])
        return task

    @patch('ai_assistant.service.get_ai_assistant_service', side_effect=AssertionError('external model called'))
    def test_claim_material_practice_verify_progress_and_retest_without_ai(self, model_boundary):
        claim = self.client.post(
            f'/api/learning-map/tasks/{self.task.pk}/claim/',
            {'version': self.catalog.version},
            format='json',
        )
        self.assertEqual(claim.status_code, 201, claim.content)
        attempt_id = claim.data['attempt_id']

        run = self.client.post('/api/teaching/runs/', {'attempt_id': attempt_id}, format='json')
        self.assertEqual(run.status_code, 201, run.content)
        self.assertEqual(run.data['task_context']['materials']['student_material_refs'], [
            {'material_id': str(self.material_revision.material.material_id), 'revision': 1},
        ])
        self.assertNotIn('synthetic/data.csv', str(run.data['task_context']))

        practice = self.client.post(
            f"/api/teaching/runs/{run.data['run_id']}/actions/",
            {'action_id': 'm2-no-ai-action-1', 'action_type': 'readonly_observation', 'payload': {'observed': True}},
            format='json',
        )
        self.assertEqual(practice.status_code, 201, practice.content)
        self.assertEqual(practice.data['status'], PracticeAction.STATUS_REGISTERED)

        absent_adapter = self.client.post(
            f"/api/teaching/runs/{run.data['run_id']}/actions/",
            {'action_id': 'm2-no-ai-action-2', 'action_type': 'sandbox_execute', 'payload': {}},
            format='json',
        )
        self.assertEqual(absent_adapter.status_code, 201)
        self.assertEqual(absent_adapter.data['status'], PracticeAction.STATUS_UNAVAILABLE)
        self.assertEqual(absent_adapter.data['dependency'], 'module4')

        submission = self.client.post(
            f'/api/skill-review/attempts/{attempt_id}/submit/',
            {
                'client_submission_id': 'm2-no-ai-submission',
                'payload': {'basis_clause': 'Synthetic rule 1', 'decision': 'reject'},
            },
            format='json',
        )
        self.assertEqual(submission.status_code, 201, submission.content)
        self.assertEqual(submission.data['overall_status'], review_constants.OVERALL_PASSED)
        original_submission = SubmissionSnapshot.objects.get(client_submission_id='m2-no-ai-submission')
        attempt = TaskAttempt.objects.get(attempt_id=attempt_id)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, map_constants.ATTEMPT_VERIFIED)
        self.assertTrue(VerificationFact.objects.filter(attempt_id=attempt.attempt_id).exists())

        progress = self.client.get(f'/api/learning-map/me/map/?version={self.catalog.version}')
        self.assertEqual(progress.status_code, 200, progress.content)
        self.assertIn('M2-NO-AI', str(progress.data))

        review = self.client.put(
            f'/api/skill-review/submissions/{original_submission.submission_id}/review-card/',
            {
                'original_task_summary': 'Synthetic data decision',
                'error_evidence': 'Synthetic evidence',
                'judgment_at_time': 'Checked fields',
                'correct_basis': 'Synthetic rule 1',
                'next_verification': 'Use a new scenario',
                'student_reflection': 'Recheck scope',
                'complete': True,
            },
            format='json',
        )
        self.assertEqual(review.status_code, 200, review.content)
        assignment = RetestAssignment.objects.get(original_submission=original_submission)
        retest_claim = self.client.post(f'/api/skill-review/retests/{assignment.assignment_id}/claim/')
        self.assertEqual(retest_claim.status_code, 201, retest_claim.content)
        retest_attempt_id = retest_claim.data['attempt_id']
        retest_submission = self.client.post(
            f'/api/skill-review/attempts/{retest_attempt_id}/submit/',
            {
                'client_submission_id': 'm2-no-ai-retest-submission',
                'payload': {'basis_clause': 'Synthetic rule 1'},
            },
            format='json',
        )
        self.assertEqual(retest_submission.status_code, 201, retest_submission.content)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, review_constants.RETEST_COMPLETED)
        self.assertEqual(assignment.outcome, review_constants.RETEST_OUTCOME_PASSED)
        self.assertEqual(ModelCallRecord.objects.count(), 0)
        model_boundary.assert_not_called()
