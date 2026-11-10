"""Explicit model-driven canary loop, pure owners only; never uses AgentRun or a database."""
import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from data_security.adapters.django.canary_tools import CanaryToolRegistry
from data_security.contracts import CanarySeed, Environment, Outlet, ProtectionContext, ProtectionError, Purpose, ReasonCode
from data_security.tests.fixtures import dto, examples
from data_security.tests.test_phase6_canary import text
from data_security.tests.test_phase6_canary_tool_protocol import ToolProtocolFixture, tool_call, tool_response
from .gateway import AgentGateway


class ModelCanaryGatewayTests(ToolProtocolFixture, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.user = SimpleNamespace(is_authenticated=True, is_active=True, pk=7)
        self.other = SimpleNamespace(is_authenticated=True, is_active=True, pk=8)
        self.seed = examples()[CanarySeed]
        self.owner = replace(examples()[ProtectionContext], actor_ref='user/7', outlet=Outlet.AUDIT,
            environment=Environment.TEST, purpose=Purpose.SECURITY_AUDIT)
        self.denied = dto(ProtectionError, code=ReasonCode.AUTHORIZATION_DENIED,
            retryable=False, trace_id='canary/model-denied')
        self.grants = {('canary.plant', self.seed.seed_id), ('canary.check', 'output/1')}
        def resolve(name, ref, user):
            if user is not self.user or (name, ref) not in self.grants:
                return self.denied
            return self.owner
        self.resolve = Mock(side_effect=resolve)
        self.plant = Mock(return_value=self.seed)
        self.load = Mock(return_value=text('Authorized synthetic output.'))
        self.checker = Mock(check=Mock(return_value=()))
        self.registry = CanaryToolRegistry(plant=self.plant, checker=self.checker,
            resolve_context=self.resolve, load_output=self.load)
        self.port = self.adapter()
        self.provider = self.handle(self.port)
        self.state, self.retrieval, self.verifier = Mock(), Mock(), Mock()
        self.runtime = AgentGateway(state_store=self.state, retrieval_service=self.retrieval,
            verifier=self.verifier, security_tools=self.registry, security_provider=self.provider)
        self.wire_bodies = []

    def run_model(self, responses, *, user=None, max_rounds=4):
        pending = iter(responses)
        def transport(url, *, body, **kwargs):
            self.wire_bodies.append(body)
            return json.dumps(next(pending)).encode()
        with patch.object(self.port, '_http', side_effect=transport) as send:
            result = self.runtime.run_security_task(user=self.user if user is None else user,
                message='Perform the explicitly authorized synthetic checks.', max_rounds=max_rounds)
        self.assertFalse(self.state.mock_calls)
        self.assertFalse(self.retrieval.mock_calls)
        self.assertFalse(self.verifier.mock_calls)
        self.assertIsNone(self.runtime.service)
        return result, send.call_count

    def test_model_chooses_check_then_plant_serially_and_only_metadata_round_trips(self):
        calls = [tool_call(call_id='check_1'), tool_call('canary_plant',
            {'seed_id': self.seed.seed_id}, call_id='plant_1')]
        final = tool_response(calls=[], content='Model prose must never enter AgentRun or the task output.', finish='stop')
        result, count = self.run_model([tool_response(calls=calls), final])
        self.assertEqual(count, 2)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['results'][0], {'status': 'clean', 'alert_count': 0})
        self.assertEqual(set(result['results'][1]), {'status', 'seed_id'})
        self.assertEqual(result['results'][1]['status'], 'planted')
        self.assertEqual([item.args[0] for item in self.resolve.call_args_list], ['canary.check', 'canary.plant'])
        self.assertTrue(all(item.args[2] is self.user for item in self.resolve.call_args_list))
        self.plant.assert_called_once()
        self.load.assert_called_once_with('output/1', self.owner)
        self.checker.check.assert_called_once_with(payload=self.load.return_value, context=self.owner)
        history = self.wire_bodies[1]['messages']
        self.assertEqual([item['role'] for item in history], ['system', 'user', 'assistant', 'tool', 'tool'])
        self.assertEqual([history[3]['tool_call_id'], history[4]['tool_call_id']], ['check_1', 'plant_1'])
        self.assertEqual(json.loads(history[3]['content']), result['results'][0])
        self.assertEqual(json.loads(history[4]['content']), result['results'][1])
        self.assertFalse('content' in result)
        self.assertEqual([item['function']['name'] for item in self.wire_bodies[0]['tools']],
            ['canary_plant', 'canary_check'])
        self.assertEqual([item['name'] for item in self.runtime.available_security_tools()],
            ['canary.plant', 'canary.check'])

    def test_model_may_choose_no_tool_without_background_or_fixed_calls(self):
        result, count = self.run_model([tool_response(calls=[], content='No authorized action needed.', finish='stop')])
        self.assertEqual(result, {'status': 'completed', 'results': []})
        self.assertEqual(count, 1)
        self.resolve.assert_not_called()
        self.load.assert_not_called()
        self.plant.assert_not_called()

    def test_current_owner_rechecks_revocation_with_same_cached_user_for_each_call(self):
        def plant(**kwargs):
            self.grants.remove(('canary.check', 'output/1'))
            return self.seed
        self.plant.side_effect = plant
        calls = [tool_call('canary_plant', {'seed_id': self.seed.seed_id}, 'plant_1'), tool_call(call_id='check_1')]
        result, count = self.run_model([tool_response(calls=calls)])
        self.assertEqual(result, {'status': 'error', 'code': 'AUTHORIZATION_DENIED'})
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.resolve.call_count, 2)
        self.assertEqual(count, 1)
        self.plant.assert_called_once()
        self.load.assert_not_called()
        self.checker.check.assert_not_called()

    def test_another_user_cannot_borrow_authority_and_no_automatic_retry_occurs(self):
        result, count = self.run_model([tool_response()], user=self.other)
        self.assertEqual(result, {'status': 'error', 'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(count, 1)
        self.resolve.assert_called_once_with('canary.check', 'output/1', self.other)
        self.load.assert_not_called()
        self.plant.assert_not_called()

    def test_unknown_bad_second_call_rejects_entire_batch_before_any_owner(self):
        for bad in (tool_call('canary.check'), tool_call('unknown'),
                    tool_call(arguments={'artifact_ref': 'output/1', 'user': 'admin'}),
                    tool_call(arguments={'artifact_ref': 'output/1', 'payload': 'synthetic-body'})):
            bad['id'] = 'bad_2'
            result, count = self.run_model([tool_response(calls=[tool_call(), bad])])
            self.assertEqual(result['status'], 'error')
            self.assertEqual(count, 1)
        self.resolve.assert_not_called()
        self.load.assert_not_called()
        self.plant.assert_not_called()

    def test_only_reference_semantics_are_validated_by_original_registry(self):
        for name, args in (('canary_check', {'artifact_ref': '../outside'}),
                           ('canary_check', {'artifact_ref': 'https://example.invalid'}),
                           ('canary_plant', {'seed_id': 'invalid-reference'})):
            result, count = self.run_model([tool_response(calls=[tool_call(name, args)])])
            self.assertEqual(result['status'], 'error')
            self.assertEqual(count, 1)
        self.resolve.assert_not_called()
        self.load.assert_not_called()
        self.plant.assert_not_called()

    def test_round_limit_stops_before_last_round_side_effect_without_retry(self):
        responses = [tool_response(calls=[tool_call(call_id='call_' + str(i))]) for i in range(3)]
        result, count = self.run_model(responses, max_rounds=3)
        self.assertEqual(result, {'status': 'error', 'code': 'LIMIT_EXCEEDED'})
        self.assertEqual(count, 3)
        self.assertEqual(self.resolve.call_count, 2)
        self.assertEqual(self.load.call_count, 2)
        self.plant.assert_not_called()

    def test_reused_call_id_is_rejected_instead_of_replayed(self):
        result, count = self.run_model([tool_response(), tool_response()])
        self.assertEqual(result, {'status': 'error', 'code': 'INVALID_VALUE'})
        self.assertEqual(count, 2)
        self.resolve.assert_called_once()
        self.load.assert_called_once()

    def test_disabled_or_unauthenticated_runtime_never_calls_model_or_owners(self):
        disabled = AgentGateway(state_store=self.state, retrieval_service=self.retrieval, verifier=self.verifier)
        self.assertEqual(disabled.run_security_task(user=self.user, message='safe'),
            {'status': 'error', 'code': 'CANARY_TOOLS_DISABLED'})
        disabled.security_tools = self.registry
        self.assertEqual(disabled.run_security_task(user=self.user, message='safe'),
            {'status': 'error', 'code': 'SECURITY_PROVIDER_DISABLED'})
        with patch.object(self.provider, 'chat_tools') as model:
            for user in (None, SimpleNamespace(is_authenticated=False, is_active=True),
                         SimpleNamespace(is_authenticated=True, is_active=False)):
                self.assertEqual(self.runtime.run_security_task(user=user, message='safe'),
                    {'status': 'error', 'code': 'AUTHORIZATION_DENIED'})
            for rounds in (0, 9, True, '4'):
                self.assertEqual(self.runtime.run_security_task(user=self.user, message='safe', max_rounds=rounds),
                    {'status': 'error', 'code': 'LIMIT_EXCEEDED'})
            self.assertEqual(self.runtime.run_security_task(user=self.user, message=None),
                {'status': 'error', 'code': 'INVALID_TYPE'})
            model.assert_not_called()
        self.resolve.assert_not_called()
        self.assertFalse(self.state.mock_calls)

    def test_exception_is_body_free_and_no_model_or_tool_retry_occurs(self):
        with patch.object(self.port, '_http', side_effect=RuntimeError('synthetic body-bearing provider error')) as send:
            result = self.runtime.run_security_task(user=self.user, message='safe')
        self.assertEqual(result, {'status': 'error', 'code': 'SECURITY_TASK_FAILED'})
        send.assert_called_once()
        self.resolve.assert_not_called()
        self.resolve.side_effect = RuntimeError('synthetic body-bearing owner error')
        result, count = self.run_model([tool_response()])
        self.assertEqual(result, {'status': 'error', 'code': 'CANARY_TOOL_FAILED'})
        self.assertEqual(count, 1)
        self.resolve.assert_called_once()
        self.load.assert_not_called()

    def test_synchronous_owner_is_not_invoked_inside_the_model_event_loop(self):
        original = self.resolve.side_effect
        def resolve(name, ref, user):
            with self.assertRaises(RuntimeError):
                asyncio.get_running_loop()
            return original(name, ref, user)
        self.resolve.side_effect = resolve
        result, count = self.run_model([tool_response(), tool_response(calls=[], content='Done.', finish='stop')])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(count, 2)
        self.resolve.assert_called_once()

    def test_task_never_logs_model_text_arguments_or_tool_results(self):
        with patch('logging.Logger._log') as log:
            result, count = self.run_model([tool_response(), tool_response(
                calls=[], content='Synthetic private prose.', finish='stop')])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(count, 2)
        log.assert_not_called()
        self.assertFalse('Synthetic private prose.' in str(result))

    def test_protocol_aliases_are_only_adaptation_and_original_dispatch_remains_closed(self):
        definitions = self.registry.model_definitions()
        definitions[0]['function']['parameters']['required'].append('user')
        self.assertEqual(self.registry.model_definitions()[0]['function']['parameters']['required'], ['seed_id'])
        for name in ('canary.plant', 'plant', 'unknown', None, []):
            self.assertEqual(self.registry.run_model_tool(name, arguments={}, user=self.user),
                {'status': 'error', 'code': 'UNSUPPORTED_SCOPE'})
        self.resolve.assert_not_called()
        self.assertEqual(self.runtime.run_security_tool('canary.check', arguments={'artifact_ref': 'output/1'},
            user=self.user), {'status': 'clean', 'alert_count': 0})
        self.resolve.assert_called_once_with('canary.check', 'output/1', self.user)
        self.assertFalse(self.state.mock_calls)
