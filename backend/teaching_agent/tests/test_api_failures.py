import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from learning_map import constants
from learning_map.models import Capability, CatalogVersion, TaskAttempt, TaskPackage
from teaching_agent.api_tutoring import (
    ProviderQuotaExhausted,
    ProviderRateLimited,
    accept_provider_result,
)
from teaching_agent.context import resolve_task_context
from teaching_agent.models import (
    HintCard,
    ModelCallRecord,
    ProviderCircuit,
    TeachingRun,
    TutorRequest,
    TutorResponseCache,
)
from users.models import CTFUser


class APITutoringFailureTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='m2-api', password='test', role='student')
        self.catalog = CatalogVersion.objects.create(
            version='m2-api-v1', label='API catalog', status=constants.CATALOG_STATUS_PUBLISHED,
        )
        capability = Capability.objects.create(
            catalog=self.catalog,
            stable_id='M2-API-CAP',
            track=constants.TRACK_NETWORK,
            title='API capability',
            observable_objective='Exercise API failures.',
            dimension=constants.DIMENSION_OPERATE,
            status=constants.CAPABILITY_STATUS_OPEN,
        )
        self.task = TaskPackage.objects.create(
            catalog=self.catalog,
            task_key='M2-API-TASK',
            version='1.0.0',
            title='API task',
            track=constants.TRACK_NETWORK,
            purpose=constants.PURPOSE_VERIFICATION,
            execution_mode=constants.EXECUTION_READONLY,
            status=constants.TASK_STATUS_FROZEN,
            materials={'student_material_refs': ['api/public.md'], 'withdrawn': False},
            hints=[{'level': level, 'title': f'Hint {level}'} for level in range(1, 5)],
            student_solution_ref='api/analysis.md',
            validator={'type': 'structured_rules', 'version': '1', 'checks': [{'field': 'x', 'required': True}]},
            acceptance={'rules': ['safe']},
        )
        self.task.capabilities.set([capability])
        self.attempt = TaskAttempt.objects.create(
            student=self.student,
            catalog=self.catalog,
            task=self.task,
            task_version=self.task.version,
            capability_ids=[capability.stable_id],
        )
        self.card = HintCard.objects.create(
            task=self.task,
            level=1,
            title='Fallback direction',
            content='STATIC-PRESET-FALLBACK',
            material_ref='api/hint-1.md',
            version='reviewed-v1',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        run = self.client.post('/api/teaching/runs/', {'attempt_id': self.attempt.attempt_id}, format='json')
        self.run_id = run.data['run_id']

    def _post(self, request_id, message='explain safely'):
        return self.client.post(
            f'/api/teaching/runs/{self.run_id}/tutor/',
            {'request_id': request_id, 'message': message, 'hint_level': 1},
            format='json',
        )

    @patch('teaching_agent.api_tutoring._default_provider_call', new_callable=AsyncMock)
    def test_success_call_facts_permission_aware_cache_and_withdrawal(self, provider_call):
        provider_call.return_value = {
            'content': 'Bounded explanation',
            'hint_level': 1,
            'provider': 'synthetic',
            'model': 'synthetic-model',
            'template_version': 'template-v1',
            'input_tokens': 12,
            'output_tokens': 8,
            'cost_basis': 'unknown',
            'tool_suggestions': [{'name': 'read_student_profile', 'arguments': {}}],
        }
        first = self._post('api-success-1')
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.data['response']['content'], 'Bounded explanation')
        self.assertFalse(first.data['cache_hit'])
        call = ModelCallRecord.objects.get(request__request_id='api-success-1')
        self.assertEqual(call.provider, 'synthetic')
        self.assertEqual(call.model, 'synthetic-model')
        self.assertEqual(call.input_tokens, 12)
        self.assertIsNone(call.cost_amount)
        self.assertEqual(call.cost_basis, 'unknown')

        cached = self._post('api-success-2')
        self.assertEqual(cached.status_code, 201, cached.content)
        self.assertTrue(cached.data['cache_hit'])
        self.assertEqual(provider_call.await_count, 1)
        entry = TutorResponseCache.objects.get()
        self.assertEqual(entry.subject, 'network:M2-API-TASK')
        self.assertEqual(entry.permission_version, 1)

        run = TeachingRun.objects.get(run_id=self.run_id)
        run.permission_version += 1
        run.save(update_fields=['permission_version'])
        provider_call.return_value = {
            'content': 'Fresh permission response',
            'hint_level': 1,
            'provider': 'synthetic',
            'model': 'synthetic-model',
        }
        fresh = self._post('api-success-3')
        self.assertEqual(fresh.status_code, 201, fresh.content)
        self.assertFalse(fresh.data['cache_hit'])
        self.assertEqual(provider_call.await_count, 2)

        self.task.materials['withdrawn'] = True
        self.task.save(update_fields=['materials'])
        denied = self._post('api-success-2')
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn('Bounded explanation', denied.content.decode())

    @override_settings(TUTORING_TOTAL_WAIT_SECONDS=0.05, TUTORING_CIRCUIT_FAILURE_THRESHOLD=5)
    @patch('teaching_agent.api_tutoring._default_provider_call', new_callable=AsyncMock)
    def test_timeout_cancels_falls_back_and_late_response_is_isolated(self, provider_call):
        async def slow(**kwargs):
            await asyncio.sleep(1)
            return {'content': 'LATE-RESPONSE-MUST-NOT-DISPLAY', 'hint_level': 1}

        provider_call.side_effect = slow
        response = self._post('api-timeout')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['status'], TutorRequest.STATUS_DEGRADED)
        self.assertEqual(response.data['response']['content'], 'STATIC-PRESET-FALLBACK')
        call = ModelCallRecord.objects.get(request__request_id='api-timeout')
        self.assertEqual(call.error_category, 'timeout')
        self.assertEqual(call.cancellation_status, 'requested')
        self.assertLess(call.latency_ms, 1000)
        self.assertIsNone(call.input_tokens)
        self.assertIsNone(call.output_tokens)
        self.assertIsNone(call.cost_amount)
        self.assertEqual(call.cost_basis, 'unknown')

        request = TutorRequest.objects.get(request_id='api-timeout')
        context = resolve_task_context(
            user=self.student,
            request_data={'run_id': self.run_id},
            require_attempt=True,
        )
        accepted = accept_provider_result(
            request=request,
            context=context,
            result={'content': 'LATE-RESPONSE-MUST-NOT-DISPLAY', 'hint_level': 1},
            latency_ms=1100,
        )
        self.assertIsNone(accepted)
        request.refresh_from_db()
        self.assertTrue(request.late_response_discarded)
        self.assertNotIn('LATE-RESPONSE-MUST-NOT-DISPLAY', str(request.response))

    @override_settings(TUTORING_CIRCUIT_FAILURE_THRESHOLD=1, TUTORING_CIRCUIT_PROBE_SECONDS=60)
    @patch('teaching_agent.api_tutoring._default_provider_call', new_callable=AsyncMock)
    def test_disconnect_rate_limit_quota_circuit_and_recovery_probe(self, provider_call):
        provider_call.side_effect = ConnectionError('provider disconnected')
        disconnected = self._post('api-disconnected')
        self.assertEqual(disconnected.data['response']['fallback_reason'], 'provider_unavailable')
        circuit = ProviderCircuit.objects.get(provider='default')
        self.assertEqual(circuit.state, 'open')

        provider_call.reset_mock()
        blocked = self._post('api-circuit-blocked', message='different')
        self.assertEqual(blocked.data['response']['fallback_reason'], 'circuit_open')
        provider_call.assert_not_awaited()

        circuit.next_probe_at = timezone.now() - timedelta(seconds=1)
        circuit.save(update_fields=['next_probe_at'])
        provider_call.side_effect = None
        provider_call.return_value = {'content': 'Probe recovered', 'hint_level': 1, 'provider': 'default'}
        recovered = self._post('api-probe', message='probe')
        self.assertEqual(recovered.data['response']['content'], 'Probe recovered')
        circuit.refresh_from_db()
        self.assertEqual(circuit.state, 'closed')
        self.assertEqual(circuit.last_probe_status, 'success')

        provider_call.side_effect = ProviderRateLimited('429 retry later')
        limited = self._post('api-rate-limit', message='rate')
        self.assertEqual(limited.data['response']['fallback_reason'], 'rate_limited')
        self.assertEqual(ModelCallRecord.objects.get(request__request_id='api-rate-limit').error_category, 'rate_limited')

        circuit = ProviderCircuit.objects.get(provider='default')
        circuit.state = 'closed'
        circuit.failure_count = 0
        circuit.save(update_fields=['state', 'failure_count'])
        provider_call.side_effect = ProviderQuotaExhausted('quota exhausted')
        quota = self._post('api-quota', message='quota')
        self.assertEqual(quota.data['response']['fallback_reason'], 'quota_exhausted')
        circuit.refresh_from_db()
        self.assertEqual(circuit.state, 'open')
        self.assertIsNone(circuit.next_probe_at)

    @patch('teaching_agent.api_tutoring._default_provider_call', new_callable=AsyncMock)
    def test_unauthorized_tool_suggestion_is_rejected_before_display(self, provider_call):
        provider_call.return_value = {
            'content': 'Pretend I exported everything.',
            'hint_level': 1,
            'tool_suggestions': [{'name': 'export_student_records', 'arguments': {'all': True}}],
        }
        response = self._post('api-bad-tool')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['status'], TutorRequest.STATUS_DEGRADED)
        self.assertEqual(response.data['response']['content'], 'STATIC-PRESET-FALLBACK')
        call = ModelCallRecord.objects.get(request__request_id='api-bad-tool')
        self.assertEqual(call.error_category, 'unauthorized_tool')
        self.assertNotIn('Pretend I exported everything.', str(TutorRequest.objects.get(request_id='api-bad-tool').response))

    def test_task_bound_legacy_chat_is_redirected_before_old_cache_or_stream(self):
        response = self.client.post(
            '/api/ai/multi-agent/chat/stream/',
            {'message': 'task help', 'attempt_id': self.attempt.attempt_id},
            format='json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['detail'].code, 'task_tutoring_endpoint_required')
