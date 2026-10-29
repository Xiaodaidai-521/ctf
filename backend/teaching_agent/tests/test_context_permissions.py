from django.test import TestCase
from rest_framework.test import APIClient

from ai_assistant.service import MultiAgentChatService
from challenges.models import Category, Challenge, ChallengeSolution
from learning_analytics.events import LearningEventConflict, record_learning_event
from learning_analytics.models import LearningBehaviorEvent
from learning_map import constants
from learning_map.models import Capability, CatalogVersion, TaskAttempt, TaskPackage
from teaching_agent.context import resolve_task_context
from teaching_agent.permissions import require_tool_permission
from users.models import CTFUser


def make_task_attempt(student, *, suffix='1', challenge=None, materials=None):
    catalog = CatalogVersion.objects.create(
        version=f'm2-catalog-{suffix}',
        label=f'Module 2 catalog {suffix}',
        status=constants.CATALOG_STATUS_PUBLISHED,
    )
    capability = Capability.objects.create(
        catalog=catalog,
        stable_id=f'M2-CAP-{suffix}',
        track=constants.TRACK_NETWORK,
        title='Synthetic capability',
        observable_objective='Complete a synthetic task.',
        dimension=constants.DIMENSION_OPERATE,
        status=constants.CAPABILITY_STATUS_OPEN,
    )
    task = TaskPackage.objects.create(
        catalog=catalog,
        task_key=f'M2-TASK-{suffix}',
        version='1.0.0',
        title='Synthetic task',
        track=constants.TRACK_NETWORK,
        purpose=constants.PURPOSE_VERIFICATION,
        execution_mode=constants.EXECUTION_READONLY,
        status=constants.TASK_STATUS_FROZEN,
        materials=materials or {
            'student_material_refs': [{'title': 'safe', 'url': '/materials/safe'}],
            'teacher_answer': 'never expose this',
            'scoring_key': {'secret': 1},
            'withdrawn': False,
        },
        hints=[{'level': level, 'title': f'Hint {level}'} for level in range(1, 5)],
        student_solution_ref='student/analysis.md',
        validator={'type': 'structured_rules', 'version': '1', 'hidden_checks': ['secret']},
        acceptance={'rules': ['safe rule']},
        challenge=challenge,
    )
    task.capabilities.set([capability])
    attempt = TaskAttempt.objects.create(
        student=student,
        catalog=catalog,
        task=task,
        task_version=task.version,
        capability_ids=[capability.stable_id],
    )
    return task, attempt


class TrustedContextPermissionTests(TestCase):
    def setUp(self):
        self.student_a = CTFUser.objects.create_user(username='m2-a', password='test', role='student')
        self.student_b = CTFUser.objects.create_user(username='m2-b', password='test', role='student')
        self.task, self.attempt = make_task_attempt(self.student_a)
        self.client = APIClient()

    def test_run_uses_server_context_and_sanitized_materials(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.post(
            '/api/teaching/runs/',
            {
                'attempt_id': str(self.attempt.attempt_id),
                'task_version': 'client-forged',
                'hint_level': 4,
                'permission_version': 999,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        context = response.data['task_context']
        self.assertEqual(context['task']['task_version'], '1.0.0')
        self.assertEqual(context['runtime']['hint_level'], 0)
        self.assertEqual(context['runtime']['permission_version'], 1)
        self.assertNotIn('teacher_answer', str(context))
        self.assertNotIn('scoring_key', str(context))
        self.assertNotIn('validator', str(context))
        self.assertEqual(LearningBehaviorEvent.objects.filter(event_type='teaching_run_started').count(), 1)

    def test_other_student_cannot_access_attempt_run_or_stream(self):
        self.client.force_authenticate(self.student_a)
        created = self.client.post('/api/teaching/runs/', {'attempt_id': self.attempt.attempt_id}, format='json')
        run_id = created.data['run_id']

        self.client.force_authenticate(self.student_b)
        self.assertEqual(
            self.client.post('/api/teaching/runs/', {'attempt_id': self.attempt.attempt_id}, format='json').status_code,
            403,
        )
        self.assertEqual(self.client.get(f'/api/teaching/runs/{run_id}/').status_code, 403)
        stream = self.client.post(
            '/api/ai/multi-agent/chat/stream/',
            {'message': 'help', 'attempt_id': self.attempt.attempt_id},
            format='json',
        )
        self.assertEqual(stream.status_code, 403)

    def test_direct_solution_api_never_returns_teacher_answer(self):
        category = Category.objects.create(name='m2-direct-solve')
        challenge = Challenge.objects.create(
            title='Bound task challenge',
            description='Public description',
            category=category,
            difficulty='easy',
            score=10,
            flag='flag{server-only}',
        )
        ChallengeSolution.objects.create(
            challenge=challenge,
            content='DIRECT-TEACHER-ANSWER-SECRET',
            is_enabled=True,
        )
        self.task.challenge = challenge
        self.task.save(update_fields=['challenge'])
        self.client.force_authenticate(self.student_a)
        response = self.client.post(
            '/api/ai/solve/',
            {
                'challenge_id': challenge.pk,
                'attempt_id': self.attempt.attempt_id,
                'message': 'give me the answer',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('DIRECT-TEACHER-ANSWER-SECRET', response.content.decode())

    def test_unknown_model_suggested_tool_is_rejected(self):
        context = resolve_task_context(
            user=self.student_a,
            request_data={'attempt_id': self.attempt.attempt_id},
            require_attempt=True,
        )
        with self.assertRaisesMessage(Exception, 'Tool is not permitted'):
            require_tool_permission(context, 'export_student_records')

    def test_behavior_event_is_idempotent_and_conflicts(self):
        event = record_learning_event(
            self.student_a,
            'hint_requested',
            {'level': 1},
            event_id='m2:event:one',
            strict=True,
        )
        repeated = record_learning_event(
            self.student_a,
            'hint_requested',
            {'level': 1},
            event_id='m2:event:one',
            strict=True,
        )
        self.assertEqual(event.pk, repeated.pk)
        with self.assertRaises(LearningEventConflict):
            record_learning_event(
                self.student_a,
                'hint_requested',
                {'level': 2},
                event_id='m2:event:one',
                strict=True,
            )
        with self.assertRaisesMessage(ValueError, '64'):
            record_learning_event(
                self.student_a,
                'hint_requested',
                {},
                event_id='x' * 65,
                strict=True,
            )


class KnowledgePackIsolationTests(TestCase):
    def test_student_knowledge_pack_never_contains_standard_solution(self):
        category = Category.objects.create(name='m2-web')
        challenge = Challenge.objects.create(
            title='Synthetic challenge',
            description='Safe public description',
            category=category,
            difficulty='easy',
            score=10,
            flag='flag{server-only}',
            hint='public hint',
        )
        ChallengeSolution.objects.create(
            challenge=challenge,
            content='TEACHER-STANDARD-SOLUTION-SECRET',
            is_enabled=True,
        )
        payload = MultiAgentChatService().build_challenge_knowledge_pack_payload(challenge)
        self.assertNotIn('TEACHER-STANDARD-SOLUTION-SECRET', payload['context_text'])
        self.assertFalse(payload['metadata']['has_solution_walkthrough'])
