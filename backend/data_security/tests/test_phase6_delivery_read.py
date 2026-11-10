"""Internal delivery reads with explicit doubles, not real crypto, PG or HTTP."""
from dataclasses import replace
from datetime import timedelta
import hashlib
from unittest import TestCase
from unittest.mock import Mock

from data_security.contracts import (
    AuditReceipt, CipherEnvelope, Durability, EventKind, MediaType, PolicyStatus,
    QuotaReceipt, QuotaState, ReasonCode, canonical_bytes, content_hash,
)
from data_security.tests.fixtures import AT, examples
from data_security.tests.test_phase5_codec import binary
from data_security.tests.test_phase6_export_flow import ExportFlowFixture


class DeliveryReadTests(ExportFlowFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.output = binary(b'Email\n[EMAIL]\n')
        output_hash = hashlib.sha256(self.output.binary).hexdigest()
        fields = dict(self.record.report.content(), output_hash=output_hash)
        report = replace(self.record.report, output_hash=output_hash, report_hash=content_hash(fields))
        self.record = replace(self.record, report=report)
        self.reports.read.return_value = self.record
        self.receipt = self.commit()
        self.delivery_event = self.audit.record.call_args.args[0]
        self.reports.delivery.return_value = self.receipt
        self.reports.lock_delivery.return_value = self.receipt
        self.settled = QuotaReceipt(schema_version=QuotaReceipt.SCHEMA, binding=self.record.binding,
            state=QuotaState.COMMITTED, settled_amount=self.receipt.delivered_records,
            observed_at=AT, evidence_ref=self.receipt.evidence_ref)
        self.quota.read_committed.return_value = self.settled
        self.risk.recheck_delivered.return_value = True
        self.envelope = examples()[CipherEnvelope]
        self.store.read.return_value = self.envelope
        self.crypto = Mock(open=Mock(return_value=self.output))
        self.flow.crypto = self.crypto
        self.flow.read_event = Mock(return_value=self.delivery_event)
        self.flow.object_context = self.record.context
        for value in (self.reports, self.store, self.risk, self.quota, self.audit, self.authorize,
                      self.policy_repository, self.authenticator, self.work):
            value.reset_mock()

    def read(self):
        return self.flow.open_delivery(self.record.binding, attempt_ref='test/download-1')

    def test_fresh_checks_and_attempt_audit_without_new_logical_delivery(self):
        calls = Mock()
        for name, method in (('record', self.reports.read), ('owner', self.authorize),
                ('policy', self.policy_repository.read), ('proof', self.authenticator.verify),
                ('receipt', self.reports.delivery), ('event', self.flow.read_event),
                ('file', self.store.read), ('open', self.crypto.open), ('lock', self.reports.lock_delivery),
                ('risk', self.risk.recheck_delivered), ('quota', self.quota.read_committed),
                ('audit', self.audit.record), ('commit', self.work.commit)):
            calls.attach_mock(method, name)
        self.assertEqual(self.read(), self.output)
        self.assertEqual([call[0] for call in calls.mock_calls],
            ['record', 'owner', 'policy', 'proof', 'receipt', 'event', 'file', 'open',
             'lock', 'owner', 'policy', 'risk', 'quota', 'audit', 'owner', 'policy', 'risk', 'commit'])
        self.crypto.open.assert_called_once_with(self.envelope, self.record.context, self.envelope.key)
        self.flow.read_event.assert_called_once_with(self.receipt.audit.event_id)
        self.reports.lock_delivery.assert_called_once_with(self.record.binding,
            hashlib.sha256(canonical_bytes(self.record, include_payload=True)).hexdigest())
        attempt = self.audit.record.call_args.args[0]
        self.assertIs(attempt.kind, EventKind.AUTHORIZATION)
        self.assertEqual(attempt.correlation_ref, 'test/download-1')
        self.assertEqual(attempt.counts, (('processed', 1), ('bytes', len(self.output.binary))))
        self.assertEqual(attempt.evidence_hashes, self.delivery_event.evidence_hashes)
        self.assertNotEqual(attempt.event_id, self.delivery_event.event_id)
        self.assertEqual(self.flow.open_delivery(self.record.binding, attempt_ref='test/download-2'), self.output)
        self.assertNotEqual(self.audit.record.call_args.args[0].event_id, attempt.event_id)
        self.assertEqual(self.audit.record.call_count, 2)
        for method in (self.quota.reserve, self.quota.commit, self.quota.release, self.quota.reconcile,
                       self.risk.decide, self.risk.issue, self.risk.consume, self.risk.recheck,
                       self.store.publish, self.store.write_candidate, self.store.verify,
                       self.reports.begin, self.reports.put, self.reports.record_delivery, self.reports.abort):
            method.assert_not_called()
        self.assertEqual(self.reports.delivery.return_value, self.receipt)

    def test_history_is_not_an_unconfigured_or_expired_download_grant(self):
        self.flow.crypto = None
        self.assertEqual(self.read().code, ReasonCode.AUTHORIZATION_DENIED)
        self.flow.crypto = self.crypto
        self.flow.clock = lambda: self.record.binding.expires_at
        self.assertEqual(self.read().code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.store.read.assert_not_called()
        self.authorize.assert_not_called()

    def test_current_target_or_policy_denial_precedes_file_read(self):
        self.authorize.return_value = self.error()
        self.assertEqual(self.read().code, ReasonCode.AUTHORIZATION_DENIED)
        self.authorize.return_value = self.owner
        self.policy_repository.read.return_value = replace(self.policy, status=PolicyStatus.RETIRED)
        self.assertEqual(self.read().code, ReasonCode.POLICY_NOT_APPROVED)
        self.store.read.assert_not_called()
        self.work.commit.assert_not_called()

    def test_missing_receipt_bad_proof_or_wrong_authenticated_event_refuses_file_read(self):
        self.authenticator.verify.return_value = self.error(ReasonCode.REPORT_MISMATCH)
        self.assertEqual(self.read().code, ReasonCode.REPORT_MISMATCH)
        self.authenticator.verify.return_value = True
        self.reports.delivery.return_value = None
        self.assertEqual(self.read().code, ReasonCode.AUTHORIZATION_DENIED)
        self.reports.delivery.return_value = self.receipt
        event = self.delivery_event
        for wrong in (replace(event, event_id='other/event'), replace(event, kind=EventKind.PROTECTION),
                replace(event, actor_ref='user/other'), replace(event, object_ref='private/other'),
                replace(event, counts=(('records', 2),)), replace(event, key_versions=('key/other',)),
                replace(event, evidence_hashes=(('ciphertext', 'f' * 64), event.evidence_hashes[1]))):
            with self.subTest(event=wrong.event_id, kind=wrong.kind):
                self.flow.read_event.return_value = wrong
                self.assertEqual(self.read().code, ReasonCode.AUDIT_UNAVAILABLE)
        self.store.read.assert_not_called()
        self.work.commit.assert_not_called()

    def test_full_open_media_type_and_output_digest_are_required(self):
        self.store.read.return_value = self.error(ReasonCode.HASH_MISMATCH)
        self.assertEqual(self.read().code, ReasonCode.HASH_MISMATCH)
        self.crypto.open.assert_not_called()
        self.store.read.return_value = self.envelope
        self.crypto.open.return_value = self.error(ReasonCode.CIPHERTEXT_INVALID)
        self.assertEqual(self.read().code, ReasonCode.CIPHERTEXT_INVALID)
        self.crypto.open.return_value = binary(b'wrong output\n')
        self.assertEqual(self.read().code, ReasonCode.HASH_MISMATCH)
        self.crypto.open.return_value = replace(self.output, media_type=MediaType.BINARY)
        self.assertEqual(self.read().code, ReasonCode.UNSUPPORTED_FORMAT)
        self.reports.lock_delivery.assert_not_called()
        self.audit.record.assert_not_called()

    def test_each_port_error_is_returned_without_compensation(self):
        ports = (self.reports.read, self.authorize, self.policy_repository.read, self.authenticator.verify,
                 self.reports.delivery, self.flow.read_event, self.store.read, self.crypto.open,
                 self.reports.lock_delivery, self.risk.recheck_delivered, self.quota.read_committed, self.audit.record)
        for port in ports:
            original, effect = port.return_value, port.side_effect
            port.side_effect, port.return_value = None, self.error()
            with self.subTest(port=ports.index(port)):
                self.assertEqual(self.read(), self.error())
                self.work.commit.assert_not_called()
                self.quota.reserve.assert_not_called()
                self.quota.release.assert_not_called()
                self.quota.reconcile.assert_not_called()
                self.store.publish.assert_not_called()
            port.return_value, port.side_effect = original, effect

    def test_revocation_after_open_or_receipt_drift_under_lock_refuses_output(self):
        self.authorize.side_effect = [self.owner, self.error()]
        self.assertEqual(self.read().code, ReasonCode.AUTHORIZATION_DENIED)
        self.crypto.open.assert_called_once()
        self.authorize.side_effect = None
        self.reports.lock_delivery.return_value = None
        self.assertEqual(self.read().code, ReasonCode.REPORT_MISMATCH)
        self.audit.record.assert_not_called()
        self.work.commit.assert_not_called()

    def test_current_risk_and_exact_settlement_are_required(self):
        self.risk.recheck_delivered.return_value = False
        self.assertEqual(self.read().code, ReasonCode.AUTHORIZATION_DENIED)
        self.risk.recheck_delivered.return_value = True
        for wrong in (replace(self.settled, settled_amount=0),
                replace(self.settled, evidence_ref='other/settlement'),
                replace(self.settled, state=QuotaState.UNKNOWN, settled_amount=None),
                replace(self.settled, binding=replace(self.record.binding, idempotency_key='other/execution'))):
            self.quota.read_committed.return_value = wrong
            with self.subTest(state=wrong.state):
                self.assertEqual(self.read().code, ReasonCode.REPORT_MISMATCH)
        self.audit.record.assert_not_called()
        self.work.commit.assert_not_called()

    def test_expiry_after_quota_or_audit_lock_wait_prevents_commit(self):
        for port in (self.quota.read_committed, self.audit.record):
            self.flow.clock = lambda: AT + timedelta(seconds=1)
            original, effect = port.return_value, port.side_effect

            def expire(*args):
                self.flow.clock = lambda: self.record.binding.expires_at
                return effect(*args) if effect is not None else original

            port.side_effect = expire
            with self.subTest(port=port):
                self.assertEqual(self.read().code, ReasonCode.AUTHORIZATION_EXPIRED)
                self.work.commit.assert_not_called()
            port.return_value, port.side_effect = original, effect

    def test_current_owner_and_policy_are_reloaded_after_final_audit_wait(self):
        produce = self.audit.record.side_effect
        for port, value, code in (
            (self.authorize, self.error(ReasonCode.AUTHORIZATION_EXPIRED), ReasonCode.AUTHORIZATION_EXPIRED),
            (self.policy_repository.read, replace(self.policy, status=PolicyStatus.RETIRED),
             ReasonCode.POLICY_NOT_APPROVED),
        ):
            original = port.return_value

            def withdraw(event, durability):
                receipt = produce(event, durability)
                port.return_value = value
                return receipt

            self.audit.record.side_effect = withdraw
            with self.subTest(port=port):
                self.assertEqual(self.read().code, code)
                self.crypto.open.assert_called()
                self.work.commit.assert_not_called()
                self.quota.commit.assert_not_called()
                self.store.publish.assert_not_called()
            port.return_value = original
        self.audit.record.side_effect = produce

    def test_shorter_risk_deadline_crossed_after_first_check_refuses_output(self):
        for port in (self.quota.read_committed, self.audit.record):
            expired = False
            original = port.side_effect

            def wait(*args):
                nonlocal expired
                expired = True
                return original(*args) if original is not None else port.return_value

            self.risk.recheck_delivered.side_effect = lambda binding: (
                self.error(ReasonCode.AUTHORIZATION_EXPIRED) if expired else True)
            port.side_effect = wait
            with self.subTest(port=port):
                result = self.read()
                self.assertEqual(result, self.error(ReasonCode.AUTHORIZATION_EXPIRED))
                self.work.commit.assert_not_called()
            port.side_effect = original

    def test_attempt_requires_v2_ledger_and_uow_confirmation_before_output(self):
        produce = self.audit.record.side_effect
        self.audit.record.side_effect = lambda event, durability: replace(produce(event, durability), chain_version='v1')
        self.assertEqual(self.read().code, ReasonCode.AUDIT_UNAVAILABLE)
        self.audit.record.side_effect = lambda event, durability: AuditReceipt(schema_version=AuditReceipt.SCHEMA,
            event_id=event.event_id, durability=Durability.DURABLE, stored_at=event.occurred_at,
            chain_version=None, entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
        self.assertEqual(self.read().code, ReasonCode.AUDIT_UNAVAILABLE)
        self.work.commit.assert_not_called()
        self.audit.record.side_effect = produce
        self.work.__exit__.side_effect = RuntimeError('synthetic download audit confirmation lost')
        self.assertEqual(self.read().code, ReasonCode.DELIVERY_UNKNOWN)
        self.quota.commit.assert_not_called()
        self.quota.release.assert_not_called()
        self.store.publish.assert_not_called()

    def test_attempt_reference_is_validated_before_reading_owner_records(self):
        self.assertEqual(self.flow.open_delivery(self.record.binding, attempt_ref='\n').code, ReasonCode.INVALID_VALUE)
        self.reports.read.assert_not_called()
        self.store.read.assert_not_called()
