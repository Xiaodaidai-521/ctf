"""Identical audit behavior cases for the memory model and isolated PostgreSQL sink."""
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from data_security.application.audit_gateway import AuditGateway
from data_security.contracts import (
    AuditCheckpoint, AuditReceipt, Durability, KeyPurpose, KeyStatus, ObjectContext,
    ProtectionError, QuotaRecoveryEvent, ReasonCode, SecurityEvent, SecurityEventV2,
    canonical_bytes, content_hash,
)
from data_security.tests.fixtures import AT, examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key
from data_security.tests.test_phase2_services import crypto_service


class AuditSinkContract:
    def setUp(self):
        super().setUp()
        self.now = AT + timedelta(seconds=1)
        self.event = examples()[SecurityEventV2]
        self.context = examples()[ObjectContext]
        self.key = reference_key(KeyPurpose.AUDIT)
        self.keys = FakeKeys()
        self.crypto = crypto_service(keys=self.keys)
        self.sink = self.make_sink()
        self.gateway = AuditGateway(sink=self.sink)

    def assert_error(self, result, code=ReasonCode.AUDIT_UNAVAILABLE, trace=None):
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, code)
        self.assertFalse(result.retryable)
        if trace is not None:
            self.assertEqual(result.trace_id, trace)

    def append(self, event=None, durability=Durability.LEDGER_CONFIRMED):
        event = self.event if event is None else event
        result = self.gateway.record(event, durability)
        self.assertIs(type(result), AuditReceipt)
        self.assertEqual(result.event_id, event.event_id)
        self.assertIs(result.durability, durability)
        self.assertEqual(AuditReceipt.from_json(canonical_bytes(result)), result)
        return result

    def test_durable_upgrade_replay_preserves_first_time_and_has_one_entry(self):
        first = self.append(durability=Durability.DURABLE)
        self.assertIsNone(first.entry_hash)
        self.assertEqual(self.resources(), (1, 0, 0, 0))
        self.now += timedelta(seconds=5)
        confirmed = self.append()
        self.assertEqual(confirmed.stored_at, first.stored_at)
        self.assertEqual(confirmed.chain_version, 'ds.audit.v2')
        self.assertEqual(confirmed.sequence, 1)
        self.assertEqual(self.append(), confirmed)
        self.assertEqual(self.append(durability=Durability.DURABLE), first)
        self.assertEqual(self.make_sink().verify('ds.audit.v2'), confirmed)
        self.assertEqual(self.resources(), (1, 1, 0, 0))

    def test_security_recovery_and_legacy_events_keep_their_chain_versions(self):
        first = self.append()
        recovery = self.append(examples()[QuotaRecoveryEvent])
        self.assertEqual(recovery.chain_version, 'ds.audit.v2')
        self.assertEqual(recovery.sequence, first.sequence + 1)
        old = self.append(replace(examples()[SecurityEvent], event_id='legacy/contract'))
        self.assertEqual(old.chain_version, 'v1')
        self.assertEqual(self.sink.verify('v1'), old)
        self.assertEqual(self.sink.verify('ds.audit.v2'), recovery)
        self.assertEqual(self.resources(), (3, 2, 1, 0))
        with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('legacy signed')):
            self.append(replace(examples()[SecurityEvent], event_id='legacy/second'))
        self.assertEqual(self.resources(), (4, 2, 2, 0))

    def test_same_event_id_cannot_change_payload_or_switch_schema(self):
        first = self.append()
        for changed in (replace(self.event, object_version='other/version'), examples()[SecurityEvent]):
            self.assert_error(self.gateway.record(changed, Durability.LEDGER_CONFIRMED),
                              ReasonCode.IDEMPOTENCY_CONFLICT, self.event.correlation_ref)
        self.assertEqual(self.sink.verify('ds.audit.v2'), first)
        self.assertEqual(self.resources(), (1, 1, 0, 0))

    def test_bare_sink_refuses_v2_instead_of_downgrading_but_keeps_legacy(self):
        bare = self.make_sink(crypto=None, key=None, context=None, checkpoints=False)
        for event in (self.event, examples()[QuotaRecoveryEvent]):
            for durability in Durability:
                self.assert_error(bare.append(event, durability), trace=event.correlation_ref)
        self.assertEqual(self.resources(), (0, 0, 0, 0))
        self.assert_error(bare.verify('ds.audit.v2'), ReasonCode.UNSUPPORTED_FORMAT, 'audit/verify')
        self.assert_error(bare.checkpoint('ds.audit.v2'), ReasonCode.UNSUPPORTED_FORMAT, 'audit/checkpoint')
        legacy = bare.append(examples()[SecurityEvent], Durability.LEDGER_CONFIRMED)
        self.assertIs(type(legacy), AuditReceipt)
        self.assertEqual(legacy.chain_version, 'v1')
        self.assertEqual(self.resources(), (1, 0, 1, 0))

    def test_empty_unknown_chain_and_disabled_checkpoint_return_precise_errors(self):
        for chain in ('v1', 'ds.audit.v2'):
            self.assert_error(self.sink.verify(chain), trace='audit/verify')
        self.assert_error(self.sink.checkpoint('ds.audit.v2'), trace='audit/checkpoint')
        self.assert_error(self.sink.verify('other/chain'), ReasonCode.UNSUPPORTED_FORMAT, 'audit/verify')
        self.assert_error(self.sink.checkpoint('v1'), ReasonCode.UNSUPPORTED_FORMAT, 'audit/checkpoint')
        self.assert_error(self.make_sink(checkpoints=False).checkpoint('ds.audit.v2'),
                          ReasonCode.UNSUPPORTED_FORMAT, 'audit/checkpoint')
        self.assertEqual(self.resources(), (0, 0, 0, 0))

    def test_failed_signing_adds_no_event_or_entry_and_upgrade_preserves_durable_record(self):
        self.keys.error = ReasonCode.KEY_UNAVAILABLE
        self.assert_error(self.gateway.record(self.event, Durability.LEDGER_CONFIRMED),
                          trace=self.event.correlation_ref)
        self.assertEqual(self.resources(), (0, 0, 0, 0))
        durable = self.append(durability=Durability.DURABLE)
        self.assert_error(self.gateway.record(self.event, Durability.LEDGER_CONFIRMED))
        self.assertEqual(self.resources(), (1, 0, 0, 0))
        self.keys.error = None
        self.assertEqual(self.append().stored_at, durable.stored_at)
        self.assertEqual(self.resources(), (1, 1, 0, 0))

    def test_future_event_and_backwards_ledger_time_cannot_be_confirmed(self):
        future = replace(self.event, occurred_at=self.now + timedelta(seconds=1))
        self.assert_error(self.gateway.record(future, Durability.LEDGER_CONFIRMED))
        self.assertEqual(self.resources(), (0, 0, 0, 0))
        first = self.append()
        self.now = AT
        self.assert_error(self.gateway.record(replace(self.event, event_id='backwards/1'),
                                             Durability.LEDGER_CONFIRMED))
        self.assertEqual(self.resources(), (1, 1, 0, 0))
        self.assertEqual(self.sink.verify('ds.audit.v2'), first)

    def test_readonly_verifies_and_replays_but_cannot_sign_new_entries_or_checkpoints(self):
        first = self.append()
        point = self.sink.checkpoint('ds.audit.v2')
        self.assertIs(type(point), AuditReceipt)
        reader = self.make_sink(key=replace(self.key, status=KeyStatus.READ_ONLY),
                                checkpoint_ref=point.checkpoint_ref)
        with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('readonly signed')):
            self.assertEqual(reader.append(self.event, Durability.LEDGER_CONFIRMED), first)
            self.assertEqual(reader.verify('ds.audit.v2'), point)
            self.assert_error(reader.append(replace(self.event, event_id='readonly/new'),
                                            Durability.LEDGER_CONFIRMED))
            self.assert_error(reader.checkpoint('ds.audit.v2'))
        self.assertEqual(self.resources(), (1, 1, 0, 1))

    def test_explicit_retained_keys_and_renewed_authorization_preserve_original_evidence(self):
        first = self.append()
        next_key = replace(self.key, key_ref='audit-auth/v2', version='v2')
        rotated = self.make_sink(key=next_key, retained_keys=(replace(self.key, status=KeyStatus.READ_ONLY),),
            context=replace(self.context, authorization_ref='authorization/renewed'))
        self.assertEqual(rotated.verify('ds.audit.v2'), first)
        second = rotated.append(replace(self.event, event_id='rotated/2'), Durability.LEDGER_CONFIRMED)
        self.assertIs(type(second), AuditReceipt)
        self.assertEqual(second.sequence, 2)
        self.assert_error(self.make_sink(key=next_key).verify('ds.audit.v2'))
        self.assertEqual(rotated.verify('ds.audit.v2'), second)
        self.assert_error(self.make_sink(context=replace(self.context, project_ref='project/other')).verify('ds.audit.v2'))
        self.assertEqual(self.resources(), (2, 2, 0, 0))

    def test_metadata_and_authenticated_entry_tampering_are_not_trusted(self):
        first = self.append()
        original = self.change_record(self.event.event_id, event=replace(self.event, object_version='forged').to_wire())
        self.assert_error(self.sink.verify('ds.audit.v2'))
        self.change_record(self.event.event_id, **original)
        original = self.change_record(self.event.event_id, stored_at=self.now + timedelta(seconds=1))
        self.assert_error(self.sink.verify('ds.audit.v2'))
        self.change_record(self.event.event_id, **original)
        for change in ({'sequence': 2}, {'previous_hash': '1' * 64}, {'current_hash': '1' * 64},
                       {'event_hash': '1' * 64}, {'authentication': bytes(32)},
                       {'recorded_at': self.now + timedelta(seconds=1)}):
            with self.subTest(field=next(iter(change))):
                original = self.change_entry(first, **change)
                self.assert_error(self.sink.verify('ds.audit.v2'))
                self.assert_error(self.sink.append(self.event, Durability.LEDGER_CONFIRMED))
                self.change_entry(first, **original)
        self.assertEqual(self.sink.verify('ds.audit.v2'), first)
        self.assertEqual(self.resources(), (1, 1, 0, 0))

    def test_checkpoint_is_canonical_authenticated_idempotent_and_not_automatically_selected(self):
        first = self.append()
        point = self.sink.checkpoint('ds.audit.v2')
        self.assertIs(type(point), AuditReceipt)
        encoded = self.checkpoint_bytes(point.checkpoint_ref)
        checkpoint = AuditCheckpoint.from_json(encoded)
        self.assertEqual(checkpoint.receipt, first)
        self.assertEqual(encoded, canonical_bytes(checkpoint))
        self.assertEqual(point.checkpoint_ref, 'audit/checkpoint/' + content_hash(checkpoint))
        self.assertTrue(self.crypto.verify_authentication(canonical_bytes(checkpoint.content()),
            checkpoint.authentication, replace(self.context, field_ref='audit/checkpoint.v1'), self.key))
        self.assertEqual(self.sink.checkpoint('ds.audit.v2'), point)
        self.assertEqual(self.sink.verify('ds.audit.v2'), first)
        self.assertEqual(self.make_sink(checkpoint_ref=point.checkpoint_ref).verify('ds.audit.v2'), point)
        self.assertEqual(self.resources(), (1, 1, 0, 1))

    def test_missing_or_damaged_checkpoint_never_falls_back_or_overwrites_existing_object(self):
        self.append()
        point = self.sink.checkpoint('ds.audit.v2')
        original = self.checkpoint_bytes(point.checkpoint_ref)
        reader = self.make_sink(checkpoint_ref=point.checkpoint_ref)
        for encoded in (b'', original[:-1], bytes(len(original)), b' ' * 16385):
            self.put_checkpoint(point.checkpoint_ref, encoded)
            self.assert_error(reader.verify('ds.audit.v2'))
            self.assert_error(reader.checkpoint('ds.audit.v2'))
            self.assert_error(self.sink.checkpoint('ds.audit.v2'))
            self.assertEqual(self.checkpoint_bytes(point.checkpoint_ref), encoded)
        self.put_checkpoint(point.checkpoint_ref, original)
        self.assertEqual(reader.verify('ds.audit.v2'), point)
        missing = self.make_sink(checkpoint_ref='audit/checkpoint/' + 'f' * 64)
        self.assert_error(missing.verify('ds.audit.v2'))
        self.assertEqual(self.resources(), (1, 1, 0, 1))

    def test_recomputed_checkpoint_filename_does_not_authenticate_changed_content(self):
        self.append()
        point = self.sink.checkpoint('ds.audit.v2')
        original = AuditCheckpoint.from_json(self.checkpoint_bytes(point.checkpoint_ref))
        forged = replace(original, checkpointed_at=original.checkpointed_at + timedelta(seconds=1))
        ref = 'audit/checkpoint/' + content_hash(forged)
        self.put_checkpoint(ref, canonical_bytes(forged))
        self.assert_error(self.make_sink(checkpoint_ref=ref).verify('ds.audit.v2'))
        self.assertEqual(self.make_sink(checkpoint_ref=point.checkpoint_ref).verify('ds.audit.v2'), point)
        self.assertEqual(self.resources(), (1, 1, 0, 2))

    def test_checkpoint_detects_covered_tail_loss_but_not_unanchored_suffix_loss(self):
        self.append()
        second = self.append(replace(self.event, event_id='chain/2'))
        point = self.sink.checkpoint('ds.audit.v2')
        third = self.append(replace(self.event, event_id='chain/3'))
        reader = self.make_sink(checkpoint_ref=point.checkpoint_ref)
        self.assertEqual(reader.verify('ds.audit.v2'), replace(third, checkpoint_ref=point.checkpoint_ref))
        self.remove_entry(third)
        self.assertEqual(reader.verify('ds.audit.v2'), point)
        self.remove_entry(second)
        self.assert_error(reader.verify('ds.audit.v2'))
        self.assert_error(reader.checkpoint('ds.audit.v2'))
        self.assertEqual(self.resources(), (3, 1, 0, 1))

    def test_read_authenticated_returns_immutable_security_and_recovery_events_without_signing(self):
        self.append()
        recovery = examples()[QuotaRecoveryEvent]
        self.append(recovery)
        self.append(replace(self.event, event_id='read/tail'))
        before = self.resources()
        with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('read signed')), \
             patch.object(self.crypto, 'verify_authentication', wraps=self.crypto.verify_authentication) as verify:
            loaded = self.sink.read_authenticated(self.event.event_id)
            self.assertIs(type(loaded), SecurityEventV2)
            self.assertEqual(loaded, self.event)
            self.assertEqual(verify.call_count, 3)
            loaded = self.sink.read_authenticated(recovery.event_id)
            self.assertIs(type(loaded), QuotaRecoveryEvent)
            self.assertEqual(loaded, recovery)
            self.assertEqual(verify.call_count, 6)
        self.assertEqual(self.resources(), before)

    def test_read_authenticated_refuses_missing_legacy_durable_only_and_other_chain(self):
        self.append(durability=Durability.DURABLE)
        old = replace(examples()[SecurityEvent], event_id='legacy/read')
        self.append(old)
        for event_id in (self.event.event_id, old.event_id, 'missing/event'):
            self.assert_error(self.sink.read_authenticated(event_id), trace='audit/read')
        bare = self.make_sink(crypto=None, key=None, context=None, checkpoints=False)
        self.assert_error(bare.read_authenticated(self.event.event_id), ReasonCode.UNSUPPORTED_FORMAT, 'audit/read')
        self.append()
        other = self.make_sink(context=replace(self.context, project_ref='project/other'))
        self.assert_error(other.read_authenticated(self.event.event_id), trace='audit/read')
        self.assert_error(self.sink.read_authenticated('missing/event'), trace='audit/read')
        self.assertEqual(self.sink.read_authenticated(self.event.event_id), self.event)
        self.assertEqual(self.resources(), (2, 1, 1, 0))

    def test_read_authenticated_rejects_forged_body_even_with_recomputed_unkeyed_hash(self):
        receipt = self.append()
        changed = replace(self.event, object_version='forged/version')
        original = self.change_record(self.event.event_id, event=changed.to_wire())
        self.assert_error(self.sink.read_authenticated(self.event.event_id), trace='audit/read')
        entry = self.change_entry(receipt, event_hash=content_hash(changed))
        self.assert_error(self.sink.read_authenticated(self.event.event_id), trace='audit/read')
        self.change_entry(receipt, **entry)
        self.change_record(self.event.event_id, **original)
        self.assertEqual(self.sink.read_authenticated(self.event.event_id), self.event)
        self.assertEqual(self.resources(), (1, 1, 0, 0))

    def test_read_authenticated_checks_suffix_before_returning_an_earlier_valid_event(self):
        self.append()
        second = self.append(replace(self.event, event_id='read/suffix'))
        original = self.change_entry(second, authentication=bytes(32))
        self.assert_error(self.sink.read_authenticated(self.event.event_id), trace='audit/read')
        self.change_entry(second, **original)
        self.assertEqual(self.sink.read_authenticated(self.event.event_id), self.event)
        self.assertEqual(self.resources(), (2, 2, 0, 0))

    def test_read_authenticated_requires_selected_checkpoint_and_detects_covered_tail_loss(self):
        self.append()
        second = self.append(replace(self.event, event_id='read/anchored-tail'))
        point = self.sink.checkpoint('ds.audit.v2')
        self.assertIs(type(point), AuditReceipt)
        reader = self.make_sink(checkpoint_ref=point.checkpoint_ref)
        self.assertEqual(reader.read_authenticated(self.event.event_id), self.event)
        missing = self.make_sink(checkpoint_ref='audit/checkpoint/' + 'f' * 64)
        self.assert_error(missing.read_authenticated(self.event.event_id), trace='audit/read')
        encoded = self.checkpoint_bytes(point.checkpoint_ref)
        self.put_checkpoint(point.checkpoint_ref, encoded[:-1])
        self.assert_error(reader.read_authenticated(self.event.event_id), trace='audit/read')
        self.put_checkpoint(point.checkpoint_ref, encoded)
        self.remove_entry(second)
        self.assert_error(reader.read_authenticated(self.event.event_id), trace='audit/read')
        self.assertEqual(self.resources(), (2, 1, 0, 1))

    def test_read_authenticated_needs_retained_keys_and_allows_readonly_without_resigning(self):
        self.append()
        next_key = replace(self.key, key_ref='audit-auth/v2', version='v2')
        self.assert_error(self.make_sink(key=next_key).read_authenticated(self.event.event_id), trace='audit/read')
        reader = self.make_sink(key=replace(next_key, status=KeyStatus.READ_ONLY),
            retained_keys=(replace(self.key, status=KeyStatus.READ_ONLY),),
            context=replace(self.context, authorization_ref='authorization/renewed'))
        with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('read signed')):
            self.assertEqual(reader.read_authenticated(self.event.event_id), self.event)
        self.keys.error = ReasonCode.KEY_UNAVAILABLE
        self.assert_error(reader.read_authenticated(self.event.event_id), trace='audit/read')
        self.keys.error = None
        self.assertEqual(self.resources(), (1, 1, 0, 0))

    def test_read_authenticated_invalid_reference_is_rejected_without_changing_evidence(self):
        self.append()
        for event_id in (None, 1, '', 'x' * 65):
            with self.subTest(event_id_type=type(event_id).__name__):
                self.assert_error(self.sink.read_authenticated(event_id), trace='audit/read')
        self.assertEqual(self.resources(), (1, 1, 0, 0))

    def test_gateway_validates_once_and_failing_signer_does_not_recurse_or_log(self):
        with patch.object(self.sink, 'append', wraps=self.sink.append) as append:
            self.assert_error(self.gateway.record(self.event.to_wire(), Durability.LEDGER_CONFIRMED),
                              ReasonCode.INVALID_TYPE, 'audit/gateway')
            append.assert_not_called()
            with patch.object(self.crypto, 'authenticate', side_effect=RuntimeError('synthetic only')), \
                    patch('logging.Logger._log') as log:
                self.assert_error(self.gateway.record(self.event, Durability.LEDGER_CONFIRMED),
                                  trace=self.event.correlation_ref)
            self.assertEqual(append.call_count, 1)
            log.assert_not_called()
        self.assertEqual(self.resources(), (0, 0, 0, 0))
