"""Isolated target approvals with current Django actors and the real v2 audit gateway."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
import json
from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from ctf_backend.security_bootstrap import assemble_export_plan_approvals
from data_security.adapters.persistence.models import ExportPlanApproval
from data_security.contracts import (
    ActionPlan, AuditReceipt, ContractViolation, Environment, ExecutionBinding, ObjectContext,
    ProtectionContext, ProtectionError, ReasonCode, Unresolved, content_hash,
)
from data_security.tests.fixtures import examples
from export_quota.models import QuotaReservation
from resources.test_phase6_private_uploads import PrivateResourceUploadFixture
from users.models import CTFUser
from .models import AuthenticatedAuditEntry, SecurityAuditRecord


class ExportPlanOwnerTests(PrivateResourceUploadFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.owner = assemble_export_plan_approvals(config_path=self.config_path)
        self.requester = CTFUser.objects.create_user(username='target-requester', role='teacher')
        self.add_permission = Permission.objects.get(content_type__app_label='security_policies',
                                                      codename='add_exportplanapproval')
        self.change_permission = Permission.objects.get(content_type__app_label='security_policies',
                                                         codename='change_exportplanapproval')
        self.teacher.user_permissions.add(self.add_permission, self.change_permission)
        template = examples()[ActionPlan]
        now = timezone.now()
        source = replace(template.source, source_environment='evaluation',
                         approval_basis_ref='synthetic/source-approval', approval_basis_version='1')
        values = dict(template.content(), source=source, created_at=now, expires_at=now + timedelta(minutes=5))
        self.plan = ActionPlan(**values, plan_hash=content_hash(values), approval=None)
        self.binding = replace(examples()[ExecutionBinding], environment='evaluation',
                               subject_ref='user/' + str(self.requester.pk), expires_at=self.plan.expires_at)
        self.context = replace(examples()[ObjectContext], environment=Environment.EVALUATION,
                               object_version=self.binding.asset_version, authorization_ref=self.binding.authorization_id)

    def approve(self, **changes):
        return self.owner.manage(**{**dict(user=self.teacher, operation='approve', plan=self.plan,
            binding=self.binding, context=self.context, requester=self.requester), **changes})

    def authorize(self, plan, **changes):
        return self.owner.authorize(**{**dict(user=self.requester, plan=plan,
                                              binding=self.binding, context=self.context), **changes})

    def revoke(self, plan):
        return self.owner.manage(user=self.teacher, operation='revoke', plan=plan,
                                 binding=self.binding, context=self.context)

    def test_real_two_person_approval_and_restart_then_current_revocation(self):
        approved, receipt = self.approve()
        self.assertIsInstance(receipt, AuditReceipt)
        self.assertEqual(approved.content(), self.plan.content())
        self.assertEqual(approved.approval.requested_by, self.binding.subject_ref)
        self.assertEqual(approved.approval.approved_by, 'user/' + str(self.teacher.pk))
        stored = ExportPlanApproval.objects.get()
        self.assertEqual(stored.binding_hash, content_hash(self.binding))
        self.assertEqual(stored.context_hash, content_hash(self.context))
        self.assertEqual(stored.document, approved.approval.to_wire())
        self.assertNotIn('actions', stored.document)
        fresh = assemble_export_plan_approvals(config_path=self.config_path)
        principal = fresh.authorize(user=self.requester, plan=approved, binding=self.binding, context=self.context)
        self.assertIs(type(principal), ProtectionContext)
        self.assertEqual(principal.actor_ref, self.binding.subject_ref)
        _, revoked = self.revoke(approved)
        self.assertEqual(self.authorize(approved).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.uploads.audit.sink.verify('ds.audit.v2'), revoked)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_current_capability_and_active_users_not_cached_roles_or_self_approval(self):
        self.assertTrue(self.teacher.has_perm('security_policies.add_exportplanapproval'))
        self.teacher.user_permissions.clear()
        CTFUser.objects.filter(pk=self.teacher.pk).update(role='admin', is_staff=True)
        self.assertEqual(self.approve().code, ReasonCode.AUTHORIZATION_DENIED)
        self.teacher.user_permissions.add(self.add_permission, self.change_permission)
        self.requester.user_permissions.add(self.add_permission)
        self.assertEqual(self.approve(user=self.requester).code, ReasonCode.AUTHORIZATION_DENIED)
        approved, _ = self.approve()
        CTFUser.objects.filter(pk=self.requester.pk).update(is_active=False)
        self.assertEqual(self.authorize(approved).code, ReasonCode.AUTHORIZATION_DENIED)
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
        self.assertEqual(self.revoke(approved).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertIsNone(ExportPlanApproval.objects.get().revoked_at)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_exact_target_full_binding_and_approval_cannot_be_substituted(self):
        approved, _ = self.approve()
        forged = replace(approved, approval=replace(approved.approval, approved_by='user/99999'))
        values = dict(approved.content(), input_hash='f' * 64)
        changed = ActionPlan(**values, plan_hash=content_hash(values),
            approval=replace(approved.approval, content_hash=content_hash(values)))
        for plan in (self.plan, forged, changed):
            self.assertEqual(self.authorize(plan).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.authorize(approved, binding=replace(self.binding, quantity=self.binding.quantity + 1)).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.authorize(approved, context=replace(self.context, project_ref='other/project')).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(ExportPlanApproval.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_unapproved_source_unresolved_expired_outer_transaction_and_unconfigured_chain_rejected(self):
        with transaction.atomic():
            self.assertEqual(self.approve().code, ReasonCode.DELIVERY_UNKNOWN)
        for changes, code in (({'source': replace(self.plan.source, approval_basis_ref=None, approval_basis_version=None)},
                               ReasonCode.SOURCE_NOT_APPROVED),
                              ({'unresolved': (examples()[Unresolved],)},
                               ReasonCode.SCOPE_INCOMPLETE),
                              ({'created_at': timezone.now() - timedelta(minutes=2),
                                'expires_at': timezone.now() - timedelta(minutes=1)}, ReasonCode.AUTHORIZATION_EXPIRED)):
            values = dict(self.plan.content(), **changes)
            plan = ActionPlan(**values, plan_hash=content_hash(values), approval=None)
            self.assertEqual(self.approve(plan=plan).code, code)
        self.assertEqual(self.approve(plan=self.plan.to_wire()).code, ReasonCode.INVALID_TYPE)
        self.assertFalse(ExportPlanApproval.objects.exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.exists())
        self.config.pop('audit_chain')
        self.config_path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            assemble_export_plan_approvals(config_path=self.config_path)

    def test_audit_failure_after_append_and_old_chain_receipt_roll_back_all_changes(self):
        writer = self.owner.write_permission.__self__
        record = writer.record_event
        def fail(event, durability):
            self.assertIsInstance(record(event, durability), AuditReceipt)
            raise DatabaseError('synthetic failure after target approval audit')
        with patch.object(writer, 'record_event', side_effect=fail):
            self.assertEqual(self.approve().code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertFalse(ExportPlanApproval.objects.exists())
        self.assertFalse(SecurityAuditRecord.objects.exists())
        def downgrade(event, durability):
            return replace(record(event, durability), chain_version='v1')
        with patch.object(writer, 'record_event', side_effect=downgrade):
            self.assertEqual(self.approve().code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertFalse(ExportPlanApproval.objects.exists())
        approved, _ = self.approve()
        with patch.object(writer, 'record_event', side_effect=fail):
            self.assertEqual(self.revoke(approved).code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertIsNone(ExportPlanApproval.objects.get().revoked_at)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_lost_commit_ack_keeps_approval_and_returns_stable_reference(self):
        @contextmanager
        def lose_ack():
            with transaction.atomic():
                yield
            raise DatabaseError('synthetic lost target approval acknowledgement')
        with patch('data_security.adapters.persistence.export_plans.transaction', SimpleNamespace(atomic=lose_ack)):
            result = self.approve()
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(result.trace_id, ExportPlanApproval.objects.get().approval_ref)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_reconcile_unknown_reloads_original_approval_without_signing_or_writing(self):
        @contextmanager
        def lose_ack():
            with transaction.atomic():
                yield
            raise DatabaseError('synthetic lost target approval acknowledgement')
        with patch('data_security.adapters.persistence.export_plans.transaction', SimpleNamespace(atomic=lose_ack)):
            failure = self.approve()
        self.assertEqual(failure.code, ReasonCode.DELIVERY_UNKNOWN)
        fresh = assemble_export_plan_approvals(config_path=self.config_path)
        writer = fresh.read_approval.__self__
        with patch.object(fresh, 'identity', side_effect=AssertionError('must not issue again')), \
             patch.object(writer, 'record_event', side_effect=AssertionError('must not append again')), \
             patch.object(writer, 'read_event', wraps=writer.read_event) as read:
            restored = fresh.reconcile(user=self.teacher, approval_ref=failure.trace_id,
                plan=self.plan, binding=self.binding, context=self.context)
        self.assertIsInstance(restored, ActionPlan)
        self.assertEqual(restored.content(), self.plan.content())
        self.assertEqual(restored.approval.to_wire(), ExportPlanApproval.objects.get().document)
        read.assert_called_once_with(failure.trace_id + '/approve')
        self.assertIsInstance(self.authorize(restored), ProtectionContext)
        self.assertEqual(fresh.reconcile(user=self.teacher, approval_ref=failure.trace_id,
            plan=self.plan, binding=self.binding, context=self.context), restored)
        self.assertEqual(ExportPlanApproval.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_reconcile_current_permission_revocation_expiry_and_outer_transaction(self):
        approved, _ = self.approve()
        args = dict(user=self.teacher, approval_ref=approved.approval.approval_ref,
                    plan=self.plan, binding=self.binding, context=self.context)
        with transaction.atomic():
            self.assertEqual(self.owner.reconcile(**args).code, ReasonCode.DELIVERY_UNKNOWN)
        self.teacher.user_permissions.clear()
        self.assertEqual(self.owner.reconcile(**args).code, ReasonCode.AUTHORIZATION_DENIED)
        self.teacher.user_permissions.add(self.add_permission, self.change_permission)
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
        self.assertEqual(self.owner.reconcile(**args).code, ReasonCode.AUTHORIZATION_DENIED)
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=True)
        writer = self.owner.read_approval.__self__
        with patch.object(writer, 'clock', return_value=self.plan.expires_at):
            self.assertEqual(self.owner.reconcile(**args).code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.revoke(approved)
        self.assertEqual(self.owner.reconcile(**args).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_reconcile_rejects_substituted_binding_document_and_unauthenticated_event(self):
        approved, _ = self.approve()
        args = dict(user=self.teacher, approval_ref=approved.approval.approval_ref,
                    plan=self.plan, binding=self.binding, context=self.context)
        self.assertEqual(self.owner.reconcile(**dict(args, approval_ref='plan-approval/missing')).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.owner.reconcile(**dict(args, binding=replace(self.binding, quantity=self.binding.quantity + 1))).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.owner.reconcile(**dict(args, context=replace(self.context, project_ref='other/project'))).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        row = ExportPlanApproval.objects.get()
        original = row.document
        row.document = replace(approved.approval, approved_by='user/99999').to_wire()
        row.save(update_fields=['document'])
        self.assertEqual(self.owner.reconcile(**args).code, ReasonCode.REPORT_MISMATCH)
        row.document = original
        row.save(update_fields=['document'])
        event = SecurityAuditRecord.objects.get()
        event.event = dict(event.event, actor_ref='user/99999')
        event.save(update_fields=['event'])
        self.assertEqual(self.owner.reconcile(**args).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(ExportPlanApproval.objects.count(), 1)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_reconcile_read_transaction_exit_failure_is_unknown_without_mutation(self):
        approved, _ = self.approve()
        @contextmanager
        def lose_ack():
            with transaction.atomic():
                yield
            raise DatabaseError('synthetic lost approval read acknowledgement')
        with patch('data_security.adapters.persistence.export_plans.transaction', SimpleNamespace(atomic=lose_ack)):
            result = self.owner.reconcile(user=self.teacher, approval_ref=approved.approval.approval_ref,
                plan=self.plan, binding=self.binding, context=self.context)
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(result.trace_id, approved.approval.approval_ref)
        self.assertEqual(ExportPlanApproval.objects.get().document, approved.approval.to_wire())
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_real_permission_lock_wait_rechecks_expiry(self):
        approved, _ = self.approve()
        started, pause = Event(), Event()
        worker = {}
        def authorize():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    worker['pid'] = cursor.fetchone()[0]
                started.set()
                return self.authorize(approved)
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                row = ExportPlanApproval.objects.select_for_update().get()
                future = pool.submit(authorize)
                self.assertTrue(started.wait(10))
                blocked, deadline = False, monotonic() + 10
                with connection.cursor() as cursor:
                    while monotonic() < deadline:
                        cursor.execute('SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))', [worker['pid']])
                        blocked = cursor.fetchone()[0]
                        if blocked:
                            break
                        pause.wait(0.01)
                self.assertTrue(blocked, 'approval reader must actually wait for our PostgreSQL lock')
                row.expires_at = timezone.now() - timedelta(seconds=1)
                row.save(update_fields=['expires_at'])
            self.assertEqual(future.result(timeout=20).code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
