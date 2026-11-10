"""Internal reads of real private deliveries; source/request authority remains synthetic.

Uses the original upload/source fixture, real file keys, owner approval, PostgreSQL
and v2 ledger. No HTTP, sharing, production source provider or network ack is added.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import replace
from datetime import timedelta
import hashlib
from queue import Queue
from threading import Event
import time
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuditLedgerLock, AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble_export_plan_approvals, assemble_resource_uploads
from data_security.adapters.persistence.models import ExportReport, PolicyVersion, PrivateObject, QuotaExecution
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import (
    BoundedPayload, DeliveryReceipt, EventKind, MediaType, PolicySnapshot, PolicyStatus,
    ProtectionError, ReasonCode, canonical_bytes, content_hash,
)
from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService
from export_risk.models import ExecutionAuthorizationRecord, RiskDecision
from users.models import CTFUser
from .models import Resource
from .test_phase6_source_delivery import PrivateSourceDeliveryFixture


class DeliveryReadPostgresTests(PrivateSourceDeliveryFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.receipt = self.flow.execute(self.plan, self.binding, self.owner)
        self.assertIs(type(self.receipt), DeliveryReceipt)
        self.record = self.flow.reports.read(self.binding)
        self.path = self.root / (self.record.stored.object_ref.removeprefix('private/') + '.sealed')
        self.assertEqual(self.receipt.delivered_records, 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)

    def new_flow(self):
        flow = super().new_flow()
        flow.crypto = flow.store.crypto
        flow.read_event = flow.audit.sink.read_authenticated
        return flow

    def read(self, attempt='test/download-1'):
        return self.flow.open_delivery(self.binding, attempt_ref=attempt)

    def state(self):
        return tuple(list(model.objects.order_by('pk').values()) for model in (
            QuotaExecution, QuotaBucket, QuotaReservation, ExportReport, PrivateObject,
            ExecutionAuthorizationRecord, RiskDecision, Resource))

    def denied(self, result, code):
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, code)

    def test_retransmission_and_reassembly_authenticate_output_without_new_logical_effects(self):
        before = self.state()
        files = {path.name: path.read_bytes() for path in self.root.iterdir()}
        calls = []
        read_file, open_file = self.flow.store._read_file, self.flow.crypto.open

        def read_outside_locks(reference, *args):
            self.assertFalse(connection.in_atomic_block)
            calls.append(reference)
            return read_file(reference, *args)

        def authenticate_outside_locks(*args):
            self.assertFalse(connection.in_atomic_block)
            return open_file(*args)

        with ExitStack() as stack:
            for method in ('reserve', 'commit', 'release', 'reconcile', 'require_active'):
                stack.enter_context(patch.object(QuotaService, method, side_effect=AssertionError('quota mutation')))
            for method in ('decide', 'issue', 'consume', 'recheck'):
                stack.enter_context(patch.object(self.flow.risk, method, side_effect=AssertionError('risk mutation')))
            stack.enter_context(patch.object(self.flow, 'load_input', side_effect=AssertionError('source reopened')))
            stack.enter_context(patch.object(self.flow.store, 'publish', side_effect=AssertionError('republished')))
            stack.enter_context(patch.object(self.flow.store, '_read_file', side_effect=read_outside_locks))
            stack.enter_context(patch.object(self.flow.crypto, 'open', side_effect=authenticate_outside_locks))
            opened = self.read()
        self.assertIs(type(opened), BoundedPayload)
        self.assertIs(opened.media_type, MediaType.CSV)
        self.assertEqual(opened.binary, self.expected)
        self.assertEqual(hashlib.sha256(opened.binary).hexdigest(), self.record.report.output_hash)
        self.assertEqual(calls, [self.record.stored.object_ref])
        event_id = content_hash({'domain': 'ds.download-attempt.v1', 'binding': self.binding,
                                 'attempt': 'test/download-1'})
        event = self.flow.audit.sink.read_authenticated(event_id)
        self.assertIs(event.kind, EventKind.AUTHORIZATION)
        self.assertEqual(event.correlation_ref, 'test/download-1')
        self.assertEqual(event.counts, (('processed', 1), ('bytes', len(self.expected))))
        self.assertEqual(dict(event.evidence_hashes), {'ciphertext': self.record.stored.ciphertext_hash,
                                                     'report': content_hash(self.record.report)})
        self.assertEqual(self.state(), before)

        self.reader = assemble_resource_uploads(config_path=self.config_path,
            private_root=self.root, project_ref='resource-upload/synthetic', source_reads=True)
        self.approvals = assemble_export_plan_approvals(config_path=self.config_path)
        self.flow = self.new_flow()
        with patch.object(QuotaService, 'reserve', side_effect=AssertionError('second hold')), \
                patch.object(self.flow.store, 'publish', side_effect=AssertionError('second publish')), \
                patch.object(self.flow, 'load_input', side_effect=AssertionError('source reopened')):
            self.assertEqual(self.read('test/download-2'), opened)
        self.assertEqual(self.state(), before)
        self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, files)
        self.assertEqual(self.flow.reports.delivery(self.binding), self.receipt)
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 6)
        self.assertEqual(self.flow.audit.sink.verify('ds.audit.v2').sequence, 6)
        self.assertEqual(list(self.media.iterdir()), [])

    def test_current_user_policy_and_expiry_are_checked_before_open(self):
        before = self.state()
        with patch.object(self.flow.store, '_read_file', side_effect=AssertionError('denied read')):
            CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
            self.denied(self.read(), ReasonCode.AUTHORIZATION_DENIED)
            CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=True)
            row = PolicyVersion.objects.get(version=self.binding.policy_binding.protection_version)
            policy = PolicySnapshot.from_wire(row.document)
            PolicyVersion.objects.filter(pk=row.pk).update(document=replace(policy, status=PolicyStatus.RETIRED).to_wire())
            self.denied(self.read(), ReasonCode.POLICY_NOT_APPROVED)
            PolicyVersion.objects.filter(pk=row.pk).update(document=row.document)
            with patch.object(self.flow, 'clock', return_value=self.binding.expires_at):
                self.denied(self.read(), ReasonCode.AUTHORIZATION_EXPIRED)
        self.assertEqual(self.state(), before)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)

    def test_revoked_target_approval_after_full_open_refuses_output(self):
        before = self.state()
        open_file = self.flow.crypto.open

        def revoke_after_open(*args):
            self.assertFalse(connection.in_atomic_block)
            opened = open_file(*args)
            self.assertIs(type(opened), BoundedPayload)
            result = self.approvals.manage(user=self.approver, operation='revoke', plan=self.plan,
                binding=self.binding, context=self.output_context)
            self.assertIs(type(result), tuple)
            return opened

        with patch.object(self.flow.crypto, 'open', side_effect=revoke_after_open) as opened:
            self.denied(self.read(), ReasonCode.AUTHORIZATION_DENIED)
        opened.assert_called_once()
        self.assertEqual(self.state(), before)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 5)  # Revocation, not download success.
        event_id = content_hash({'domain': 'ds.download-attempt.v1', 'binding': self.binding,
                                 'attempt': 'test/download-1'})
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id=event_id).exists())

    def test_bad_report_mac_and_raw_delivery_event_never_reach_file_open(self):
        bad = replace(self.record, proof=replace(self.record.proof,
            authentication=b'\x00' * len(self.record.proof.authentication)))
        ExportReport.objects.update(document=bad.to_wire(include_payload=True),
            document_hash=hashlib.sha256(canonical_bytes(bad, include_payload=True)).hexdigest())
        before = self.state()
        with patch.object(self.flow.store, '_read_file', side_effect=AssertionError('untrusted report read')):
            self.denied(self.read(), ReasonCode.REPORT_MISMATCH)
        self.assertEqual(self.state(), before)
        ExportReport.objects.update(document=self.record.to_wire(include_payload=True),
            document_hash=hashlib.sha256(canonical_bytes(self.record, include_payload=True)).hexdigest())
        AuthenticatedAuditEntry.objects.filter(record__event_id=self.receipt.audit.event_id).delete()
        self.assertTrue(SecurityAuditRecord.objects.filter(event_id=self.receipt.audit.event_id).exists())
        before = self.state()
        with patch.object(self.flow.store, '_read_file', side_effect=AssertionError('unauthenticated delivery read')):
            self.denied(self.read(), ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(self.state(), before)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)

    def test_bad_ciphertext_or_wrong_complete_output_cannot_create_download_audit(self):
        encoded = self.path.read_bytes()
        broken = bytes([encoded[0] ^ 1]) + encoded[1:]
        self.path.write_bytes(broken)
        before = self.state()
        self.denied(self.read(), ReasonCode.HASH_MISMATCH)
        self.assertEqual(self.path.read_bytes(), broken)
        self.path.write_bytes(encoded)
        envelope = self.flow.store.read(self.record.stored, self.output_context)
        opened = self.flow.crypto.open(envelope, self.output_context, envelope.key)
        # The real file is intact; this fault is between full open and M4's hash check.
        with patch.object(self.flow.crypto, 'open', return_value=replace(opened, binary=b'wrong\n')):
            self.denied(self.read(), ReasonCode.HASH_MISMATCH)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.path.read_bytes(), encoded)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)

    def test_current_risk_revocation_and_inconsistent_settlement_refuse_output(self):
        authorization = self.risk_authorization
        self.risk_authorization = replace(authorization, allowed_operations=())
        before = self.state()
        self.denied(self.read(), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.state(), before)
        self.risk_authorization = authorization
        quota = QuotaExecution.objects.get()
        terminal = dict(quota.terminal_receipt, settled_amount=1)
        QuotaExecution.objects.filter(pk=quota.pk).update(terminal_receipt=terminal)
        before = self.state()
        self.denied(self.read(), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)

    def test_audit_failure_rolls_back_only_attempt_without_changing_original_delivery(self):
        before = self.state()
        append = self.flow.audit.sink.append

        def fail_after_append(*args):
            result = append(*args)
            self.assertNotIsInstance(result, ProtectionError)
            self.assertEqual(AuthenticatedAuditEntry.objects.count(), 5)
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                   retryable=False, trace_id='test/download-audit')

        with patch.object(self.flow.audit.sink, 'append', side_effect=fail_after_append):
            self.denied(self.read(), ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(self.state(), before)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)
        self.assertEqual(SecurityAuditRecord.objects.count(), 4)
        self.assertEqual(self.flow.audit.sink.verify('ds.audit.v2'), self.receipt.audit)

    def test_lost_attempt_commit_confirmation_is_unknown_without_new_quota_effect(self):
        before = self.state()

        class LostAcknowledgement(DjangoUnitOfWork):
            def __exit__(work, *args):
                super().__exit__(*args)
                raise RuntimeError('synthetic download audit commit confirmation lost')

        self.flow.uow_factory = LostAcknowledgement
        self.denied(self.read(), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(self.state(), before)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 5)
        self.assertEqual(self.flow.reports.delivery(self.binding), self.receipt)
        self.flow.uow_factory = DjangoUnitOfWork
        opened = self.read('test/download-2')
        self.assertIs(type(opened), BoundedPayload)
        self.assertEqual(opened.binary, self.expected)
        self.assertEqual(self.state(), before)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 6)
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)

    def test_audit_lock_wait_rechecks_shorter_consumed_authorization_deadline(self):
        pids, opened, resume = Queue(), Event(), Event()
        open_file = self.flow.crypto.open

        def pause_after_open(*args):
            payload = open_file(*args)
            self.assertIs(type(payload), BoundedPayload)
            opened.set()
            self.assertTrue(resume.wait(timeout=10))
            return payload

        def worker():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    pids.put(cursor.fetchone()[0])
                return self.read()
            finally:
                connection.close()

        with patch.object(self.flow.crypto, 'open', side_effect=pause_after_open), \
                ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker)
            pid = pids.get(timeout=5)
            try:
                self.assertTrue(opened.wait(timeout=10))
                until = timezone.now() + timedelta(seconds=3)
                ExecutionAuthorizationRecord.objects.update(valid_until=until)
                before = self.state()
                with transaction.atomic():
                    # Earlier authenticated reads and full open have finished.
                    # Only the final attempt append can now wait on this fence.
                    list(AuditLedgerLock.objects.select_for_update().all())
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_backend_pid()')
                        main_pid = cursor.fetchone()[0]
                    resume.set()
                    deadline = time.monotonic() + 10
                    blocked = False
                    while time.monotonic() < deadline:
                        with connection.cursor() as cursor:
                            # Refresh activity within this deliberately held transaction.
                            cursor.execute('SELECT pg_stat_clear_snapshot()')
                            cursor.execute('SELECT wait_event_type, query, pg_blocking_pids(pid) '
                                           'FROM pg_stat_activity WHERE pid = %s', [pid])
                            wait, query, blockers = cursor.fetchone()
                        blocked = wait == 'Lock' and main_pid in blockers
                        if blocked:
                            break
                        Event().wait(0.01)
                    self.assertTrue(blocked, 'real PostgreSQL audit lock wait was not observed')
                    self.assertIn('audit_auditledgerlock', query)
                    while timezone.now() < until:
                        Event().wait(0.02)
            finally:
                resume.set()
            result = future.result(timeout=20)
        self.denied(result, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.state(), before)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
