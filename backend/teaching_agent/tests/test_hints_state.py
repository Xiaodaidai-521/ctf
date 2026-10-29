from django.test import TestCase
from rest_framework.test import APIClient

from learning_analytics.models import LearningBehaviorEvent
from learning_map import constants
from learning_map.models import Capability, CatalogVersion, TaskAttempt, TaskPackage
from skill_review.models import AssistanceRecord
from teaching_agent.models import HintCard, ResumeReceipt, StudentAnalysis, TeacherTicket, TeachingRun
from users.models import CTFUser


class HintStateAndAnalysisTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='m2-state', password='test', role='student')
        self.other = CTFUser.objects.create_user(username='m2-state-other', password='test', role='student')
        self.teacher = CTFUser.objects.create_user(username='m2-teacher', password='test', role='teacher')
        self.catalog = CatalogVersion.objects.create(
            version='m2-state-v1', label='State catalog', status=constants.CATALOG_STATUS_PUBLISHED,
        )
        capability = Capability.objects.create(
            catalog=self.catalog,
            stable_id='M2-STATE-CAP',
            track=constants.TRACK_NETWORK,
            title='State capability',
            observable_objective='Exercise tutoring state.',
            dimension=constants.DIMENSION_OPERATE,
            status=constants.CAPABILITY_STATUS_OPEN,
        )
        self.task = TaskPackage.objects.create(
            catalog=self.catalog,
            task_key='M2-STATE-TASK',
            version='1.0.0',
            title='State task',
            track=constants.TRACK_NETWORK,
            purpose=constants.PURPOSE_VERIFICATION,
            execution_mode=constants.EXECUTION_READONLY,
            status=constants.TASK_STATUS_FROZEN,
            materials={'student_material_refs': ['state/public.md'], 'withdrawn': False},
            hints=[{'level': level, 'title': f'Hint {level}'} for level in range(1, 5)],
            student_solution_ref='state/analysis.md',
            validator={
                'type': 'structured_rules',
                'version': 'state-v1',
                'manual_required': False,
                'checks': [{'id': 'answer', 'field': 'answer', 'equals': 'safe'}],
            },
            acceptance={'rules': ['Submit safe.']},
        )
        self.task.capabilities.set([capability])
        self.attempt = TaskAttempt.objects.create(
            student=self.student,
            catalog=self.catalog,
            task=self.task,
            task_version=self.task.version,
            capability_ids=[capability.stable_id],
        )
        for level in range(1, 5):
            HintCard.objects.create(
                task=self.task,
                level=level,
                title=f'Reviewed hint {level}',
                content=f'STATIC-HINT-{level}',
                material_ref=f'hints/{level}.md',
                version='reviewed-v1',
                unlock_rule={'previous_level_shown': level > 1},
            )
        self.analysis = StudentAnalysis.objects.create(
            task=self.task,
            title='Unlocked analysis',
            content='STATIC-STUDENT-ANALYSIS-SECRET',
            content_ref='state/analysis.md',
            version='reviewed-v1',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        response = self.client.post('/api/teaching/runs/', {'attempt_id': self.attempt.attempt_id}, format='json')
        self.run_id = response.data['run_id']

    def test_four_level_unlock_and_request_display_are_separate(self):
        locked = self.client.post(
            f'/api/teaching/runs/{self.run_id}/hints/request/',
            {'request_id': 'hint-level-2-early', 'level': 2},
            format='json',
        )
        self.assertEqual(locked.status_code, 403)

        requested = self.client.post(
            f'/api/teaching/runs/{self.run_id}/hints/request/',
            {'request_id': 'hint-level-1', 'level': 1},
            format='json',
        )
        self.assertEqual(requested.status_code, 201, requested.content)
        self.assertNotIn('content', requested.data)
        record = AssistanceRecord.objects.get(record_id=requested.data['record_id'])
        self.assertFalse(record.shown)
        self.assertEqual(LearningBehaviorEvent.objects.filter(event_type='hint_requested').count(), 1)
        self.assertEqual(LearningBehaviorEvent.objects.filter(event_type='hint_displayed').count(), 0)

        displayed = self.client.post(
            f'/api/teaching/runs/{self.run_id}/hints/hint-level-1/display/',
            {},
            format='json',
        )
        self.assertEqual(displayed.status_code, 200, displayed.content)
        self.assertEqual(displayed.data['content'], 'STATIC-HINT-1')
        record.refresh_from_db()
        self.assertTrue(record.shown)
        self.assertEqual(LearningBehaviorEvent.objects.filter(event_type='hint_displayed').count(), 1)

        level_two = self.client.post(
            f'/api/teaching/runs/{self.run_id}/hints/request/',
            {'request_id': 'hint-level-2', 'level': 2},
            format='json',
        )
        self.assertEqual(level_two.status_code, 201)
        self.task.materials['withdrawn'] = True
        self.task.save(update_fields=['materials'])
        withdrawn = self.client.post(
            f'/api/teaching/runs/{self.run_id}/hints/hint-level-2/display/',
            {},
            format='json',
        )
        self.assertEqual(withdrawn.status_code, 403)
        self.assertNotIn('STATIC-HINT-2', withdrawn.content.decode())

    def test_pause_resume_survives_fresh_client_and_is_idempotent(self):
        run = TeachingRun.objects.get(run_id=self.run_id)
        paused = self.client.post(
            f'/api/teaching/runs/{self.run_id}/pause/',
            {'expected_state_version': run.state_version},
            format='json',
        )
        self.assertEqual(paused.status_code, 200, paused.content)
        self.assertEqual(paused.data['state'], TeachingRun.STATE_PAUSED)

        fresh_client = APIClient()
        fresh_client.force_authenticate(self.student)
        resumed = fresh_client.post(
            f'/api/teaching/runs/{self.run_id}/resume/',
            {'request_id': 'resume-after-restart', 'expected_state_version': paused.data['state_version']},
            format='json',
        )
        self.assertEqual(resumed.status_code, 200, resumed.content)
        self.assertTrue(resumed.data['created'])
        repeated = fresh_client.post(
            f'/api/teaching/runs/{self.run_id}/resume/',
            {'request_id': 'resume-after-restart', 'expected_state_version': paused.data['state_version']},
            format='json',
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertFalse(repeated.data['created'])
        self.assertEqual(repeated.data['state_version'], resumed.data['state_version'])
        self.assertEqual(ResumeReceipt.objects.count(), 1)

        stale = fresh_client.post(
            f'/api/teaching/runs/{self.run_id}/resume/',
            {'request_id': 'resume-stale', 'expected_state_version': paused.data['state_version']},
            format='json',
        )
        self.assertEqual(stale.status_code, 409)

    def test_ticket_ownership_teacher_help_and_static_analysis_authorization(self):
        locked = self.client.get(f'/api/teaching/runs/{self.run_id}/analysis/')
        self.assertEqual(locked.status_code, 403)
        self.assertNotIn('STATIC-STUDENT-ANALYSIS-SECRET', locked.content.decode())
        run_detail = self.client.get(f'/api/teaching/runs/{self.run_id}/')
        self.assertNotIn('STATIC-STUDENT-ANALYSIS-SECRET', run_detail.content.decode())

        ticket_response = self.client.post(
            f'/api/teaching/runs/{self.run_id}/teacher-tickets/',
            {'question_summary': 'Need reviewed guidance'},
            format='json',
        )
        self.assertEqual(ticket_response.status_code, 201)
        ticket_id = ticket_response.data['ticket_id']

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/teaching/teacher-tickets/{ticket_id}/').status_code, 403)

        self.client.force_authenticate(self.teacher)
        helped = self.client.post(
            f'/api/teaching/teacher-tickets/{ticket_id}/help/',
            {'summary': 'Actual reviewed help'},
            format='json',
        )
        self.assertEqual(helped.status_code, 200, helped.content)
        self.assertEqual(helped.data['actual_help_summary'], 'Actual reviewed help')
        self.assertEqual(TeacherTicket.objects.get(ticket_id=ticket_id).status, TeacherTicket.STATUS_HELPED)
        self.assertTrue(AssistanceRecord.objects.filter(attempt=self.attempt, kind='teacher_help', shown=True).exists())

        self.client.force_authenticate(self.student)
        submission = self.client.post(
            f'/api/skill-review/attempts/{self.attempt.attempt_id}/submit/',
            {'client_submission_id': 'state-pass', 'payload': {'answer': 'safe'}},
            format='json',
        )
        self.assertEqual(submission.status_code, 201, submission.content)
        unlocked = self.client.get(f'/api/teaching/runs/{self.run_id}/analysis/')
        self.assertEqual(unlocked.status_code, 200, unlocked.content)
        self.assertEqual(unlocked.data['content'], 'STATIC-STUDENT-ANALYSIS-SECRET')
        self.assertEqual(unlocked['Cache-Control'], 'private, no-store')
        self.assertTrue(AssistanceRecord.objects.filter(attempt=self.attempt, kind='analysis_view', shown=True).exists())
