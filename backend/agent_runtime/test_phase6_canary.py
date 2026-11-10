"""Runtime dispatch with explicit synthetic grants and the real isolated PG ledger."""
from dataclasses import replace
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from audit.models import AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
from audit.test_phase6_authenticated_chain import AuditChainFixture
from data_security.adapters.django.canary_tools import CanaryToolRegistry
from data_security.application.canary import CanaryTools
from data_security.contracts import (
    BASELINE_LIMITS, CanarySeed, Environment, Outlet, PolicyBinding, ProtectionContext,
    ProtectionError, Purpose, ReasonCode, SecurityEventV2, canonical_bytes,
)
from data_security.tests.fixtures import dto, examples
from data_security.tests.test_phase6_canary import text
from .gateway import AgentGateway
from .models import AgentRun
from .tests import FakeLearningService
from .tool_registry import LearningToolRegistry


class CanaryGatewayDisabledTests(SimpleTestCase):
    def test_default_gateway_does_not_register_or_discover_security_tools(self):
        gateway = AgentGateway(state_store=Mock(), retrieval_service=Mock(), verifier=Mock())
        self.assertEqual(gateway.available_security_tools(), [])
        self.assertEqual(gateway.run_security_tool('canary.plant', arguments={}, user=None),
                         {'status': 'error', 'code': 'CANARY_TOOLS_DISABLED'})
        gateway.state_store.create_run.assert_not_called()
        gateway.retrieval_service.retrieve.assert_not_called()
        self.assertIsNone(gateway.service)


class CanaryGatewayTests(AuditChainFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(username='canary-runtime', password='pass12345')
        self.other = User.objects.create_user(username='canary-other', password='pass12345', role='admin')
        self.seed = examples()[CanarySeed]
        self.owner = replace(examples()[ProtectionContext], actor_ref=f'user/{self.user.pk}',
            object_ref=self.seed.target_ref, object_version=self.seed.target_version,
            outlet=Outlet.AUDIT, purpose=Purpose.SECURITY_AUDIT)
        self.check_context = replace(self.owner, outlet=Outlet.EXPORT,
            object_ref='synthetic/output/1', object_version='1', trace_id='canary/runtime/1')
        self.grants = {('canary.plant', self.seed.seed_id): self.owner,
                       ('canary.check', 'output/1'): self.check_context}
        self.denied = dto(ProtectionError, code=ReasonCode.AUTHORIZATION_DENIED,
            retryable=False, trace_id='canary/runtime/denied')
        def resolve(operation, ref, user):
            # Explicit synthetic grants; administrator role alone cannot authorize.
            if user.pk != self.user.pk or not User.objects.filter(pk=user.pk, is_active=True).exists():
                return self.denied
            return self.grants.get((operation, ref), self.denied)
        self.resolve = Mock(side_effect=resolve)
        self.packets = []
        def plant(seed, packet, context):
            self.packets.append(packet)
            return seed
        self.tools = CanaryTools(seeds=(self.seed,), environment=Environment.TEST, domain=self.seed.domain,
            limits=BASELINE_LIMITS, policy_binding=examples()[PolicyBinding],
            authorize=lambda operation, context, seed: context, plant_target=plant, audit=self.gateway,
            clock=timezone.now, event_id=lambda: 'canary/runtime/' + str(SecurityAuditRecord.objects.count() + 1))
        self.load = Mock(return_value=text('safe synthetic output'))
        self.registry = CanaryToolRegistry(plant=self.tools.plant, checker=self.tools,
            resolve_context=self.resolve, load_output=self.load)
        self.runtime = AgentGateway(security_tools=self.registry)

    def test_explicit_runtime_plant_and_check_confirm_new_chain_without_body_results(self):
        self.assertEqual([item['name'] for item in self.runtime.available_security_tools()],
                         ['canary.plant', 'canary.check'])
        result = self.runtime.run_security_tool('canary.plant',
            arguments={'seed_id': self.seed.seed_id}, user=self.user)
        self.assertEqual(result, {'status': 'planted', 'seed_id': self.seed.seed_id})
        self.assertEqual(len(self.packets), 1)
        self.assertEqual(self.runtime.run_security_tool('canary.check',
            arguments={'artifact_ref': 'output/1'}, user=self.user), {'status': 'clean', 'alert_count': 0})
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.load.return_value = self.packets[0]
        self.assertEqual(self.runtime.run_security_tool('canary.check',
            arguments={'artifact_ref': 'output/1'}, user=self.user), {'status': 'alert', 'alert_count': 1})
        self.load.assert_called_with('output/1', self.check_context)
        receipt = self.sink.verify('ds.audit.v2')
        self.assertEqual(receipt.sequence, 1)
        event = SecurityEventV2.from_wire(SecurityAuditRecord.objects.get(event_id=receipt.event_id).event)
        self.assertEqual(event.actor_ref, self.owner.actor_ref)
        self.assertEqual(event.object_ref, self.seed.target_ref)
        self.assertEqual(event.correlation_ref, self.check_context.trace_id)
        self.assertEqual(event.counts, (('hit', 3),))
        self.assertIn('outlet/export', event.algorithm_versions)
        for value in self.packets[0].tree.to_value()['values'].values():
            self.assertNotIn(value.encode(), canonical_bytes(event))
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
        self.assertEqual(AgentRun.objects.count(), 0)
        self.assertIsNone(self.runtime.service)

    def test_other_user_unknown_reference_and_revoked_grant_do_not_load_or_plant(self):
        for user, arguments in ((self.other, {'artifact_ref': 'output/1'}),
                                (self.user, {'artifact_ref': 'output/unknown'})):
            self.assertEqual(self.runtime.run_security_tool('canary.check',
                arguments=arguments, user=user)['code'], 'AUTHORIZATION_DENIED')
        self.assertEqual(self.runtime.run_security_tool('canary.plant',
            arguments={'seed_id': self.seed.seed_id}, user=self.other)['code'], 'AUTHORIZATION_DENIED')
        del self.grants[('canary.plant', self.seed.seed_id)]
        self.assertEqual(self.runtime.run_security_tool('canary.plant',
            arguments={'seed_id': self.seed.seed_id}, user=self.user)['code'], 'AUTHORIZATION_DENIED')
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertTrue(self.user.is_active)  # A cached principal cannot bypass current owner recheck.
        self.assertEqual(self.runtime.run_security_tool('canary.check',
            arguments={'artifact_ref': 'output/1'}, user=self.user)['code'], 'AUTHORIZATION_DENIED')
        self.load.assert_not_called()
        self.assertEqual(self.packets, [])
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)

    def test_bound_security_tools_are_not_automatically_called_by_learning_retrieval(self):
        self.assertEqual(LearningToolRegistry().available_learning_tools(),
            ['read_student_profile', 'read_user_knowledge_state', 'read_learning_path_modules'])
        self.runtime.service = FakeLearningService()
        run = self.runtime.run_learning_task(user=self.user, message='SQL injection basics')
        self.assertEqual(run.status, AgentRun.STATUS_COMPLETED)
        self.assertEqual([item['name'] for item in run.used_tools],
            ['read_student_profile', 'read_user_knowledge_state', 'read_learning_path_modules'])
        self.resolve.assert_not_called()
        self.load.assert_not_called()
        self.assertEqual(self.packets, [])
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
