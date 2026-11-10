"""Receipt storage/locking on PostgreSQL. Receipt fixtures do NOT prove v2 auditing."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from threading import Barrier
from unittest.mock import patch

from django.db import DatabaseError, close_old_connections, connection
from django.test import TransactionTestCase

from data_security.adapters.persistence.models import ExportReport, PrivateObject
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import AuditReceipt, DeliveryReceipt, Durability, Environment, Outcome, ReasonCode, canonical_bytes
from resources.test_phase6_report_records import ReportRecordFixture


class DeliveryReceiptTests(ReportRecordFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.repository.put(self.record)
        self.record_hash = hashlib.sha256(canonical_bytes(self.record, include_payload=True)).hexdigest()
        audit = AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id='test-double/delivery',
            durability=Durability.LEDGER_CONFIRMED, stored_at=self.record.report.created_at,
            chain_version='ds.audit.v2', entry_ref='test-double/ledger/1', sequence=1,
            entry_hash='0' * 64, checkpoint_ref=None)
        self.receipt = DeliveryReceipt(schema_version=DeliveryReceipt.SCHEMA, binding=self.record.binding,
            outcome=Outcome.SUCCEEDED, delivered_records=4, evidence_ref='test-double/quota', audit=audit)

    def test_outer_uow_required_and_pending_is_not_a_delivery(self):
        self.assertFalse(connection.in_atomic_block)
        self.assertIsNone(self.repository.delivery(self.record.binding))
        self.denied(self.repository.lock_delivery(self.record.binding, self.record_hash), ReasonCode.AUTHORIZATION_DENIED)
        self.denied(self.repository.record_delivery(self.receipt), ReasonCode.AUTHORIZATION_DENIED)
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_receipt_persists_only_with_outer_commit_and_replays_without_overwrite(self):
        with DjangoUnitOfWork():
            self.assertIsNone(self.repository.lock_delivery(self.record.binding, self.record_hash))
            self.assertEqual(self.repository.record_delivery(self.receipt), self.receipt)
        self.assertIsNone(self.repository.delivery(self.record.binding))
        with DjangoUnitOfWork() as work:
            self.assertIsNone(self.repository.lock_delivery(self.record.binding, self.record_hash))
            self.assertEqual(self.repository.record_delivery(self.receipt), self.receipt)
            work.commit()
        self.assertEqual(self.repository.delivery(self.record.binding), self.receipt)
        with DjangoUnitOfWork() as work:
            self.assertEqual(self.repository.lock_delivery(self.record.binding, self.record_hash), self.receipt)
            self.assertEqual(self.repository.record_delivery(self.receipt), self.receipt)
            self.denied(self.repository.record_delivery(replace(self.receipt, delivered_records=3)),
                        ReasonCode.IDEMPOTENCY_CONFLICT)
            work.commit()
        self.assertEqual(self.repository.read(self.record.binding), self.record)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')  # Repository does not publish.

    def test_abort_returns_delivered_receipt_and_never_relabels_success_as_no_delivery(self):
        with DjangoUnitOfWork() as work:
            self.assertEqual(self.repository.record_delivery(self.receipt), self.receipt)
            work.commit()
        before = ExportReport.objects.values().get()
        with DjangoUnitOfWork() as work:
            self.assertEqual(self.repository.abort(self.record.binding), self.receipt)
            work.commit()
        self.assertEqual(ExportReport.objects.values().get(), before)
        ExportReport.objects.update(delivery_receipt={})
        with DjangoUnitOfWork():
            self.denied(self.repository.abort(self.record.binding), ReasonCode.REPORT_MISMATCH)
        self.assertEqual(ExportReport.objects.get().state, 'prepared')

    def test_missing_mismatched_or_changed_report_is_not_pending_success(self):
        self.denied(self.repository.delivery(replace(self.record.binding, idempotency_key='missing/key')),
                    ReasonCode.REPORT_MISMATCH)
        self.denied(self.repository.delivery(replace(self.record.binding, quantity=9)), ReasonCode.IDEMPOTENCY_CONFLICT)
        with DjangoUnitOfWork():
            self.denied(self.repository.lock_delivery(self.record.binding, '0' * 64), ReasonCode.REPORT_MISMATCH)
        ExportReport.objects.update(document={})
        self.denied(self.repository.delivery(self.record.binding), ReasonCode.REPORT_MISMATCH)

    def test_unconfirmed_or_malformed_receipts_fail_closed(self):
        with DjangoUnitOfWork():
            old = replace(self.receipt, audit=replace(self.receipt.audit, chain_version='v1'))
            self.denied(self.repository.record_delivery(old), ReasonCode.AUDIT_UNAVAILABLE)
            unknown = replace(self.receipt, outcome=Outcome.UNKNOWN, delivered_records=None)
            self.denied(self.repository.record_delivery(unknown), ReasonCode.AUDIT_UNAVAILABLE)
        for invalid in ({}, {'outcome': 'client-success'}, self.receipt.to_wire() | {'unexpected': True}):
            ExportReport.objects.update(delivery_receipt=invalid)
            self.denied(self.repository.delivery(self.record.binding))

    def test_database_failure_is_unknown_and_keeps_candidate(self):
        with patch.object(ExportReport.objects, 'filter', side_effect=DatabaseError('injected')):
            self.denied(self.repository.delivery(self.record.binding), ReasonCode.DELIVERY_UNKNOWN)
        with DjangoUnitOfWork():
            with patch.object(ExportReport, 'save', side_effect=DatabaseError('injected')):
                self.denied(self.repository.record_delivery(self.receipt), ReasonCode.DELIVERY_UNKNOWN)
        self.assertIsNone(self.repository.delivery(self.record.binding))
        self.assertTrue(self.path(self.record.stored).exists())

    def test_concurrent_locker_observes_single_immutable_winner(self):
        self.assertEqual(connection.vendor, 'postgresql')
        barrier = Barrier(2)
        def deliver(receipt):
            close_old_connections()
            try:
                repository = DjangoReportRepository(environment=Environment.TEST)
                barrier.wait(timeout=10)
                with DjangoUnitOfWork() as work:
                    previous = repository.lock_delivery(receipt.binding, self.record_hash)
                    if previous is not None:
                        return previous
                    result = repository.record_delivery(receipt)
                    self.assertIsInstance(result, DeliveryReceipt)
                    work.commit()
                return result
            finally:
                close_old_connections()
        alternatives = [self.receipt, replace(self.receipt, evidence_ref='test-double/other')]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(deliver, alternatives))
        self.assertEqual(results[0], results[1])
        self.assertIn(results[0], alternatives)
        self.assertEqual(self.repository.delivery(self.record.binding), results[0])
        self.assertEqual(ExportReport.objects.count(), 1)
