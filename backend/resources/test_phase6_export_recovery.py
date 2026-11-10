"""Real same-database recovery; explicit synthetic recovery permission only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from unittest.mock import Mock, patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.adapters.persistence.models import ExportReport
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.application.audit_gateway import AuditGateway
from data_security.application.export_flow import ExportFlow
from data_security.contracts import KeyPurpose, ProtectionError, QuotaReceipt, QuotaRecoveryEvent, QuotaState, ReasonCode
from data_security.tests.fixtures import recovery_context
from data_security.tests.phase2_fixtures import reference_key
from export_quota.models import QuotaBucket, QuotaReservation
from resources.test_phase6_report_records import ReportRecordFixture


class ExportRecoveryPostgresTests(ReportRecordFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql')
        # Recover a preparation row, not a newly approved export. The historical
        # plan is never executed again and no proof is re-signed for this binding.
        self.binding = replace(self.record.binding, expires_at=timezone.now() + timedelta(minutes=5))
        with DjangoUnitOfWork() as work:
            self.assertIs(self.repository.begin(self.record.plan, self.binding, self.record.context), True)
            work.commit()
        self.quota = DjangoQuotaPort(environment='test', window_key='recovery', limit=20)
        self.assertIsInstance(self.quota.reserve(self.binding), QuotaReceipt)
        self.actor = recovery_context(self.binding)
        self.authorize = Mock(return_value=self.actor)
        self.sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto,
                                    key=reference_key(KeyPurpose.AUDIT), context=self.context)
        self.flow = ExportFlow(reports=self.repository, authenticator=self.auth, store=self.store,
            risk=Mock(), quota=self.quota, policies=Mock(), authorize=Mock(), audit=AuditGateway(sink=self.sink),
            uow_factory=DjangoUnitOfWork, clock=timezone.now, authorize_recovery=self.authorize)

    def unknown(self):
        result = self.quota.reconcile(self.binding, None, 'test-only/uncertain')
        self.assertIs(result.state, QuotaState.UNKNOWN)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)

    def test_reserved_release_replays_without_reclaiming_preparation_or_deleting_ciphertext(self):
        first = self.flow.release(self.binding)
        self.assertIsInstance(first, QuotaReceipt)
        self.assertIs(first.state, QuotaState.RELEASED)
        self.assertEqual(self.flow.release(self.binding), first)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertEqual(QuotaReservation.objects.get().state, 'released')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 0)
        self.assertEqual(QuotaBucket.objects.get().settled, 0)
        self.assertTrue(self.path(self.record.stored).exists())
        self.denied(self.store.read(self.record.stored, self.record.context), ReasonCode.AUTHORIZATION_DENIED)
        with DjangoUnitOfWork():
            self.denied(self.repository.begin(self.record.plan, self.binding, self.record.context),
                        ReasonCode.AUTHORIZATION_DENIED)

    def test_unknown_cannot_release_and_only_locked_abort_allows_zero_reconciliation(self):
        self.unknown()
        self.denied(self.flow.release(self.binding), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)
        first = self.flow.reconcile(self.binding)
        self.assertIsInstance(first, QuotaReceipt)
        self.assertIs(first.state, QuotaState.COMMITTED)
        self.assertEqual(first.settled_amount, 0)
        self.assertEqual(self.flow.reconcile(self.binding), first)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 0)
        self.assertEqual(QuotaBucket.objects.get().settled, 0)

    def test_failure_after_quota_write_rolls_back_abort_and_unknown_balance(self):
        self.unknown()
        reconcile = self.quota.reconcile
        def fail(binding, delivered, evidence):
            result = reconcile(binding, delivered, evidence)
            self.assertIsInstance(result, QuotaReceipt)
            self.assertEqual(ExportReport.objects.get().state, 'aborted')
            self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 0)
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
                                   retryable=False, trace_id='test-only/after-reconcile')
        with patch.object(self.quota, 'reconcile', side_effect=fail):
            self.denied(self.flow.reconcile(self.binding), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaReservation.objects.get().state, 'unknown')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)
        self.assertTrue(self.path(self.record.stored).exists())

    def test_commit_acknowledgement_loss_returns_unknown_then_replays_committed_result(self):
        self.unknown()
        class LostAcknowledgement(DjangoUnitOfWork):
            def __exit__(self, *args):
                super().__exit__(*args)
                raise RuntimeError('synthetic acknowledgement lost after actual commit')
        self.flow.uow_factory = LostAcknowledgement
        self.denied(self.flow.reconcile(self.binding), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        self.flow.uow_factory = DjangoUnitOfWork
        result = self.flow.reconcile(self.binding)
        self.assertIsInstance(result, QuotaReceipt)
        self.assertEqual(result.settled_amount, 0)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 0)

    def test_concurrent_reconcile_has_one_immutable_receipt_and_no_double_credit(self):
        self.unknown()
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.flow.reconcile(self.binding)
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertIsInstance(results[0], QuotaReceipt)
        self.assertEqual(results[0], results[1])
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 0, 0))
        self.assertEqual(QuotaReservation.objects.count(), 1)

    def test_recovery_audit_records_each_operator_observation_without_repeating_quota_effect(self):
        first = self.flow.release(self.binding)
        self.assertIsInstance(first, QuotaReceipt)
        event = QuotaRecoveryEvent.from_wire(SecurityAuditRecord.objects.get().event)
        self.assertEqual(event.quota, first)
        self.assertEqual((event.actor_ref, event.authorization_ref, event.operation),
                         (self.actor.actor_ref, self.actor.authorization_ref, 'release'))
        self.authorize.return_value = replace(self.actor, actor_ref='actor/second-operator',
                                               authorization_ref='authorization/second-recovery')
        self.assertEqual(self.flow.release(self.binding), first)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 0)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        last = self.sink.verify('ds.audit.v2')
        self.assertNotIsInstance(last, ProtectionError)
        self.assertEqual(last.sequence, 2)
        events = [QuotaRecoveryEvent.from_wire(r.event) for r in SecurityAuditRecord.objects.order_by('stored_at')]
        self.assertEqual([e.actor_ref for e in events], [self.actor.actor_ref, 'actor/second-operator'])
        self.assertEqual([e.quota for e in events], [first, first])

    def test_failure_after_actual_audit_append_rolls_back_release_and_fence(self):
        append = self.sink.append
        staged = []
        def fail(event, durability):
            receipt = append(event, durability)
            self.assertNotIsInstance(receipt, ProtectionError)
            self.assertEqual(QuotaReservation.objects.get().state, 'released')
            self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
            staged.append(True)
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                   retryable=False, trace_id='test-only/after-recovery-audit')
        with patch.object(self.sink, 'append', side_effect=fail):
            self.denied(self.flow.release(self.binding), ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(staged, [True])
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, self.binding.quantity)
        self.assertFalse(AuthenticatedAuditEntry.objects.exists())
        self.assertFalse(SecurityAuditRecord.objects.exists())

    def test_unconfigured_v2_sink_cannot_commit_unaudited_recovery(self):
        self.flow.audit = AuditGateway(sink=DjangoAuditSink(clock=timezone.now))
        self.denied(self.flow.release(self.binding), ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, self.binding.quantity)
        self.assertFalse(AuthenticatedAuditEntry.objects.exists())

    def test_recovery_actor_tampering_is_detected_by_authenticated_chain(self):
        self.assertIsInstance(self.flow.release(self.binding), QuotaReceipt)
        self.assertNotIsInstance(self.sink.verify('ds.audit.v2'), ProtectionError)
        row = SecurityAuditRecord.objects.get()
        row.event['actor_ref'] = 'actor/forged-recovery'
        row.save(update_fields=['event'])
        self.denied(self.sink.verify('ds.audit.v2'), ReasonCode.AUDIT_UNAVAILABLE)

    def test_missing_execution_and_revoked_permission_do_not_change_quota(self):
        self.unknown()
        self.denied(self.flow.reconcile(replace(self.binding, idempotency_key='absent/execution')),
                    ReasonCode.REPORT_MISMATCH)
        self.authorize.return_value = False
        self.denied(self.flow.reconcile(self.binding), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaReservation.objects.get().state, 'unknown')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)
