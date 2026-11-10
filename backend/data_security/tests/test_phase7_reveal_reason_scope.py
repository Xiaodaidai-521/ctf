"""Real reason protection; memory receipts/UoW are not PostgreSQL evidence."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from data_security.application.protection import ProtectionService
from data_security.application.reveal import RevealFlow
from data_security.contracts import (
    BASELINE_LIMITS, Category, CryptoPort, Environment, EventKind, Outcome, Outlet,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, RevealRepository,
    RevealRequestRecord, RevealRequestRepository, RevealSourcePort, Role, UnitOfWork,
)
from data_security.tests.fixtures import AT, examples
from data_security.tests.phase2_fixtures import MemoryPolicy, algorithm, policy, text
from data_security.tests.test_phase7_reveal_flow import MemoryLedger

MARKERS = ('reveal-reason@example.invalid', '192.0.2.17', '4111111111111111')


class RevealReasonScopeTests(TestCase):
    def setUp(self):
        self.record = replace(examples()[RevealRequestRecord], state='pending', grant=None,
            decided_by=None, decided_at=None, decision_event_ref=None,
            reason=text('核对合成资料 ' + ' '.join(MARKERS)))
        self.context = replace(examples()[ProtectionContext], actor_ref=self.record.subject_ref,
            object_ref=self.record.object_ref, object_version=self.record.object_version,
            scope_refs=tuple(reference for category, reference in self.record.fields),
            domain='ctf', environment=Environment.EVALUATION, outlet=Outlet.API,
            purpose=Purpose.INVESTIGATION, role=Role.STUDENT)
        self.specs = {category: algorithm() for category in (Category.EMAIL, Category.IPV4, Category.CARD)}
        snapshot, binding = policy(self.context, specs=self.specs)
        self.policies = MemoryPolicy(snapshot)
        self.audit = MemoryLedger([])
        self.protection = ProtectionService(policies=self.policies, audit=self.audit, clock=lambda: AT,
            random_bytes=lambda size: b'\x17' * size, environment=self.context.environment,
            limits=BASELINE_LIMITS, field_ref='content/body', authenticated_audit=True)
        self.requests = Mock(spec=RevealRequestRepository)
        self.requests.submit.side_effect = lambda record, context: record
        self.work = MagicMock(spec=UnitOfWork)
        self.work.__enter__.return_value = self.work
        self.work.__exit__.return_value = False
        self.crypto = Mock(spec=CryptoPort)
        self.options = dict(repository=Mock(spec=RevealRepository), sources=Mock(spec=RevealSourcePort),
            crypto=self.crypto, policies=self.policies, policy_binding=binding, audit=self.audit,
            uow_factory=lambda: self.work, clock=lambda: AT, limits=BASELINE_LIMITS,
            requests=self.requests, protection=self.protection, identifier=lambda: 'synthetic-reason')
        self.flow = RevealFlow(**self.options)

    def test_reason_uses_its_own_scope_without_expanding_disclosure(self):
        original = self.context
        with patch.object(self.protection, 'protect', wraps=self.protection.protect) as protected:
            result = self.flow.request(self.record, self.context)
        self.assertIsInstance(result, RevealRequestRecord)
        reason_context = protected.call_args.args[1]
        self.assertEqual(reason_context.scope_refs, ('content/body',))
        self.assertEqual(replace(reason_context, scope_refs=original.scope_refs), original)
        self.assertEqual(self.context, original)
        for field in ('fields', 'subject_ref', 'object_ref', 'object_version', 'purpose_ref', 'course_id'):
            with self.subTest(field=field):
                self.assertEqual(getattr(result, field), getattr(self.record, field))
        self.assertIsNone(result.grant)
        for marker in MARKERS:
            self.assertNotIn(marker, result.reason.text)
        self.assertIn('核对合成资料', result.reason.text)
        self.assertEqual(self.requests.submit.call_args.args, (result, original))
        self.work.commit.assert_called_once_with()
        self.crypto.open.assert_not_called()
        self.assertEqual([(event.kind, event.outcome) for event in self.audit.events],
                         [(EventKind.PROTECTION, Outcome.SUCCEEDED),
                          (EventKind.AUTHORIZATION, Outcome.SUCCEEDED)])

    def test_replacement_protection_port_uses_explicit_reason_field(self):
        protection = ProtectionService(policies=self.policies, audit=self.audit, clock=lambda: AT,
            random_bytes=lambda size: b'\x18' * size, environment=self.context.environment,
            limits=BASELINE_LIMITS, field_ref='reveal-request/reason', authenticated_audit=True)
        flow = RevealFlow(**dict(self.options, protection=protection, reason_field_ref=protection.field_ref))
        with patch.object(protection, 'protect', wraps=protection.protect) as protected:
            result = flow.request(self.record, self.context)
        self.assertIsInstance(result, RevealRequestRecord)
        self.assertEqual(protected.call_args.args[1].scope_refs, ('reveal-request/reason',))
        self.assertEqual(self.requests.submit.call_args.args[1], self.context)
        self.assertEqual(result.fields, self.record.fields)
        self.work.commit.assert_called_once_with()

    def test_client_cannot_add_the_reason_field_to_disclosure_scope(self):
        replaced = replace(self.context, scope_refs=self.context.scope_refs + ('content/body',))
        with patch.object(self.protection, 'protect', wraps=self.protection.protect) as protected:
            result = self.flow.request(self.record, replaced)
        self.assertIsInstance(result, ProtectionError)
        self.assertIs(result.code, ReasonCode.AUTHORIZATION_DENIED)
        protected.assert_not_called()
        self.requests.submit.assert_not_called()
        self.work.__enter__.assert_not_called()
        self.crypto.open.assert_not_called()
        self.assertEqual([event.outcome for event in self.audit.events], [Outcome.DENIED])

    def test_missing_investigation_rule_still_rejects_before_storage(self):
        snapshot, binding = policy(replace(self.context, purpose=Purpose.ANALYSIS), specs=self.specs)
        self.policies.value = snapshot
        self.flow.policy_binding = binding
        result = self.flow.request(self.record, self.context)
        self.assertIsInstance(result, ProtectionError)
        self.assertIs(result.code, ReasonCode.POLICY_NOT_APPROVED)
        self.requests.submit.assert_not_called()
        self.work.__enter__.assert_not_called()
        self.crypto.open.assert_not_called()
        self.assertEqual([event.outcome for event in self.audit.events], [Outcome.DENIED])
