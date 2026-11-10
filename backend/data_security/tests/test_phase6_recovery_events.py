"""Recovery observations have a separate schema, not extra fields on legacy events."""
from dataclasses import fields, replace
from unittest import TestCase
from unittest.mock import Mock

from data_security.application.audit_gateway import AuditGateway
from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, Outcome, QuotaRecoveryEvent, QuotaState,
    ReasonCode, SecurityEvent, SecurityEventV2,
)
from data_security.tests.fixtures import examples


class RecoveryEventTests(TestCase):
    def test_explicit_schema_roundtrip_preserves_complete_receipt_without_extending_old_events(self):
        event = examples()[QuotaRecoveryEvent]
        self.assertEqual(QuotaRecoveryEvent.from_wire(event.to_wire()), event)
        for cls in (SecurityEvent, SecurityEventV2):
            with self.assertRaises(ContractViolation):
                cls.from_wire(event.to_wire())
        with self.assertRaises(ContractViolation):
            QuotaRecoveryEvent.from_wire(dict(event.to_wire(), detail='not accepted'))

    def test_operation_receipt_counts_and_owner_binding_must_agree(self):
        event = examples()[QuotaRecoveryEvent]
        changes = ({'operation': 'release'}, {'operation': 'arbitrary'}, {'outcome': Outcome.SUCCEEDED},
                   {'counts': (('unknown', 0),)}, {'object_ref': 'other/reservation'},
                   {'object_version': 'other/version'}, {'correlation_ref': 'other/execution'})
        for values in changes:
            with self.subTest(values=values), self.assertRaises(ContractViolation):
                replace(event, **values)
        released = replace(event.quota, state=QuotaState.RELEASED)
        value = replace(event, operation='release', quota=released, outcome=Outcome.SUCCEEDED,
                        counts=(('records', 0),))
        self.assertEqual(QuotaRecoveryEvent.from_wire(value.to_wire()), value)
        with self.assertRaises(ContractViolation):
            replace(value, operation='reconcile', quota=replace(released, state=QuotaState.COMMITTED,
                                                               settled_amount=1))

    def test_gateway_accepts_exact_recovery_dto_not_dict_or_subclass(self):
        event = examples()[QuotaRecoveryEvent]
        receipt = replace(examples()[AuditReceipt], event_id=event.event_id)
        sink = Mock(append=Mock(return_value=receipt))
        gateway = AuditGateway(sink=sink)
        self.assertEqual(gateway.record(event, Durability.DURABLE), receipt)
        sink.reset_mock()
        class Derived(QuotaRecoveryEvent):
            pass
        for untrusted in (event.to_wire(), Derived(**{f.name: getattr(event, f.name) for f in fields(event)})):
            self.assertEqual(gateway.record(untrusted, Durability.DURABLE).code, ReasonCode.INVALID_TYPE)
        sink.append.assert_not_called()
