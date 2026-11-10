"""Execute-level faults retain authoritative PostgreSQL state, not mock success."""
from dataclasses import replace
from unittest.mock import Mock, patch

from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.adapters.persistence.models import ExportReport, PrivateObject, QuotaExecution
from data_security.application.audit_gateway import AuditGateway
from data_security.contracts import DeliveryReceipt, KeyPurpose, ProtectionError, QuotaReceipt, QuotaState, ReasonCode
from data_security.tests.fixtures import recovery_context
from data_security.tests.phase2_fixtures import reference_key
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.models import ExecutionAuthorizationRecord
from resources.test_phase6_export_commit import ExportOwnerFixture


class ExportExecutionFailurePostgresTests(ExportOwnerFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.flow.audit = AuditGateway(sink=DjangoAuditSink(clock=timezone.now, crypto=self.crypto,
            key=reference_key(KeyPurpose.AUDIT), context=self.context))
        self.flow.authorize_recovery = Mock(return_value=recovery_context(self.binding))

    def execute(self):
        return self.flow.execute(self.plan, self.binding, self.owner)

    def failure(self, code=ReasonCode.DELIVERY_UNKNOWN):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='test-only/execute-stage')

    def assert_unknown_without_delivery(self):
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
        self.assertEqual(QuotaReservation.objects.get().state, 'unknown')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled),
                         (0, self.binding.quantity, 0))
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        record = self.reports.read(self.binding)
        self.assertTrue(self.path(record.stored).exists())
        self.denied(self.store.read(record.stored, record.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        event = SecurityAuditRecord.objects.get().event
        self.assertEqual(event['schema_version'], 'ds.quota-recovery-event.v1')
        self.assertEqual(event['operation'], 'unknown')
        self.assertEqual(event['quota']['state'], 'unknown')
        self.assertEqual(event['actor_ref'], self.owner.actor_ref)
        self.assertEqual(self.flow.audit.sink.verify('ds.audit.v2').sequence, 1)

    def test_different_complete_binding_cannot_reuse_delivered_idempotency_key(self):
        receipt = self.execute()
        self.assertIsInstance(receipt, DeliveryReceipt)
        self.flow.load_input.reset_mock()
        wrong = replace(self.binding, reservation_id='other/reservation')
        self.denied(self.flow.execute(self.plan, wrong, self.owner), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.flow.load_input.assert_not_called()
        self.assertEqual(self.reports.delivery(self.binding), receipt)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_error_after_real_reservation_rolls_back_new_report_and_entire_hold(self):
        reserve = self.quota.reserve
        def fail_after_hold(binding):
            result = reserve(binding)
            self.assertIsInstance(result, QuotaReceipt)
            self.assertEqual(QuotaBucket.objects.get().active_reserved, binding.quantity)
            self.assertEqual(ExportReport.objects.get().state, 'preparing')
            return self.failure(ReasonCode.LIMIT_EXCEEDED)
        with patch.object(self.quota, 'reserve', side_effect=fail_after_hold) as called:
            self.denied(self.execute(), ReasonCode.LIMIT_EXCEEDED)
            called.assert_called_once()
        for model in (ExportReport, QuotaBucket, QuotaReservation, QuotaExecution,
                      ExecutionAuthorizationRecord, PrivateObject):
            self.assertFalse(model.objects.exists())
        self.flow.load_input.assert_not_called()
        self.flow.authorize_recovery.assert_not_called()

    def test_load_failure_with_revoked_recovery_permission_keeps_hold_until_authorized_retry(self):
        self.flow.load_input.return_value = self.failure(ReasonCode.AUTHORIZATION_DENIED)
        self.flow.authorize_recovery.return_value = False
        self.denied(self.execute(), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, self.binding.quantity)
        self.assertFalse(PrivateObject.objects.exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.exists())
        self.flow.authorize_recovery.return_value = recovery_context(self.binding)
        self.assertIs(self.flow.release(self.binding).state, QuotaState.RELEASED)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 0)

    def test_unknown_after_persisted_report_never_reprepares_or_discards_ciphertext(self):
        put = self.reports.put
        def fail_after_put(record):
            self.assertEqual(put(record), record)
            return self.failure()
        with patch.object(self.reports, 'put', side_effect=fail_after_put) as called:
            self.denied(self.execute(), ReasonCode.DELIVERY_UNKNOWN)
            called.assert_called_once()
        self.assert_unknown_without_delivery()
        self.flow.load_input.reset_mock()
        self.denied(self.execute(), ReasonCode.AUTHORIZATION_DENIED)
        self.flow.load_input.assert_not_called()
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)

    def test_unknown_after_settlement_rolls_back_delivery_before_fencing_and_retaining_full_hold(self):
        commit = self.quota.commit
        def fail_after_settlement(binding, delivered):
            self.assertIsInstance(commit(binding, delivered), QuotaReceipt)
            self.assertEqual(PrivateObject.objects.get().state, 'published')
            self.assertEqual(QuotaBucket.objects.get().settled, 2)
            return self.failure()
        with patch.object(self.quota, 'commit', side_effect=fail_after_settlement) as called:
            self.denied(self.execute(), ReasonCode.DELIVERY_UNKNOWN)
            called.assert_called_once()
        self.assert_unknown_without_delivery()
        reconciled = self.flow.reconcile(self.binding)
        self.assertIsInstance(reconciled, QuotaReceipt)
        self.assertEqual(reconciled.settled_amount, 0)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 0)

    def test_exception_after_actual_v2_and_receipt_write_rolls_back_before_unknown_registration(self):
        save = self.reports.record_delivery
        staged = []
        def fail_after_receipt(receipt):
            self.assertEqual(save(receipt), receipt)
            self.assertIsNotNone(ExportReport.objects.get().delivery_receipt)
            self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
            staged.append(True)
            raise RuntimeError('synthetic failure after receipt write before UoW commit')
        with patch.object(self.reports, 'record_delivery', side_effect=fail_after_receipt):
            self.denied(self.execute(), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(staged, [True])
        self.assert_unknown_without_delivery()
