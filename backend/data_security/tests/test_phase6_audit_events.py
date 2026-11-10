"""Versioned evidence metadata and the unchanged closed gateway boundary."""
from dataclasses import fields, replace
from unittest import TestCase
from unittest.mock import Mock

from data_security.application.audit_gateway import AuditGateway
from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, EventKind, Outcome, ProtectionError,
    ReasonCode, SecurityEvent, SecurityEventV2,
)
from data_security.tests.fixtures import HASH, examples


class AuditEvidenceTests(TestCase):
    def test_versioned_wire_does_not_extend_legacy_schema(self):
        event = examples()[SecurityEventV2]
        self.assertEqual(SecurityEventV2.from_wire(event.to_wire()), event)
        with self.assertRaises(ContractViolation):
            SecurityEvent.from_wire(event.to_wire())
        with self.assertRaises(ContractViolation):
            SecurityEventV2.from_wire(dict(event.to_wire(), detail='untrusted original'))

    def test_successful_delivery_requires_both_owner_evidence_digests(self):
        event = examples()[SecurityEventV2]
        for evidence in ((), (('report', HASH),), (('ciphertext', HASH),)):
            with self.assertRaises(ContractViolation):
                replace(event, kind=EventKind.DELIVERY, outcome=Outcome.SUCCEEDED, evidence_hashes=evidence)
        value = replace(event, kind=EventKind.DELIVERY,
                        evidence_hashes=(('ciphertext', HASH), ('report', HASH)))
        self.assertEqual(SecurityEventV2.from_wire(value.to_wire()), value)

    def test_evidence_is_bounded_sorted_unique_digest_metadata(self):
        event = examples()[SecurityEventV2]
        for evidence in ((('detail', HASH),), (('report', 'original'),),
                         (('report', HASH), ('report', HASH)),
                         (('report', HASH), ('ciphertext', HASH))):
            with self.assertRaises(ContractViolation):
                replace(event, evidence_hashes=evidence)

    def test_gateway_allows_exact_v2_but_never_dictionaries_or_derived_events(self):
        event = examples()[SecurityEventV2]
        sink = Mock(append=Mock(return_value=examples()[AuditReceipt]))
        gateway = AuditGateway(sink=sink)
        self.assertEqual(gateway.record(event, Durability.DURABLE), examples()[AuditReceipt])
        sink.append.assert_called_once_with(event, Durability.DURABLE)
        sink.reset_mock()
        class Derived(SecurityEventV2):
            pass
        derived = Derived(**{f.name: getattr(event, f.name) for f in fields(event)})
        for value in (event.to_wire(), Mock(spec=SecurityEventV2), derived):
            result = gateway.record(value, Durability.DURABLE)
            self.assertIsInstance(result, ProtectionError)
            self.assertEqual(result.code, ReasonCode.INVALID_TYPE)
        sink.append.assert_not_called()
