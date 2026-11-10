"""6-F02 faults against the ordinary-startup owner chain and original writers."""
from contextlib import ExitStack
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.adapters.persistence.models import ExportReport, PrivateObject, QuotaExecution
from data_security.adapters.persistence.private_store import DjangoPrivateStore
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.adapters.persistence.risk import DjangoRiskPort
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.application.table_reports import TableReportExecutor
from data_security.contracts import Environment, EventKind, ProtectionError, QuotaReceipt, ReasonCode
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.models import ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision

from .export_sources import ResourceExportSources
from .test_phase6_formal_fixtures import FormalResourceFixture, formal_call


def invoke_fault(entry, user, reviewer, fields):
    """Wrap real stage methods; never replace an owner, authority or B capability."""
    source_ref, permission_ref = fields['source_ref'], fields['permission_ref']
    fault, stages = fields['fault'], []
    unknown = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
                              retryable=False, trace_id='test/formal-stage')
    owned = entry._bound(user=user, source_ref=source_ref, permission_ref=permission_ref)
    assert not isinstance(owned, ProtectionError)
    fired = False

    with ExitStack() as stack:
        if fault == 'reserve-rejected':
            original = DjangoQuotaPort.reserve
            def rejected(self, binding):
                receipt = original(self, binding)
                assert isinstance(receipt, QuotaReceipt)
                assert connection.in_atomic_block
                assert QuotaBucket.objects.get().active_reserved == binding.quantity
                assert ExportReport.objects.get().state == 'preparing'
                stages.append('real-reservation-written')
                return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.LIMIT_EXCEEDED,
                                       retryable=False, trace_id='test/formal-reservation')
            stack.enter_context(patch.object(DjangoQuotaPort, 'reserve', rejected))
            stack.enter_context(patch.object(entry.sources, 'read_original',
                side_effect=AssertionError('rejected reservation opened original')))
            stack.enter_context(patch.object(TableReportExecutor, 'prepare',
                side_effect=AssertionError('rejected reservation prepared output')))
        elif fault == 'risk-revoked-before-issue':
            original = DjangoRiskPort.issue
            def revoked(self, binding):
                assert not connection.in_atomic_block
                assert QuotaReservation.objects.get().state == 'reserved'
                assert not isinstance(entry.risks.revoke(user=reviewer,
                    permission_ref=fields['risk_ref']), ProtectionError)
                stages.append('real-risk-revoked-after-reserve')
                return original(self, binding)
            stack.enter_context(patch.object(DjangoRiskPort, 'issue', revoked))
            stack.enter_context(patch.object(entry.sources, 'read_original',
                side_effect=AssertionError('denied issue opened original')))
        elif fault == 'source-use-revoked-after-input':
            original = ResourceExportSources.load_input
            def revoked(self, *args, **kwargs):
                payload = original(self, *args, **kwargs)
                assert not isinstance(payload, ProtectionError)
                assert not connection.in_atomic_block
                assert not isinstance(entry.sources.revoke_permission(user=reviewer,
                    permission_ref=permission_ref), ProtectionError)
                stages.append('real-source-use-revoked-after-original-read')
                return payload
            stack.enter_context(patch.object(ResourceExportSources, 'load_input', revoked))
        elif fault == 'target-revoked-after-preparation':
            original = TableReportExecutor.prepare
            def revoked(self, *args):
                candidate = original(self, *args)
                assert not isinstance(candidate, ProtectionError)
                assert not connection.in_atomic_block
                assert not isinstance(entry.targets.manage(user=reviewer, operation='revoke',
                    plan=owned.plan, binding=owned.binding, context=owned.context), ProtectionError)
                stages.append('real-target-revoked-after-preparation')
                return candidate
            stack.enter_context(patch.object(TableReportExecutor, 'prepare', revoked))
        elif fault == 'put-unknown':
            original = DjangoReportRepository.put
            def uncertain(self, record):
                assert original(self, record) == record
                assert not connection.in_atomic_block
                assert ExportReport.objects.get().document is not None
                stages.append('complete-report-persisted')
                return unknown
            stack.enter_context(patch.object(DjangoReportRepository, 'put', uncertain))
        elif fault == 'publish-unknown':
            original = DjangoPrivateStore.publish
            def uncertain(self, *args):
                stored = original(self, *args)
                assert not isinstance(stored, ProtectionError)
                assert stored.state == 'published' and connection.in_atomic_block
                assert PrivateObject.objects.get(object_ref=stored.object_ref).state == 'published'
                assert ExecutionAuthorizationRecord.objects.get().state == 'consumed'
                stages.append('real-publication-written')
                return unknown
            stack.enter_context(patch.object(DjangoPrivateStore, 'publish', uncertain))
        elif fault == 'settlement-unknown':
            original = DjangoQuotaPort.commit
            def uncertain(self, binding, delivered):
                assert isinstance(original(self, binding, delivered), QuotaReceipt)
                assert connection.in_atomic_block
                assert QuotaBucket.objects.get().settled == binding.quantity
                assert ExecutionAuthorizationRecord.objects.get().state == 'consumed'
                assert PrivateObject.objects.filter(state='published').count() == 1
                stages.append('real-consume-publication-and-settlement-written')
                return unknown
            stack.enter_context(patch.object(DjangoQuotaPort, 'commit', uncertain))
        elif fault == 'delivery-audit-rejected':
            original = DjangoAuditSink.append
            def rejected(self, event, durability):
                receipt = original(self, event, durability)
                assert not isinstance(receipt, ProtectionError)
                if event.kind is EventKind.DELIVERY:
                    assert connection.in_atomic_block and receipt.chain_version == 'ds.audit.v2'
                    assert SecurityAuditRecord.objects.filter(event__kind='delivery').count() == 1
                    stages.append('real-v2-delivery-written')
                    return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                           retryable=False, trace_id='test/formal-delivery-audit')
                return receipt
            stack.enter_context(patch.object(DjangoAuditSink, 'append', rejected))
        elif fault == 'receipt-exception':
            original = DjangoReportRepository.record_delivery
            def uncertain(self, receipt):
                assert original(self, receipt) == receipt
                assert connection.in_atomic_block
                assert ExportReport.objects.get().delivery_receipt is not None
                assert SecurityAuditRecord.objects.filter(event__kind='delivery').count() == 1
                assert AuthenticatedAuditEntry.objects.filter(record__event__kind='delivery').count() == 1
                stages.append('real-v2-and-delivery-receipt-written')
                raise RuntimeError('synthetic failure before delivery UoW commit')
            stack.enter_context(patch.object(DjangoReportRepository, 'record_delivery', uncertain))
        elif fault in ('reserve-confirmation-lost', 'delivery-confirmation-lost'):
            original = DjangoUnitOfWork.__exit__
            def uncertain(self, *args):
                nonlocal fired
                result = original(self, *args)
                if not fired and args[0] is None and self._committed:
                    report = ExportReport.objects.get()
                    lose = ((fault == 'reserve-confirmation-lost' and report.state == 'preparing') or
                            (fault == 'delivery-confirmation-lost' and report.delivery_receipt is not None))
                    if lose:
                        assert not connection.in_atomic_block
                        fired = True
                        stages.append('real-' + ('reservation' if fault == 'reserve-confirmation-lost' else 'delivery')
                                      + '-committed-before-confirmation-loss')
                        raise RuntimeError('synthetic UoW commit confirmation lost')
                return result
            stack.enter_context(patch.object(DjangoUnitOfWork, '__exit__', uncertain))
        else:
            raise AssertionError('unknown formal stage fault')
        result = entry.execute(user=user, source_ref=source_ref, permission_ref=permission_ref)
    assert isinstance(result, ProtectionError)
    return {'code': result.code.value, 'stages': stages}


class FormalDeliveryFailureTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def setUp(self):
        super().setUp()
        self.source_ref, self.permission_ref, self.risk_ref, self.execution = self.ready()
        self.audit_count = AuthenticatedAuditEntry.objects.count()

    def fault(self, name):
        return formal_call(self, 'fault', source_ref=self.source_ref, permission_ref=self.permission_ref,
                           risk_ref=self.risk_ref, fault=name)

    def assert_retained(self, *, unknown, prepared=True, claimed=True, audit_increment=0):
        report = ExportReport.objects.get()
        self.assertEqual(report.state, 'aborted' if unknown else ('prepared' if prepared else 'preparing'))
        self.assertIsNone(report.delivery_receipt)
        self.assertEqual(report.document is not None, prepared)
        self.assertEqual(QuotaReservation.objects.get().state, 'unknown' if unknown else 'reserved')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled),
                         (0, self.execution.quantity, 0) if unknown else (self.execution.quantity, 0, 0))
        self.assertEqual(QuotaExecution.objects.count(), 1)
        self.assertIsNone(QuotaExecution.objects.get().terminal_receipt)
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), int(claimed))
        if claimed:
            self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(PrivateObject.objects.count(), 2 if prepared else 1)
        self.assertEqual(set(PrivateObject.objects.values_list('state', flat=True)), {'verified'})
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), self.audit_count + audit_increment + int(unknown))
        self.assertEqual(self.gateway.sink.verify('ds.audit.v2').chain_version, 'ds.audit.v2')
        self.assertEqual(RiskDecision.objects.get().action, 'require_approval')
        if prepared:
            record = DjangoReportRepository(environment=Environment.EVALUATION).read(self.execution)
            self.assertNotIsInstance(record, ProtectionError)
            store = DjangoPrivateStore(root=self.root, crypto=self.gateway.sink.crypto,
                                       environment=Environment.EVALUATION)
            self.assertEqual(store.read(record.stored, record.context).code, ReasonCode.AUTHORIZATION_DENIED)
            for path in self.root.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn(b'first@example.invalid', path.read_bytes())
        if unknown:
            event = SecurityAuditRecord.objects.get(event__operation='unknown').event
            self.assertEqual(event['schema_version'], 'ds.quota-recovery-event.v1')
            self.assertEqual(event['quota']['state'], 'unknown')
            self.assertEqual(event['quota']['binding'], self.execution.to_wire())

    def test_real_reservation_rejection_rolls_back_report_hold_and_adapter_binding(self):
        before = (list(RiskDecision.objects.values()), list(IdempotencyRecord.objects.values()), self.audit_count)
        self.assertEqual(self.fault('reserve-rejected'), {'code': 'LIMIT_EXCEEDED',
            'stages': ['real-reservation-written']})
        for model in (ExportReport, QuotaExecution, QuotaReservation, QuotaBucket, ExecutionAuthorizationRecord):
            self.assertFalse(model.objects.exists())
        self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertEqual((list(RiskDecision.objects.values()), list(IdempotencyRecord.objects.values()),
                          AuthenticatedAuditEntry.objects.count()), before)

    def test_real_risk_revocation_after_reserve_denies_issue_without_automatic_release(self):
        self.assertEqual(self.fault('risk-revoked-before-issue'), {'code': 'AUTHORIZATION_DENIED',
            'stages': ['real-risk-revoked-after-reserve']})
        self.assert_retained(unknown=False, prepared=False, claimed=False, audit_increment=1)

    def test_current_source_use_revoked_after_original_read_denies_commit_and_retains_capacity(self):
        self.assertEqual(self.fault('source-use-revoked-after-input'), {'code': 'SOURCE_NOT_APPROVED',
            'stages': ['real-source-use-revoked-after-original-read']})
        self.assert_retained(unknown=False, audit_increment=1)

    def test_current_target_revoked_after_preparation_denies_commit_and_retains_capacity(self):
        self.assertEqual(self.fault('target-revoked-after-preparation'), {'code': 'AUTHORIZATION_DENIED',
            'stages': ['real-target-revoked-after-preparation']})
        self.assert_retained(unknown=False, audit_increment=1)

    def test_unknown_after_complete_report_persistence_fences_without_reopening_or_discarding_ciphertext(self):
        self.assertEqual(self.fault('put-unknown'), {'code': 'DELIVERY_UNKNOWN',
            'stages': ['complete-report-persisted']})
        self.assert_retained(unknown=True)
        before = (list(QuotaExecution.objects.values()), list(QuotaReservation.objects.values()),
                  list(ExecutionAuthorizationRecord.objects.values()), list(PrivateObject.objects.values()),
                  list(SecurityAuditRecord.objects.values()))
        self.assertEqual(formal_call(self, 'execute', source_ref=self.source_ref,
            permission_ref=self.permission_ref), {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual((list(QuotaExecution.objects.values()), list(QuotaReservation.objects.values()),
                          list(ExecutionAuthorizationRecord.objects.values()), list(PrivateObject.objects.values()),
                          list(SecurityAuditRecord.objects.values())), before)

    def test_unknown_after_real_publication_rolls_back_consumption_and_publication(self):
        self.assertEqual(self.fault('publish-unknown'), {'code': 'DELIVERY_UNKNOWN',
            'stages': ['real-publication-written']})
        self.assert_retained(unknown=True)

    def test_unknown_after_real_settlement_rolls_back_all_logical_delivery_effects(self):
        self.assertEqual(self.fault('settlement-unknown'), {'code': 'DELIVERY_UNKNOWN',
            'stages': ['real-consume-publication-and-settlement-written']})
        self.assert_retained(unknown=True)

    def test_actual_v2_audit_rejection_rolls_back_delivery_but_cannot_release_without_recovery_permission(self):
        self.assertEqual(self.fault('delivery-audit-rejected'), {'code': 'AUDIT_UNAVAILABLE',
            'stages': ['real-v2-delivery-written']})
        self.assert_retained(unknown=False)

    def test_exception_after_real_v2_and_receipt_write_rolls_back_then_preserves_full_unknown(self):
        self.assertEqual(self.fault('receipt-exception'), {'code': 'DELIVERY_UNKNOWN',
            'stages': ['real-v2-and-delivery-receipt-written']})
        self.assert_retained(unknown=True)

    def test_lost_reservation_confirmation_fences_real_hold_without_issue_or_original_open(self):
        self.assertEqual(self.fault('reserve-confirmation-lost'), {'code': 'DELIVERY_UNKNOWN',
            'stages': ['real-reservation-committed-before-confirmation-loss']})
        self.assert_retained(unknown=True, prepared=False, claimed=False)

    def test_lost_delivery_confirmation_preserves_committed_winner_and_replay_never_resettles(self):
        self.assertEqual(self.fault('delivery-confirmation-lost'), {'code': 'DELIVERY_UNKNOWN',
            'stages': ['real-delivery-committed-before-confirmation-loss']})
        report = ExportReport.objects.get()
        self.assertEqual(report.state, 'prepared')
        self.assertIsNotNone(report.delivery_receipt)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 0, 2))
        self.assertEqual(sorted(PrivateObject.objects.values_list('state', flat=True)), ['published', 'verified'])
        self.assertFalse(SecurityAuditRecord.objects.filter(event__operation='unknown').exists())
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        before = tuple(list(model.objects.order_by('pk').values()) for model in (
            ExportReport, QuotaExecution, QuotaReservation, QuotaBucket, ExecutionAuthorizationRecord,
            PrivateObject, AuthenticatedAuditEntry, SecurityAuditRecord))
        replay = formal_call(self, 'replay', source_ref=self.source_ref, permission_ref=self.permission_ref,
                             risk_ref=self.risk_ref)
        self.assertEqual(replay, {'binding': self.execution.to_wire(), 'delivery': report.delivery_receipt})
        self.assertEqual(tuple(list(model.objects.order_by('pk').values()) for model in (
            ExportReport, QuotaExecution, QuotaReservation, QuotaBucket, ExecutionAuthorizationRecord,
            PrivateObject, AuthenticatedAuditEntry, SecurityAuditRecord)), before)
