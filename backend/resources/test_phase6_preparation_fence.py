"""Persisted preparation ownership and abort fencing, using real PostgreSQL locks."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from queue import Queue
from threading import Barrier, Event
import time
from unittest.mock import patch

from django.db import DatabaseError, close_old_connections, connection
from django.test import TransactionTestCase

from data_security.adapters.persistence.models import ExportReport
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import ReasonCode, content_hash
from export_quota.services import QuotaService
from resources.test_phase6_report_records import ReportRecordFixture, document_hash


class PreparationFenceTests(ReportRecordFixture, TransactionTestCase):
    def begin(self):
        with DjangoUnitOfWork() as work:
            result = self.repository.begin(self.record.plan, self.record.binding, self.record.context)
            if type(result) is bool:
                work.commit()
        return result

    def test_begin_claims_once_without_a_report_file_reference_or_quota_write(self):
        with patch.object(QuotaService, 'reserve', side_effect=AssertionError('reserve')):
            self.assertIs(self.begin(), True)
            self.assertIs(self.begin(), False)
        row = ExportReport.objects.get()
        self.assertEqual(row.state, 'preparing')
        self.assertIsNone(row.document)
        self.assertIsNone(row.private_object_id)
        self.assertIsNone(self.repository.read(self.record.binding))
        self.denied(self.repository.delivery(self.record.binding), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.repository.put(self.record), self.record)
        self.assertEqual(self.repository.read(self.record.binding), self.record)
        self.assertIs(self.begin(), False)
        self.assertEqual(ExportReport.objects.get().state, 'prepared')

    def test_begin_binds_plan_context_execution_and_requires_outer_uow(self):
        self.denied(self.repository.begin(self.record.plan, self.record.binding, self.record.context),
                    ReasonCode.AUTHORIZATION_DENIED)
        self.assertIs(self.begin(), True)
        values = dict(self.record.plan.content(), plan_id='plan/changed')
        changed_plan = replace(self.record.plan, plan_id='plan/changed', approval=None,
                               plan_hash=content_hash(values))
        for plan, binding, context in (
            (changed_plan, self.record.binding, self.record.context),
            (self.record.plan, self.record.binding, replace(self.record.context, field_ref='other/field')),
            (self.record.plan, replace(self.record.binding, quantity=self.record.binding.quantity + 1),
             self.record.context),
            (self.record.plan, replace(self.record.binding, idempotency_key='other/key'), self.record.context),
        ):
            with DjangoUnitOfWork():
                self.denied(self.repository.begin(plan, binding, context), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(ExportReport.objects.count(), 1)
        self.denied(self.repository.put(replace(self.record, plan=changed_plan)), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertIsNone(ExportReport.objects.get().document)

    def test_legacy_prepared_document_is_not_rewritten_or_reclaimed(self):
        self.assertEqual(self.repository.put(self.record), self.record)
        ExportReport.objects.update(intent_hash='')
        before = ExportReport.objects.values().get()
        self.assertIs(self.begin(), False)
        self.assertEqual(ExportReport.objects.values().get(), before)
        self.assertEqual(self.repository.read(self.record.binding), self.record)

    def test_abort_fences_late_put_and_commit_without_deleting_evidence_or_releasing(self):
        self.assertIs(self.begin(), True)
        with patch.object(QuotaService, 'release', side_effect=AssertionError('release')):
            with DjangoUnitOfWork() as work:
                self.assertIsNone(self.repository.abort(self.record.binding))
                work.commit()
        self.denied(self.repository.put(self.record), ReasonCode.AUTHORIZATION_DENIED)
        self.denied(self.begin(), ReasonCode.AUTHORIZATION_DENIED)
        with DjangoUnitOfWork() as work:
            self.assertIsNone(self.repository.abort(self.record.binding))
            work.commit()
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertIsNone(self.repository.read(self.record.binding))
        self.denied(self.store.read(self.record.stored, self.record.context), ReasonCode.AUTHORIZATION_DENIED)

    def test_prepared_abort_preserves_document_and_blocks_delivery_lock(self):
        self.repository.put(self.record)
        original = ExportReport.objects.get().document
        with DjangoUnitOfWork() as work:
            self.assertIsNone(self.repository.abort(self.record.binding))
            work.commit()
        self.assertEqual(self.repository.read(self.record.binding), self.record)
        self.assertEqual(ExportReport.objects.get().document, original)
        with DjangoUnitOfWork():
            self.denied(self.repository.lock_delivery(self.record.binding, document_hash(original)),
                        ReasonCode.AUTHORIZATION_DENIED)
        self.denied(self.repository.put(self.record), ReasonCode.AUTHORIZATION_DENIED)

    def test_missing_binding_database_errors_and_rollback_are_not_zero_delivery_proof(self):
        self.denied(self.repository.abort(self.record.binding), ReasonCode.AUTHORIZATION_DENIED)
        with DjangoUnitOfWork():
            self.denied(self.repository.abort(self.record.binding), ReasonCode.REPORT_MISMATCH)
            self.assertIs(self.repository.begin(self.record.plan, self.record.binding, self.record.context), True)
        self.assertFalse(ExportReport.objects.exists())
        self.assertIs(self.begin(), True)
        with DjangoUnitOfWork():
            self.denied(self.repository.abort(replace(self.record.binding, subject_ref='other/subject')),
                        ReasonCode.IDEMPOTENCY_CONFLICT)
            self.assertIsNone(self.repository.abort(self.record.binding))
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        with patch.object(ExportReport, 'save', side_effect=DatabaseError('omitted')), DjangoUnitOfWork():
            self.denied(self.repository.abort(self.record.binding), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')

    def test_postgres_competing_begin_has_one_preparation_owner(self):
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return self.begin()
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(ExportReport.objects.count(), 1)

    def test_postgres_put_waiting_on_abort_cannot_revive_preparation(self):
        self.assertIs(self.begin(), True)
        pids = Queue()
        def worker():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    pids.put(cursor.fetchone()[0])
                return self.repository.put(self.record)
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with DjangoUnitOfWork() as work:
                ExportReport.objects.select_for_update().get()
                future = pool.submit(worker)
                pid = pids.get(timeout=5)
                blocked = False
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT cardinality(pg_blocking_pids(%s)) > 0', [pid])
                        blocked = cursor.fetchone()[0]
                    if blocked:
                        break
                    Event().wait(0.01)
                self.assertTrue(blocked, 'real PostgreSQL report lock wait was not observed')
                self.assertIsNone(self.repository.abort(self.record.binding))
                work.commit()
            self.denied(future.result(timeout=15), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertIsNone(ExportReport.objects.get().document)
