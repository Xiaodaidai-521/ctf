"""Real PG execution from no hold/claim/file; only owner inputs and keys are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from dataclasses import replace
from threading import Event
from unittest.mock import Mock, patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.adapters.persistence.models import ExportReport, PolicyVersion, PrivateObject
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.application.audit_gateway import AuditGateway
from data_security.contracts import DeliveryReceipt, KeyPurpose, PolicyStatus, ProtectionError, QuotaState, ReasonCode
from data_security.tests.fixtures import recovery_context
from data_security.tests.phase2_fixtures import reference_key
from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService
from export_risk.models import ExecutionAuthorizationRecord, RiskDecision
from resources.test_phase6_export_commit import ExportOwnerFixture


class ExportExecutePostgresTests(ExportOwnerFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
                                    context=self.context)
        self.flow.audit = AuditGateway(sink=self.sink)
        self.flow.authorize_recovery = Mock(return_value=recovery_context(self.binding))
        # A real decision reference is part of the owner binding. It is not a
        # reservation, a claim, or permission to bypass execute's fresh admission.
        self.assertEqual(RiskDecision.objects.count(), 1)
        for model in (QuotaReservation, ExecutionAuthorizationRecord, ExportReport, PrivateObject):
            self.assertFalse(model.objects.exists())

    def execute(self):
        return self.flow.execute(self.plan, self.binding, self.owner)

    def failure(self, code=ReasonCode.AUTHORIZATION_DENIED):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='test-only/execute')

    def test_real_execute_reserves_claims_prepares_and_delivers_once_outside_large_io_locks(self):
        def load(*args):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(ExportReport.objects.get().state, 'preparing')
            self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
            self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
            return self.payload
        self.flow.load_input.side_effect = load
        write = self.store.write_candidate
        def write_candidate(*args):
            self.assertFalse(connection.in_atomic_block)
            return write(*args)
        with patch.object(QuotaService, 'reserve', wraps=QuotaService.reserve) as reserve, \
                patch.object(self.store, 'write_candidate', side_effect=write_candidate):
            receipt = self.execute()
            self.assertIsInstance(receipt, DeliveryReceipt)
            self.assertEqual(receipt.delivered_records, 2)
            reserve.assert_called_once()
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 0)
        self.assertEqual(PrivateObject.objects.get().state, 'published')
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
        self.assertEqual(self.sink.verify('ds.audit.v2'), receipt.audit)
        self.flow.load_input.reset_mock()
        with patch.object(QuotaService, 'reserve', side_effect=AssertionError('re-reserve')):
            self.assertEqual(self.execute(), receipt)
        self.flow.load_input.assert_not_called()
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.count(), 1)

    def test_peer_during_preparation_cannot_claim_load_reserve_or_abort_owner(self):
        entered, proceed = Event(), Event()
        original_load = self.flow.load_input
        def load(*args):
            entered.set()
            self.assertTrue(proceed.wait(15))
            return self.payload
        worker_flow = copy(self.flow)
        worker_flow.risk = copy(self.risk)
        worker_flow.load_input = load
        def worker():
            close_old_connections()
            try:
                return worker_flow.execute(self.plan, self.binding, self.owner)
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker)
            try:
                self.assertTrue(entered.wait(15))
                self.denied(self.execute(), ReasonCode.DELIVERY_UNKNOWN)
                original_load.assert_not_called()
                self.assertEqual(ExportReport.objects.get().state, 'preparing')
                self.assertEqual(QuotaReservation.objects.count(), 1)
                self.assertEqual(QuotaBucket.objects.get().active_reserved, self.binding.quantity)
            finally:
                proceed.set()
            self.assertIsInstance(future.result(timeout=30), DeliveryReceipt)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_revoked_admission_and_retired_policy_never_create_a_hold(self):
        self.risk.authorize.return_value = self.failure()
        self.denied(self.execute(), ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(ExportReport.objects.exists())
        PolicyVersion.objects.update(document=replace(self.policy, status=PolicyStatus.RETIRED).to_wire())
        self.denied(self.execute(), ReasonCode.POLICY_NOT_APPROVED)
        self.assertFalse(QuotaReservation.objects.exists())
        self.flow.load_input.assert_not_called()

    def test_issue_failure_releases_only_after_current_recovery_permission_and_fence(self):
        with patch.object(self.risk, 'issue', return_value=self.failure()):
            self.denied(self.execute(), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertEqual(QuotaReservation.objects.get().state, 'released')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 0)
        self.assertFalse(PrivateObject.objects.exists())
        self.flow.load_input.assert_not_called()

    def test_failure_after_actual_candidate_preserves_ciphertext_but_never_publishes(self):
        prepare = self.executor.prepare
        def fail_after_candidate(*args):
            candidate = prepare(*args)
            self.assertNotIsInstance(candidate, ProtectionError)
            return self.failure(ReasonCode.REPORT_MISMATCH)
        with patch.object(self.executor, 'prepare', side_effect=fail_after_candidate):
            self.denied(self.execute(), ReasonCode.REPORT_MISMATCH)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertEqual(QuotaReservation.objects.get().state, 'released')
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        entry = AuthenticatedAuditEntry.objects.select_related('record').get()
        self.assertEqual(entry.record.event['schema_version'], 'ds.quota-recovery-event.v1')
        self.assertEqual(entry.record.event['operation'], 'release')
        self.assertEqual(self.sink.verify('ds.audit.v2').sequence, 1)

    def test_unknown_prepare_fences_and_retains_capacity_until_explicit_zero_reconcile(self):
        with patch.object(self.executor, 'prepare', return_value=self.failure(ReasonCode.DELIVERY_UNKNOWN)):
            self.denied(self.execute(), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertEqual(QuotaReservation.objects.get().state, 'unknown')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
        self.denied(self.execute(), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)
        result = self.flow.reconcile(self.binding)
        self.assertIs(result.state, QuotaState.COMMITTED)
        self.assertEqual(result.settled_amount, 0)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 0)
        events = [e.record.event for e in AuthenticatedAuditEntry.objects.select_related('record').order_by('sequence')]
        self.assertEqual([e['operation'] for e in events], ['unknown', 'reconcile'])
        self.assertEqual([e['actor_ref'] for e in events], [self.owner.actor_ref, 'actor/recovery'])
        self.assertEqual(self.sink.verify('ds.audit.v2').sequence, 2)

    def test_unknown_audit_failure_preserves_full_hold_without_claiming_a_status_commit(self):
        with patch.object(self.executor, 'prepare', return_value=self.failure(ReasonCode.DELIVERY_UNKNOWN)), \
                patch.object(self.sink, 'append', return_value=self.failure(ReasonCode.AUDIT_UNAVAILABLE)) as audited:
            self.denied(self.execute(), ReasonCode.DELIVERY_UNKNOWN)
            audited.assert_called_once()
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, self.binding.quantity)
        self.assertFalse(AuthenticatedAuditEntry.objects.exists())

    def test_lost_final_commit_acknowledgement_preserves_actual_delivery_and_replays_it(self):
        class LostAcknowledgement(DjangoUnitOfWork):
            def __exit__(work, *args):
                result = super().__exit__(*args)
                if ExportReport.objects.filter(delivery_receipt__isnull=False).exists():
                    raise RuntimeError('synthetic final commit acknowledgement lost')
                return result
        self.flow.uow_factory = LostAcknowledgement
        self.denied(self.execute(), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(PrivateObject.objects.get().state, 'published')
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.flow.uow_factory = DjangoUnitOfWork
        self.flow.load_input.reset_mock()
        self.assertIsInstance(self.execute(), DeliveryReceipt)
        self.flow.load_input.assert_not_called()
        self.assertEqual(QuotaBucket.objects.get().settled, 2)

    def test_lost_reservation_commit_acknowledgement_keeps_full_unknown_hold_without_claim(self):
        lost = []
        class LostAcknowledgement(DjangoUnitOfWork):
            def __exit__(work, *args):
                result = super().__exit__(*args)
                if not lost and QuotaReservation.objects.exists():
                    lost.append(True)
                    raise RuntimeError('synthetic reserve commit acknowledgement lost')
                return result
        self.flow.uow_factory = LostAcknowledgement
        self.denied(self.execute(), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertEqual(QuotaReservation.objects.get().state, 'unknown')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.flow.load_input.assert_not_called()
