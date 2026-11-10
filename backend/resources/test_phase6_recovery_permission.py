"""Explicit synthetic recovery permissions on isolated PostgreSQL, not role-based grants."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from queue import Queue
from threading import Event
import time
from unittest.mock import Mock, patch

from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.adapters.persistence.models import ExportReport, RecoveryPermission
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.recovery import DjangoRecoveryAuthorization
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.application.audit_gateway import AuditGateway
from data_security.application.export_flow import ExportFlow
from data_security.contracts import (
    ContractViolation, Environment, ExecutionBinding, KeyPurpose, Outlet, ProtectionContext,
    ProtectionError, Purpose, QuotaReceipt, QuotaRecoveryEvent, QuotaState, ReasonCode, content_hash,
)
from data_security.tests.fixtures import examples, recovery_context
from data_security.tests.phase2_fixtures import reference_key
from export_quota.models import QuotaBucket, QuotaReservation
from resources.test_phase6_report_records import ReportRecordFixture


class RecoveryPermissionFixture:
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql')
        self.now = timezone.now()
        self.binding = replace(examples()[ExecutionBinding], environment='test',
                               expires_at=self.now - timedelta(days=1))
        self.principal = recovery_context(self.binding)
        self.permission = RecoveryPermission.objects.create(authorization_ref='recovery/explicit',
            actor_ref=self.principal.actor_ref, binding_hash=content_hash(self.binding),
            allow_release=True, expires_at=self.now + timedelta(minutes=5))
        self.authorize = DjangoRecoveryAuthorization(principal=self.principal,
            authorization_ref=self.permission.authorization_ref, clock=timezone.now)


class RecoveryPermissionTests(RecoveryPermissionFixture, TestCase):
    def test_explicit_permission_for_old_export_returns_current_audit_identity(self):
        actor = self.authorize(self.binding, 'release')
        self.assertIsInstance(actor, ProtectionContext)
        self.assertEqual((actor.actor_ref, actor.authorization_ref),
                         (self.principal.actor_ref, self.permission.authorization_ref))
        self.assertEqual((actor.object_ref, actor.object_version, actor.scope_refs),
                         (self.binding.execution_id, self.binding.asset_version, (self.binding.reservation_id,)))
        self.assertEqual((actor.outlet, actor.purpose), (Outlet.AUDIT, Purpose.SECURITY_AUDIT))
        self.assertEqual((actor.source_ref, actor.source_version, actor.source_hash), (None, None, None))
        self.assertLess(self.binding.expires_at, timezone.now())
        self.assertEqual(RecoveryPermission.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.count(), 0)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)

    def test_missing_permission_and_default_flags_do_not_infer_role_or_export_rights(self):
        RecoveryPermission.objects.all().delete()
        self.assertEqual(self.authorize(self.binding, 'release').code, ReasonCode.AUTHORIZATION_DENIED)
        RecoveryPermission.objects.create(authorization_ref=self.permission.authorization_ref,
            actor_ref=self.principal.actor_ref, binding_hash=content_hash(self.binding),
            expires_at=self.now + timedelta(minutes=5))
        for operation in ('release', 'reconcile', 'unknown', 'publish'):
            with self.subTest(operation=operation):
                self.assertEqual(self.authorize(self.binding, operation).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(RecoveryPermission.objects.count(), 1)

    def test_operations_are_independent_and_permission_changes_are_not_cached(self):
        self.assertEqual(self.authorize(self.binding, 'reconcile').code, ReasonCode.AUTHORIZATION_DENIED)
        RecoveryPermission.objects.filter(pk=self.permission.pk).update(allow_release=False, allow_reconcile=True)
        self.assertEqual(self.authorize(self.binding, 'release').code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertIsInstance(self.authorize(self.binding, 'reconcile'), ProtectionContext)

    def test_actor_and_every_changed_binding_component_are_denied(self):
        altered = ({'idempotency_key': 'other/idempotency'}, {'request_fingerprint': 'a' * 64},
            {'request_id': 'other/request'}, {'authorization_id': 'other/authorization'},
            {'decision_id': 'other/decision'}, {'asset_version': 'other/version'},
            {'execution_id': 'other/execution'}, {'reservation_id': 'other/reservation'},
            {'subject_ref': 'other/subject'}, {'domain_ref': 'other/domain'}, {'environment': 'evaluation'},
            {'quantity': self.binding.quantity + 1}, {'expires_at': self.binding.expires_at + timedelta(seconds=1)},
            {'policy_binding': replace(self.binding.policy_binding, risk_version='other/risk')},
            {'scope': replace(self.binding.scope, sheets=(replace(self.binding.scope.sheets[0],
                                                                 sheet_id='other-sheet'),))})
        for change in altered:
            with self.subTest(field=next(iter(change))):
                self.assertEqual(self.authorize(replace(self.binding, **change), 'release').code,
                                 ReasonCode.AUTHORIZATION_DENIED)
        other = DjangoRecoveryAuthorization(principal=replace(self.principal, actor_ref='actor/other'),
            authorization_ref=self.permission.authorization_ref, clock=timezone.now)
        self.assertEqual(other(self.binding, 'release').code, ReasonCode.AUTHORIZATION_DENIED)

    def test_revoked_and_expired_permissions_deny_including_exact_deadline(self):
        RecoveryPermission.objects.filter(pk=self.permission.pk).update(revoked_at=self.now)
        self.assertEqual(self.authorize(self.binding, 'release').code, ReasonCode.AUTHORIZATION_DENIED)
        RecoveryPermission.objects.filter(pk=self.permission.pk).update(revoked_at=None, expires_at=self.now)
        self.authorize.clock = lambda: self.now
        self.assertEqual(self.authorize(self.binding, 'release').code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.authorize.clock = timezone.now
        self.assertEqual(self.authorize(self.binding, 'release').code, ReasonCode.AUTHORIZATION_EXPIRED)

    def test_database_failure_never_returns_permission(self):
        with patch.object(RecoveryPermission.objects, 'select_for_update', side_effect=DatabaseError('synthetic')):
            self.assertEqual(self.authorize(self.binding, 'release').code, ReasonCode.DELIVERY_UNKNOWN)

    def test_constructor_does_not_accept_client_wire_or_production_identity(self):
        for principal in (True, self.principal.to_wire(), replace(self.principal, environment=Environment.PRODUCTION)):
            with self.subTest(type=type(principal).__name__), self.assertRaises(ContractViolation):
                DjangoRecoveryAuthorization(principal=principal, authorization_ref='recovery/explicit',
                                            clock=timezone.now)


class RecoveryPermissionLockTests(RecoveryPermissionFixture, TransactionTestCase):
    def test_call_outside_short_uow_is_denied(self):
        self.assertFalse(connection.in_atomic_block)
        self.assertEqual(self.authorize(self.binding, 'release').code, ReasonCode.AUTHORIZATION_DENIED)

    def test_real_permission_lock_wait_observes_expiry_and_committed_revocation(self):
        for change in ('expiry', 'revocation'):
            with self.subTest(change=change):
                until = timezone.now() + timedelta(seconds=1)
                RecoveryPermission.objects.filter(pk=self.permission.pk).update(
                    revoked_at=None, expires_at=until if change == 'expiry' else until + timedelta(minutes=5))
                pids = Queue()
                def worker():
                    close_old_connections()
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT pg_backend_pid()')
                            pids.put(cursor.fetchone()[0])
                        with DjangoUnitOfWork():
                            return self.authorize(self.binding, 'release')
                    finally:
                        connection.close()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with transaction.atomic():
                        RecoveryPermission.objects.select_for_update().get(pk=self.permission.pk)
                        future = pool.submit(worker)
                        pid = pids.get(timeout=5)
                        deadline = time.monotonic() + 10
                        blocked = False
                        while time.monotonic() < deadline:
                            with connection.cursor() as cursor:
                                cursor.execute('SELECT cardinality(pg_blocking_pids(%s)) > 0', [pid])
                                blocked = cursor.fetchone()[0]
                            if blocked:
                                break
                            Event().wait(0.01)
                        self.assertTrue(blocked, 'real PostgreSQL permission lock wait was not observed')
                        if change == 'expiry':
                            while timezone.now() < until:
                                Event().wait(0.02)
                        else:
                            RecoveryPermission.objects.filter(pk=self.permission.pk).update(revoked_at=timezone.now())
                    result = future.result(timeout=15)
                self.assertEqual(result.code, ReasonCode.AUTHORIZATION_EXPIRED if change == 'expiry'
                                 else ReasonCode.AUTHORIZATION_DENIED)


class RecoveryPermissionFlowFixture(ReportRecordFixture):
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql')
        self.binding = replace(self.record.binding, expires_at=timezone.now() + timedelta(minutes=5))
        with DjangoUnitOfWork() as work:
            self.assertIs(self.repository.begin(self.record.plan, self.binding, self.record.context), True)
            work.commit()
        self.quota = DjangoQuotaPort(environment='test', window_key='permission', limit=20)
        self.assertIsInstance(self.quota.reserve(self.binding), QuotaReceipt)
        self.principal = recovery_context(self.binding)
        self.permission = RecoveryPermission.objects.create(authorization_ref='recovery/flow-explicit',
            actor_ref=self.principal.actor_ref, binding_hash=content_hash(self.binding),
            allow_release=True, allow_reconcile=True, expires_at=timezone.now() + timedelta(minutes=5))
        self.authorize = DjangoRecoveryAuthorization(principal=self.principal,
            authorization_ref=self.permission.authorization_ref, clock=timezone.now)
        self.sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto,
                                   key=reference_key(KeyPurpose.AUDIT), context=self.context)
        self.flow = ExportFlow(reports=self.repository, authenticator=self.auth, store=self.store,
            risk=Mock(), quota=self.quota, policies=Mock(), authorize=Mock(), audit=AuditGateway(sink=self.sink),
            uow_factory=DjangoUnitOfWork, clock=timezone.now, authorize_recovery=self.authorize)


class RecoveryPermissionFlowTests(RecoveryPermissionFlowFixture, TestCase):
    def test_authorized_release_replays_with_current_permission_audited(self):
        receipt = self.flow.release(self.binding)
        self.assertIsInstance(receipt, QuotaReceipt)
        self.assertIs(receipt.state, QuotaState.RELEASED)
        event = QuotaRecoveryEvent.from_wire(SecurityAuditRecord.objects.get().event)
        self.assertEqual((event.actor_ref, event.authorization_ref, event.quota),
                         (self.principal.actor_ref, self.permission.authorization_ref, receipt))
        self.assertEqual(self.flow.release(self.binding), receipt)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        RecoveryPermission.objects.filter(pk=self.permission.pk).update(revoked_at=timezone.now())
        self.denied(self.flow.release(self.binding), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertNotIsInstance(self.sink.verify('ds.audit.v2'), ProtectionError)

    def test_denied_permission_rolls_back_report_abort_and_keeps_full_hold(self):
        for change in ({'allow_release': False}, {'actor_ref': 'actor/other'}, {'binding_hash': 'b' * 64},
                       {'revoked_at': timezone.now()}, {'expires_at': timezone.now() - timedelta(seconds=1)}):
            with self.subTest(field=next(iter(change))), transaction.atomic():
                RecoveryPermission.objects.filter(pk=self.permission.pk).update(**change)
                self.assertIsInstance(self.flow.release(self.binding), ProtectionError)
                self.assertEqual(ExportReport.objects.get().state, 'preparing')
                self.assertEqual(QuotaBucket.objects.get().active_reserved, self.binding.quantity)
                self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
                self.assertEqual(SecurityAuditRecord.objects.count(), 0)
                self.assertTrue(self.path(self.record.stored).exists())
                transaction.set_rollback(True)

    def test_unknown_requires_reconcile_permission_and_does_not_repeat_settlement(self):
        self.assertIs(self.quota.reconcile(self.binding, None, 'test-only/uncertain').state, QuotaState.UNKNOWN)
        RecoveryPermission.objects.filter(pk=self.permission.pk).update(allow_reconcile=False)
        self.denied(self.flow.reconcile(self.binding), ReasonCode.AUTHORIZATION_DENIED)
        self.denied(self.flow.release(self.binding), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        RecoveryPermission.objects.filter(pk=self.permission.pk).update(allow_reconcile=True)
        receipt = self.flow.reconcile(self.binding)
        self.assertIsInstance(receipt, QuotaReceipt)
        self.assertEqual((receipt.state, receipt.settled_amount), (QuotaState.COMMITTED, 0))
        self.assertEqual(self.flow.reconcile(self.binding), receipt)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 0)
        self.assertEqual(QuotaBucket.objects.get().settled, 0)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')

    def test_valid_permission_cannot_bypass_missing_authenticated_audit(self):
        self.flow.audit = AuditGateway(sink=DjangoAuditSink(clock=timezone.now))
        self.denied(self.flow.release(self.binding), ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, self.binding.quantity)
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)


class RecoveryPermissionFlowLockTests(RecoveryPermissionFlowFixture, TransactionTestCase):
    def test_report_lock_wait_observes_current_permission_and_rolls_back_abort(self):
        for change in ('expiry', 'revocation'):
            with self.subTest(change=change):
                until = timezone.now() + timedelta(seconds=1)
                RecoveryPermission.objects.filter(pk=self.permission.pk).update(
                    revoked_at=None, expires_at=until if change == 'expiry' else until + timedelta(minutes=5))
                pids = Queue()
                def worker():
                    close_old_connections()
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT pg_backend_pid()')
                            pids.put(cursor.fetchone()[0])
                        return self.flow.release(self.binding)
                    finally:
                        connection.close()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with transaction.atomic():
                        ExportReport.objects.select_for_update().get(execution_id=self.binding.execution_id)
                        future = pool.submit(worker)
                        pid = pids.get(timeout=5)
                        deadline = time.monotonic() + 10
                        blocked = False
                        while time.monotonic() < deadline:
                            with connection.cursor() as cursor:
                                cursor.execute('SELECT cardinality(pg_blocking_pids(%s)) > 0', [pid])
                                blocked = cursor.fetchone()[0]
                            if blocked:
                                break
                            Event().wait(0.01)
                        self.assertTrue(blocked, 'real PostgreSQL report lock wait was not observed')
                        if change == 'expiry':
                            while timezone.now() < until:
                                Event().wait(0.02)
                        else:
                            RecoveryPermission.objects.filter(pk=self.permission.pk).update(revoked_at=timezone.now())
                    result = future.result(timeout=15)
                self.denied(result, ReasonCode.AUTHORIZATION_EXPIRED if change == 'expiry'
                            else ReasonCode.AUTHORIZATION_DENIED)
                self.assertEqual(ExportReport.objects.get().state, 'preparing')
                self.assertEqual(QuotaBucket.objects.get().active_reserved, self.binding.quantity)
                self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
                self.assertEqual(SecurityAuditRecord.objects.count(), 0)
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
                self.assertTrue(self.path(self.record.stored).exists())
