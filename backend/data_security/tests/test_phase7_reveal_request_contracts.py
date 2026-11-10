"""New server request state; old source/grant test methods are not reloaded."""
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import inspect
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase

from data_security.contracts import (
    CONTRACT_TYPES, CONTRACT_VERSION, PORT_TYPES, ContractViolation, GrantState,
    PayloadKind, ReasonCode, RevealGrant, RevealRepository, RevealRequestRecord,
    RevealRequestRepository, content_hash,
)
from data_security.tests.fixtures import examples
from data_security.tests import test_import_isolation as isolation_fixture


class RevealRequestContractTests(TestCase):
    def setUp(self):
        self.record = examples()[RevealRequestRecord]
        self.pending = replace(self.record, state='pending', grant=None, decided_by=None,
                               decided_at=None, decision_event_ref=None)

    def test_registration_keeps_m0_version_and_old_consume_boundary(self):
        self.assertEqual(CONTRACT_VERSION, 'ds.m0.v1')
        self.assertEqual(len(CONTRACT_TYPES), 49)
        self.assertEqual(len(PORT_TYPES), 23)
        self.assertEqual(set(examples()), set(CONTRACT_TYPES))
        self.assertIn(RevealRequestRepository, PORT_TYPES)
        self.assertTrue(RevealRequestRepository._is_protocol)
        self.assertEqual(list(inspect.signature(RevealRepository.consume).parameters),
                         ['self', 'grant', 'context', 'expected_version', 'at'])
        self.assertEqual(list(inspect.signature(RevealRequestRepository.approved).parameters),
                         ['self', 'request_ref', 'context'])

    def test_request_state_is_frozen_sensitive_and_server_only(self):
        with self.assertRaises(FrozenInstanceError):
            self.record.state = 'pending'
        self.assertEqual(repr(self.record), 'RevealRequestRecord(<redacted>)')
        self.assertFalse(hasattr(self.record, '__dict__'))
        for operation, code in (
            (self.record.to_wire, ReasonCode.SENSITIVE_SERIALIZATION_FORBIDDEN),
            (lambda: RevealRequestRecord.from_wire(self.record.to_wire(include_payload=True)),
             ReasonCode.TRUSTED_CONSTRUCTION_REQUIRED),
            (lambda: RevealGrant.from_wire(self.record.grant.to_wire()),
             ReasonCode.TRUSTED_CONSTRUCTION_REQUIRED),
        ):
            with self.subTest(code=code), self.assertRaises(ContractViolation) as caught:
                operation()
            self.assertIs(caught.exception.code, code)

    def test_reason_scope_course_and_closed_states_are_bounded_at_the_boundary(self):
        for changes in (
            {'course_id': True}, {'course_id': 0}, {'course_id': 2**53},
            {'fields': ()}, {'fields': list(self.pending.fields)},
            {'fields': self.pending.fields * 17}, {'state': 'accepted'},
            {'reason': replace(self.pending.reason, text='   ')},
            {'requested_at': self.pending.requested_at.replace(tzinfo=None)},
        ):
            with self.subTest(changes=tuple(changes)), self.assertRaises(ContractViolation):
                replace(self.pending, **changes)
        self.assertIs(self.pending.reason.kind, PayloadKind.TEXT)
        with self.assertRaises(ContractViolation) as caught:
            replace(self.pending, fields=self.pending.fields * 2)
        self.assertIs(caught.exception.code, ReasonCode.DUPLICATE_FIELD)
        with self.assertRaises(ContractViolation) as caught:
            replace(self.pending.reason, text='x' * (self.pending.reason.limits.max_text_chars + 1))
        self.assertIs(caught.exception.code, ReasonCode.LIMIT_EXCEEDED)

    def test_decision_state_and_grant_cannot_disagree_or_change_approved_scope(self):
        for changes in (
            {'state': 'approved'}, {'decided_by': 'actor/reviewer'},
            {'decision_event_ref': 'a' * 64},
        ):
            with self.subTest(changes=tuple(changes)), self.assertRaises(ContractViolation):
                replace(self.pending, **changes)
        for changes in (
            {'state': 'rejected'}, {'decided_by': self.record.subject_ref},
            {'decided_at': self.record.requested_at - timedelta(seconds=1)},
            {'object_version': 'v2'}, {'decision_event_ref': 'not-a-digest'},
        ):
            with self.subTest(changes=tuple(changes)), self.assertRaises(ContractViolation):
                replace(self.record, **changes)
        rejected = replace(self.pending, state='rejected', decided_by='actor/reviewer',
                           decided_at=self.pending.requested_at, decision_event_ref='a' * 64)
        self.assertIsNone(rejected.grant)
        consumed = replace(self.record.grant, state=GrantState.CONSUMED,
                           consumed_at=self.record.grant.issued_at + timedelta(seconds=1))
        self.assertEqual(replace(self.record, state='consumed', grant=consumed).grant, consumed)

    def test_authorization_evidence_binds_metadata_without_a_public_reason_digest(self):
        content = self.record.authorization_content()
        self.assertNotIn('reason', content)
        self.assertNotIn('decision_event_ref', content)
        changed_reason = replace(self.record, reason=replace(self.record.reason, text='另一条合成理由'))
        changed_event = replace(self.record, decision_event_ref='b' * 64)
        self.assertEqual(content_hash(content), content_hash(changed_reason.authorization_content()))
        self.assertEqual(content_hash(content), content_hash(changed_event.authorization_content()))
        for changes in ({'request_ref': 'another-request'}, {'course_id': 2},
                        {'requested_at': self.record.requested_at - timedelta(seconds=1)}):
            with self.subTest(changes=tuple(changes)):
                changed = replace(self.record, **changes)
                self.assertNotEqual(content_hash(content), content_hash(changed.authorization_content()))

    def test_new_record_import_uses_all_existing_strict_guards_and_exact_counts(self):
        root = Path(__file__).resolve().parents[3]
        program = isolation_fixture.PROBE + '\nassert contracts.RevealRequestRepository._is_protocol\n'
        with tempfile.TemporaryDirectory(prefix='reveal-request-import-') as directory:
            result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', program, str(root / 'backend')],
                                    cwd=directory, env={}, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"imported_contracts": 49', result.stdout)
            self.assertIn('"ports": 23', result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])
