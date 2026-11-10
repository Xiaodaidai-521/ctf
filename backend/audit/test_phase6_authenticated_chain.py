"""Real isolated PG and CryptoPort; no simulated authenticated-chain receipts."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.application.audit_gateway import AuditGateway
from data_security.contracts import (
    AuditReceipt, Durability, KeyPurpose, KeyStatus, ObjectContext, ProtectionError,
    ReasonCode, SecurityEvent, SecurityEventV2, content_hash,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import reference_key
from data_security.tests.test_phase2_services import crypto_service
from .models import AuditEvent, AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
from .services import AuditLedgerService


class AuditChainFixture:
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql')
        self.event = examples()[SecurityEventV2]
        self.context = examples()[ObjectContext]
        self.key = reference_key(KeyPurpose.AUDIT)
        self.crypto = crypto_service()
        self.sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=self.key, context=self.context)
        self.gateway = AuditGateway(sink=self.sink)

    def append(self, number=1):
        value = self.gateway.record(replace(self.event, event_id=f'v2/{number}'), Durability.LEDGER_CONFIRMED)
        self.assertIsInstance(value, AuditReceipt)
        return value


class AuthenticatedChainTests(AuditChainFixture, TransactionTestCase):
    def test_durable_upgrade_replay_and_legacy_are_separate(self):
        durable = self.gateway.record(self.event, Durability.DURABLE)
        self.assertIsNone(durable.entry_hash)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        confirmed = self.gateway.record(self.event, Durability.LEDGER_CONFIRMED)
        self.assertIsInstance(confirmed, AuditReceipt)
        self.assertEqual(confirmed.chain_version, 'ds.audit.v2')
        self.assertEqual(self.gateway.record(self.event, Durability.LEDGER_CONFIRMED), confirmed)
        self.assertEqual(self.gateway.record(self.event, Durability.DURABLE), durable)
        self.assertEqual(self.sink.verify('ds.audit.v2'), confirmed)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
        legacy = replace(examples()[SecurityEvent], event_id='legacy/1')
        old = self.gateway.record(legacy, Durability.LEDGER_CONFIRMED)
        self.assertEqual(old.chain_version, 'v1')
        self.assertTrue(AuditLedgerService.verify_chain().is_valid)
        self.assertEqual(self.sink.verify('v1').entry_hash, old.entry_hash)
        self.assertEqual(self.sink.verify('ds.audit.v2'), confirmed)

    def test_changed_event_conflicts_and_unconfigured_sink_never_downgrades(self):
        self.append()
        conflict = self.gateway.record(replace(self.event, event_id='v2/1', object_version='v2'),
                                       Durability.LEDGER_CONFIRMED)
        self.assertEqual(conflict.code, ReasonCode.IDEMPOTENCY_CONFLICT)
        bare = AuditGateway(sink=DjangoAuditSink(clock=timezone.now))
        self.assertEqual(bare.record(self.event, Durability.LEDGER_CONFIRMED).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_crypto_and_database_failures_roll_back_without_logging_or_recursive_audit(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                                  retryable=False, trace_id='fixture/key')
        for target, options in ((self.crypto, {'return_value': failure}),
                                (self.crypto, {'side_effect': RuntimeError('omitted')})):
            with patch.object(target, 'authenticate', **options), patch('logging.Logger._log') as log:
                result = self.gateway.record(self.event, Durability.LEDGER_CONFIRMED)
            self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
            log.assert_not_called()
            self.assertEqual(SecurityAuditRecord.objects.count(), 0)
            self.assertEqual(AuditEvent.objects.count(), 0)
        with patch.object(AuthenticatedAuditEntry, 'save', side_effect=DatabaseError('omitted')):
            self.assertEqual(self.gateway.record(self.event, Durability.LEDGER_CONFIRMED).code,
                             ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)

    def test_outer_uow_controls_durable_event_and_authenticated_entry_together(self):
        with DjangoUnitOfWork():
            self.append()
            self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        with DjangoUnitOfWork() as work:
            first = self.append()
            work.commit()
        self.assertEqual(first.sequence, 1)
        self.assertEqual(self.sink.verify('ds.audit.v2'), first)

    def test_authenticated_read_does_not_commit_the_callers_transaction(self):
        event = replace(self.event, event_id='v2/1')
        with DjangoUnitOfWork():
            self.append()
            with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('read signed')):
                self.assertEqual(self.sink.read_authenticated(event.event_id), event)
            self.assertTrue(connection.in_atomic_block)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)
        self.assertEqual(self.sink.read_authenticated(event.event_id).code, ReasonCode.AUDIT_UNAVAILABLE)
        with DjangoUnitOfWork() as work:
            self.append()
            self.assertEqual(self.sink.read_authenticated(event.event_id), event)
            work.commit()
        with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('read signed')):
            self.assertEqual(self.sink.read_authenticated(event.event_id), event)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_readonly_verifies_original_bytes_but_cannot_append_or_renew_key(self):
        first = self.append()
        row = AuthenticatedAuditEntry.objects.get()
        readonly = replace(self.key, status=KeyStatus.READ_ONLY)
        reader = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=readonly, context=self.context)
        with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('no signing')):
            self.assertEqual(reader.verify('ds.audit.v2'), first)
            result = AuditGateway(sink=reader).record(replace(self.event, event_id='new/1'),
                                                    Durability.LEDGER_CONFIRMED)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(self.crypto.keys.calls[-1][0].status, KeyStatus.READ_ONLY)
        self.assertEqual(AuthenticatedAuditEntry.objects.get().key, row.key)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)

    def test_explicit_rotation_retains_verification_and_wrong_domain_or_missing_key_fails(self):
        first = self.append()
        rotated = replace(self.key, key_ref='audit-auth/v2', version='v2')
        readonly = replace(self.key, status=KeyStatus.READ_ONLY)
        sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=rotated,
                               context=self.context, retained_keys=(readonly,))
        second = AuditGateway(sink=sink).record(replace(self.event, event_id='rotated/2'),
                                                Durability.LEDGER_CONFIRMED)
        self.assertIsInstance(second, AuditReceipt)
        self.assertEqual(second.sequence, first.sequence + 1)
        self.assertEqual(sink.verify('ds.audit.v2'), second)
        missing = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=rotated, context=self.context)
        self.assertIsInstance(missing.verify('ds.audit.v2'), ProtectionError)
        other = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=self.key,
                                context=replace(self.context, project_ref='project/other'))
        self.assertIsInstance(other.verify('ds.audit.v2'), ProtectionError)

    def test_payload_time_sequence_key_and_mac_tampering_is_detected(self):
        self.append()
        entry = AuthenticatedAuditEntry.objects.get()
        changes = ({'event_hash': '1' * 64}, {'sequence': 2}, {'previous_hash': '1' * 64},
                   {'recorded_at': entry.recorded_at + timedelta(seconds=1)},
                   {'authentication': bytes(32)}, {'current_hash': '2' * 64},
                   {'key': replace(self.key, status=KeyStatus.READ_ONLY).to_wire()})
        for change in changes:
            with self.subTest(field=next(iter(change))), transaction.atomic():
                AuthenticatedAuditEntry.objects.filter(pk=entry.pk).update(**change)
                self.assertIsInstance(self.sink.verify('ds.audit.v2'), ProtectionError)
                transaction.set_rollback(True)
        for change in ({'object_version': 'v2'}, {'occurred_at': self.event.occurred_at + timedelta(seconds=1)},
                       {'evidence_hashes': (('report', '2' * 64),)}):
            with self.subTest(field=next(iter(change))), transaction.atomic():
                altered = replace(self.event, event_id='v2/1', **change)
                SecurityAuditRecord.objects.filter(pk=entry.record_id).update(event=altered.to_wire())
                AuthenticatedAuditEntry.objects.filter(pk=entry.pk).update(event_hash=content_hash(altered))
                forged = AuthenticatedAuditEntry.objects.select_related('record').get()
                forged.current_hash = content_hash({'content': self.sink._entry_content(forged),
                                                     'authentication': bytes(forged.authentication)})
                forged.save(update_fields=['current_hash'])
                self.assertIsInstance(self.sink.verify('ds.audit.v2'), ProtectionError)
                transaction.set_rollback(True)
        self.assertIsInstance(self.sink.verify('ds.audit.v2'), AuditReceipt)

    def test_middle_deletion_order_and_insertion_fail_but_unanchored_tail_has_a_window(self):
        receipts = [self.append(n) for n in range(1, 4)]
        with transaction.atomic():
            AuthenticatedAuditEntry.objects.filter(sequence=2).delete()
            self.assertIsInstance(self.sink.verify('ds.audit.v2'), ProtectionError)
            transaction.set_rollback(True)
        with transaction.atomic():
            AuthenticatedAuditEntry.objects.filter(sequence=2).update(sequence=4)
            self.assertIsInstance(self.sink.verify('ds.audit.v2'), ProtectionError)
            transaction.set_rollback(True)
        with transaction.atomic():
            event = replace(self.event, event_id='inserted/4')
            self.gateway.record(event, Durability.DURABLE)
            original = AuthenticatedAuditEntry.objects.get(sequence=3)
            original.pk = None
            original.record = SecurityAuditRecord.objects.get(event_id=event.event_id)
            original.sequence, original.current_hash = 4, '3' * 64
            original.save(force_insert=True)
            self.assertIsInstance(self.sink.verify('ds.audit.v2'), ProtectionError)
            transaction.set_rollback(True)
        AuthenticatedAuditEntry.objects.filter(sequence=3).delete()
        self.assertEqual(self.sink.verify('ds.audit.v2'), receipts[1])
        # No external checkpoint is implemented yet: this is NOT tail-truncation protection.
        self.assertEqual(self.sink.checkpoint('ds.audit.v2').code, ReasonCode.UNSUPPORTED_FORMAT)

    def test_postgres_competing_replays_produce_one_authenticated_entry(self):
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return self.gateway.record(self.event, Durability.LEDGER_CONFIRMED)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        self.assertTrue(all(type(value) is AuditReceipt for value in results))
        self.assertEqual(results[0], results[1])
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(self.sink.verify('ds.audit.v2'), results[0])
