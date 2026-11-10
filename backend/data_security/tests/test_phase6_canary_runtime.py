"""Reference-only tool boundary; synthetic owners do not stand in for business ACL."""
from dataclasses import replace
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from data_security.adapters.django.canary_tools import CanaryToolRegistry
from data_security.contracts import Environment, Outlet, ProtectionError, ReasonCode, TableSnapshot
from data_security.tests.fixtures import dto, examples
from data_security.tests.test_phase6_canary import CanaryToolFixture, text


class CanaryRuntimeTests(CanaryToolFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.user = SimpleNamespace(is_authenticated=True, is_active=True, pk=7)
        self.resolve = Mock(return_value=self.context)
        self.load = Mock(return_value=text('safe synthetic output'))
        self.registry = CanaryToolRegistry(plant=self.service.plant, checker=self.service,
            resolve_context=self.resolve, load_output=self.load)

    def run_tool(self, name='canary.check', arguments=None, user=None):
        return self.registry.run(name, arguments=arguments if arguments is not None else
            {'artifact_ref': 'output/1'}, user=user if user is not None else self.user)

    def test_definitions_are_closed_and_do_not_expose_seed_values_or_authority(self):
        definitions = self.registry.definitions()
        self.assertEqual([item['name'] for item in definitions], ['canary.plant', 'canary.check'])
        for item, field in zip(definitions, ('seed_id', 'artifact_ref')):
            self.assertEqual(item['input_schema']['required'], [field])
            self.assertEqual(set(item['input_schema']['properties']), {field})
            self.assertIs(item['input_schema']['additionalProperties'], False)
        definitions[0]['input_schema']['required'].append('context')
        self.assertEqual(self.registry.definitions()[0]['input_schema']['required'], ['seed_id'])
        self.resolve.assert_not_called()
        self.load.assert_not_called()
        self.plant.assert_not_called()

    def test_plant_returns_only_metadata_and_check_reads_owner_output(self):
        result = self.run_tool('canary.plant', {'seed_id': self.seed.seed_id})
        self.assertEqual(result, {'status': 'planted', 'seed_id': self.seed.seed_id})
        self.resolve.assert_called_once_with('canary.plant', self.seed.seed_id, self.user)
        self.load.assert_not_called()
        self.assertEqual(len(self.packets), 1)
        self.resolve.return_value = replace(self.context, outlet=Outlet.MODEL)
        self.load.return_value = self.packets[0]
        self.assertEqual(self.run_tool(), {'status': 'alert', 'alert_count': 1})
        self.load.assert_called_once_with('output/1', self.resolve.return_value)
        self.assertEqual(self.events[0].counts, (('hit', 3),))
        self.load.return_value = text('[EMAIL] [IP] [CARD]')
        self.assertEqual(self.run_tool(), {'status': 'clean', 'alert_count': 0})
        self.assertEqual(len(self.events), 1)

    def test_model_cannot_supply_payload_context_authority_or_paths(self):
        cases = [None, False, [], {}, {'artifact_ref': 'output/1', 'payload': 'text'},
            {'artifact_ref': 'output/1', 'context': self.context},
            {'artifact_ref': 'output/1', 'user': self.user},
            {'artifact_ref': '../secret'}, {'artifact_ref': '/tmp/secret'},
            {'artifact_ref': 'https://example.invalid'}, {'artifact_ref': 'x' * 161},
            {'artifact_ref': False}, {'artifact_ref': 'output/1', 'authorization_ref': 'approved'}]
        for arguments in cases:
            with self.subTest(case=type(arguments).__name__):
                self.assertEqual(self.registry.run('canary.check', arguments=arguments,
                    user=self.user)['status'], 'error')
        for seed_id in ('f' * 31, 'F' * 32, 'g' * 32, True):
            self.assertEqual(self.run_tool('canary.plant', {'seed_id': seed_id})['status'], 'error')
        for name in ('__dict__', 'plant', 'canary.retire', None, []):
            self.assertEqual(self.run_tool(name)['code'], 'UNSUPPORTED_SCOPE')
        self.resolve.assert_not_called()
        self.load.assert_not_called()
        self.plant.assert_not_called()

    def test_anonymous_or_inactive_principal_never_reaches_owner(self):
        for user in (None, SimpleNamespace(is_authenticated=False, is_active=True),
                     SimpleNamespace(is_authenticated=True, is_active=False)):
            self.assertEqual(self.registry.run('canary.check', arguments={'artifact_ref': 'output/1'},
                user=user)['code'], 'AUTHORIZATION_DENIED')
        self.resolve.assert_not_called()
        self.load.assert_not_called()

    def test_current_owner_is_called_each_time_and_denial_precedes_loading(self):
        self.resolve.return_value = replace(self.context, outlet=Outlet.LOG)
        self.assertEqual(self.run_tool()['status'], 'clean')
        self.resolve.return_value = dto(ProtectionError, code=ReasonCode.AUTHORIZATION_DENIED,
            retryable=False, trace_id='canary/current-owner')
        self.assertEqual(self.run_tool()['code'], 'AUTHORIZATION_DENIED')
        self.assertEqual(self.resolve.call_count, 2)
        self.assertEqual(self.load.call_count, 1)
        for invalid in (True, None, replace(self.context, environment=Environment.PRODUCTION)):
            self.resolve.return_value = invalid
            self.assertEqual(self.run_tool()['code'], 'AUTHORIZATION_DENIED')
        self.assertEqual(self.load.call_count, 1)
        self.plant.assert_not_called()

    def test_loader_failure_and_tool_failure_are_not_clean_or_planted(self):
        self.resolve.return_value = replace(self.context, outlet=Outlet.EXPORT)
        error = dto(ProtectionError, code=ReasonCode.SCOPE_INCOMPLETE,
            retryable=False, trace_id='canary/output')
        self.load.return_value = error
        self.assertEqual(self.run_tool(), {'status': 'error', 'code': 'SCOPE_INCOMPLETE'})
        self.assertEqual(self.events, [])
        checker = self.registry.checker = Mock()
        self.load.return_value = text('safe')
        for invalid in (None, False, [], (False,)):
            checker.check.return_value = invalid
            self.assertEqual(self.run_tool()['code'], 'AUDIT_UNAVAILABLE')
        checker.check.return_value = error
        self.assertEqual(self.run_tool()['code'], 'SCOPE_INCOMPLETE')
        self.resolve.return_value = self.context
        self.registry.plant = Mock()
        for invalid in (None, True, replace(self.seed, seed_id='f' * 32)):
            self.registry.plant.return_value = invalid
            self.assertEqual(self.run_tool('canary.plant', {'seed_id': self.seed.seed_id})['code'],
                'SOURCE_NOT_APPROVED')
        self.registry.plant.return_value = error
        self.assertEqual(self.run_tool('canary.plant', {'seed_id': self.seed.seed_id})['code'],
            'SCOPE_INCOMPLETE')

    def test_owner_exceptions_are_fixed_errors_without_body_or_retry(self):
        self.resolve.side_effect = RuntimeError('synthetic body must not enter tool result')
        self.assertEqual(self.run_tool(), {'status': 'error', 'code': 'CANARY_TOOL_FAILED'})
        self.resolve.assert_called_once()
        self.load.assert_not_called()
        self.resolve.side_effect = None
        self.resolve.return_value = replace(self.context, outlet=Outlet.EXPORT)
        self.load.side_effect = RuntimeError('synthetic body must not enter tool result')
        self.assertEqual(self.run_tool(), {'status': 'error', 'code': 'CANARY_TOOL_FAILED'})
        self.load.assert_called_once()
        self.load.side_effect = None
        self.registry.checker = Mock()
        self.registry.checker.check.side_effect = RuntimeError('synthetic body')
        self.assertEqual(self.run_tool(), {'status': 'error', 'code': 'CANARY_TOOL_FAILED'})
        self.registry.checker.check.assert_called_once()
        self.registry.plant = Mock(side_effect=RuntimeError('synthetic body'))
        self.resolve.return_value = self.context
        self.assertEqual(self.run_tool('canary.plant', {'seed_id': self.seed.seed_id}),
                         {'status': 'error', 'code': 'CANARY_TOOL_FAILED'})
        self.registry.plant.assert_called_once()

    def test_owner_decoded_table_reaches_checker_without_serialization_or_copy(self):
        self.resolve.return_value = replace(self.context, outlet=Outlet.EXPORT)
        snapshot = examples()[TableSnapshot]
        self.load.return_value = snapshot
        self.registry.checker = Mock()
        self.registry.checker.check.return_value = ()
        self.assertEqual(self.run_tool(), {'status': 'clean', 'alert_count': 0})
        self.registry.checker.check.assert_called_once_with(payload=snapshot,
            context=self.resolve.return_value)
        self.assertIs(self.registry.checker.check.call_args.kwargs['payload'], snapshot)
