import asyncio
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.test import APIClient

from articles.models import Article
from learning_analytics.models import LearningBehaviorEvent
from learning_map import constants
from learning_knowledge.models import CourseGrant, Material
from learning_knowledge.policy import material_ref, task_policy_stamp
from learning_knowledge.services import search
from skill_review.models import AssistanceRecord
from teaching_agent.api_tutoring import ProviderQuotaExhausted, ProviderRateLimited, _material_hash, accept_provider_result
from teaching_agent.context import resolve_task_context
from teaching_agent.models import HintCard, StudentAnalysis, TeachingRun, TutorRequest, TutorResponseCache
from .helpers import material, setup_case


class TeachingBoundaryTests(TestCase):
    def setUp(self):
        setup_case(self)
        self.lesson = material(self)
        self.hint = material(self, 'hint', text='REVIEWED-DIRECTION', level=1)
        self.card = HintCard.objects.create(task=self.task, level=1, title='Direction',
                                           content='STALE-COPY-SECRET', material_ref=material_ref(self.hint), version='m3-test')
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        created = self.client.post('/api/teaching/runs/', {'attempt_id': str(self.attempt.attempt_id)}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.run_id = created.data['run_id']
        self.base = f'/api/teaching/runs/{self.run_id}/'

    def tutor(self, request_id):
        return self.client.post(self.base + 'tutor/', {'request_id': request_id, 'message': 'explain', 'hint_level': 1}, format='json')

    def test_t3_12_hint_request_show_uses_real_module_six_and_live_source(self):
        requested = self.client.post(self.base + 'hints/request/', {'request_id': 'hint-one', 'level': 1}, format='json')
        self.assertEqual(requested.status_code, 201, requested.data)
        self.assertFalse(AssistanceRecord.objects.get().shown)
        self.assertNotIn('REVIEWED-DIRECTION', str(requested.data))
        shown = self.client.post(self.base + 'hints/hint-one/display/', {}, format='json')
        self.assertEqual(shown.status_code, 200, shown.data)
        self.assertEqual(shown.data['content'], self.hint.source_snapshot)
        self.assertEqual(shown['Cache-Control'], 'private, no-store')
        self.assertTrue(AssistanceRecord.objects.get().shown)
        Material.objects.filter(pk=self.hint.material_id).update(revoked_at=timezone.now())
        denied = self.client.post(self.base + 'hints/hint-one/display/', {}, format='json')
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn('REVIEWED-DIRECTION', str(denied.data))
        self.assertTrue(AssistanceRecord.objects.get().shown)

    def test_t3_07_generation_result_revoked_before_commit_is_not_saved(self):
        context = resolve_task_context(user=self.student, request_data={'run_id': self.run_id}, require_attempt=True)
        request = TutorRequest.objects.create(request_id='pending', idempotency_key='pending', payload_hash='test',
            student=self.student, run=context.run, attempt=self.attempt, hint_level=1,
            context_version=context.run.context_version, permission_version=context.run.permission_version,
            material_hash=_material_hash(context))
        TeachingRun.objects.filter(pk=context.run.pk).update(state=TeachingRun.STATE_WAITING_AI)
        Material.objects.filter(pk=self.lesson.material_id).update(revoked_at=timezone.now())
        with self.assertRaises(PermissionDenied):
            accept_provider_result(request=request, context=context, result={'content': 'GENERATED-SECRET'}, latency_ms=1)
        request.refresh_from_db()
        self.assertNotIn('GENERATED-SECRET', str(request.response))
        self.assertFalse(TutorResponseCache.objects.exists())

    def test_t3_07_revocation_during_provider_failure_does_not_fallback_to_old_hint(self):
        def fail(*args, **kwargs):
            CourseGrant.objects.filter(user=self.student).update(active=False)
            raise ConnectionError('disconnected')
        with patch('teaching_agent.api_tutoring._run_with_budget', side_effect=fail):
            response = self.tutor('revoke-during-call')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['response']['hint_level'], 0)
        self.assertNotIn('REVIEWED-DIRECTION', str(response.data))
        self.assertFalse(AssistanceRecord.objects.exists())

    def test_t3_13_unverified_provider_inference_falls_back_to_reviewed_static_card(self):
        with patch('teaching_agent.api_tutoring._run_with_budget', return_value={'content': 'UNVERIFIED-SECRET', 'sources': ['valid-looking-id']}):
            response = self.tutor('unverified')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['response']['content'], self.hint.source_snapshot)
        self.assertNotIn('UNVERIFIED-SECRET', str(response.data))
        self.assertFalse(TutorResponseCache.objects.exists())
        TutorRequest.objects.filter(request_id='unverified').update(response={'content': 'POISONED-HISTORY'})
        repeated = self.tutor('unverified')
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertNotIn('POISONED-HISTORY', str(repeated.data))
        self.assertEqual(AssistanceRecord.objects.count(), 1)

    def test_t3_14_disconnect_timeout_429_quota_all_use_reviewed_static(self):
        for index, error in enumerate([ConnectionError(), asyncio.TimeoutError(), ProviderRateLimited(), ProviderQuotaExhausted()]):
            with self.subTest(error=type(error).__name__):
                from teaching_agent.models import ProviderCircuit
                ProviderCircuit.objects.all().delete()
                with patch('teaching_agent.api_tutoring._run_with_budget', side_effect=error):
                    response = self.tutor(f'fault-{index}')
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data['response']['content'], self.hint.source_snapshot)
                self.assertTrue(response.data['response']['fallback'])
        self.assertEqual(AssistanceRecord.objects.filter(shown=True).count(), 4)

    def test_t3_14_independent_retest_never_gets_fallback_hint(self):
        self.task.purpose = constants.PURPOSE_RETEST
        self.task.save()
        with patch('teaching_agent.api_tutoring._run_with_budget') as provider:
            self.assertEqual(self.tutor('retest').status_code, 403)
            provider.assert_not_called()
        response = self.client.post(self.base + 'hints/request/', {'request_id': 'no-hint', 'level': 1}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AssistanceRecord.objects.exists())
        self.assertEqual(len(search(self.scope)['results']), 1)

    def test_t3_05_source_status_expiry_and_user_are_live_not_cached(self):
        article = Article.objects.create(author=self.teacher, title='external', content='reviewed', status='approved')
        revision = material(self, text=article.content, source_type='article', source_id=article.pk)
        before = task_policy_stamp(self.task)
        article.status = 'rejected'
        article.save()
        self.assertNotEqual(before, task_policy_stamp(self.task))
        before = task_policy_stamp(self.task)
        revision.recheck_due_at = timezone.now() - timedelta(seconds=1)
        revision.save()
        self.assertNotEqual(before, task_policy_stamp(self.task))
        type(self.student).objects.filter(pk=self.student.pk).update(is_active=False)
        with self.assertRaises(NotFound):
            search(self.scope)

    def test_t3_15_model_context_and_events_exclude_hidden_content(self):
        for kind in ('teacher_answer', 'grading_secret', 'student_analysis'):
            material(self, kind, text=f'NEVER-{kind}')
        captured = {}
        def inspect(**kwargs):
            captured.update(kwargs['model_context'])
            raise ConnectionError()
        with patch('teaching_agent.api_tutoring._run_with_budget', side_effect=inspect):
            self.tutor('privacy')
        serialized = str(captured) + str(list(LearningBehaviorEvent.objects.values('metadata'))) + str(list(AssistanceRecord.objects.values('content_ref', 'note')))
        self.assertNotIn('NEVER-', serialized)
        self.assertNotIn('STALE-COPY-SECRET', serialized)
        self.assertNotIn('REVIEWED-DIRECTION', serialized)
        self.assertNotIn('hidden_checks', serialized)

    def test_t3_14_models_off_submission_unlocks_analysis_then_revocation_denies(self):
        revision = material(self, 'student_analysis', text='REVIEWED-ANALYSIS')
        StudentAnalysis.objects.create(task=self.task, title='analysis', content='STALE-ANALYSIS',
                                       content_ref=material_ref(revision), version='m3-test')
        self.task.validator = {'type': 'structured_rules', 'version': 'test', 'manual_required': False,
                               'checks': [{'id': 'answer', 'field': 'answer', 'equals': 'safe'}]}
        self.task.save()
        self.assertEqual(self.client.get(self.base + 'analysis/').status_code, 403)
        with patch('teaching_agent.api_tutoring._default_provider_call', side_effect=AssertionError('Models disabled')):
            response = self.client.post(f'/api/skill-review/attempts/{self.attempt.attempt_id}/submit/',
                                       {'client_submission_id': 'no-model', 'payload': {'answer': 'safe'}}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        unlocked = self.client.get(self.base + 'analysis/')
        self.assertEqual(unlocked.status_code, 200, unlocked.data)
        self.assertEqual(unlocked.data['content'], revision.source_snapshot)
        self.assertNotIn('REVIEWED-ANALYSIS', str(search(self.scope)))
        Material.objects.filter(pk=revision.material_id).update(revoked_at=timezone.now())
        denied = self.client.get(self.base + 'analysis/')
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn('REVIEWED-ANALYSIS', str(denied.data))
        self.assertTrue(AssistanceRecord.objects.filter(kind='analysis_view', shown=True).exists())

    def test_unregistered_legacy_card_cannot_bypass_registered_task(self):
        self.card.material_ref = 'old/unverified.md'
        self.card.save()
        with patch('teaching_agent.api_tutoring._run_with_budget', side_effect=ConnectionError()):
            response = self.tutor('legacy-card')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['response']['hint_level'], 0)
        self.assertNotIn('STALE-COPY-SECRET', str(response.data))
