"""Real B and PostgreSQL permission ownership; no role-only grant or quota mutation."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from ctf_backend.security_bootstrap import assemble_recovery_permissions
from data_security.adapters.persistence.models import RecoveryPermission
from data_security.contracts import AuditReceipt, ExecutionBinding, ProtectionContext, ReasonCode, content_hash
from data_security.tests.fixtures import examples
from export_quota.models import QuotaReservation
from resources.test_phase6_private_uploads import PrivateResourceUploadFixture
from users.models import CTFUser
from .models import AuthenticatedAuditEntry, SecurityAuditRecord


class RecoveryPermissionOwnerTests(PrivateResourceUploadFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.owner = assemble_recovery_permissions(config_path=self.config_path)
        self.grantee = CTFUser.objects.create_user(username='recovery-grantee', role='student')
        self.binding = replace(examples()[ExecutionBinding], environment='evaluation',
            expires_at=timezone.now() - timedelta(days=1))
        self.until = timezone.now() + timedelta(minutes=5)
        self.add_permission = Permission.objects.get(content_type__app_label='security_policies',
            codename='add_recoverypermission')
        self.change_permission = Permission.objects.get(content_type__app_label='security_policies',
            codename='change_recoverypermission')
        self.teacher.user_permissions.add(self.add_permission, self.change_permission)

    def grant(self, **changes):
        return self.owner.manage(**{**dict(user=self.teacher, binding=self.binding, operation='grant',
            grantee_id=self.grantee.pk, expires_at=self.until, allow_release=True), **changes})

    def test_real_grant_current_actor_and_explicit_flags_then_audited_revocation(self):
        reference, receipt = self.grant()
        self.assertIs(type(receipt), AuditReceipt)
        permission = RecoveryPermission.objects.get()
        self.assertEqual(permission.actor_ref, 'user/' + str(self.grantee.pk))
        self.assertEqual(permission.binding_hash, content_hash(self.binding))
        with transaction.atomic():
            actor = self.owner.authorize(user=self.grantee, binding=self.binding,
                operation='release', authorization_ref=reference)
            self.assertIs(type(actor), ProtectionContext)
            self.assertEqual(actor.actor_ref, permission.actor_ref)
            self.assertEqual(actor.authorization_ref, reference)
            result = self.owner.authorize(user=self.grantee, binding=self.binding,
                operation='reconcile', authorization_ref=reference)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        revoked_ref, revoked = self.owner.manage(user=self.teacher, binding=self.binding,
            operation='revoke', authorization_ref=reference)
        self.assertEqual(revoked_ref, reference)
        self.assertIs(type(revoked), AuditReceipt)
        with transaction.atomic():
            result = self.owner.authorize(user=self.grantee, binding=self.binding,
                operation='release', authorization_ref=reference)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(self.uploads.audit.sink.verify('ds.audit.v2'), revoked)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_current_django_capability_not_cached_role_controls_management(self):
        self.teacher.user_permissions.clear()
        CTFUser.objects.filter(pk=self.teacher.pk).update(role='admin', is_staff=True)
        with patch.object(self.owner, 'write_permission', side_effect=AssertionError('unauthorized write')):
            self.assertEqual(self.grant().code, ReasonCode.AUTHORIZATION_DENIED)
        self.teacher.user_permissions.add(self.add_permission)
        reference, _ = self.grant()
        self.assertEqual(self.owner.manage(user=self.teacher, binding=self.binding,
            operation='revoke', authorization_ref=reference).code, ReasonCode.AUTHORIZATION_DENIED)
        self.teacher.user_permissions.add(self.change_permission)
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
        self.assertEqual(self.owner.manage(user=self.teacher, binding=self.binding,
            operation='revoke', authorization_ref=reference).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertIsNone(RecoveryPermission.objects.get().revoked_at)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_current_grantee_and_full_binding_are_rechecked_without_role_inference(self):
        reference, _ = self.grant()
        with transaction.atomic():
            CTFUser.objects.filter(pk=self.grantee.pk).update(is_active=False)
            with patch.object(self.owner, 'read_permission', side_effect=AssertionError('inactive actor read')):
                result = self.owner.authorize(user=self.grantee, binding=self.binding,
                    operation='release', authorization_ref=reference)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
            CTFUser.objects.filter(pk=self.grantee.pk).update(is_active=True)
            result = self.owner.authorize(user=self.grantee,
                binding=replace(self.binding, quantity=self.binding.quantity + 1),
                operation='release', authorization_ref=reference)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        for binding in (self.binding.to_wire(), replace(self.binding, environment='production')):
            result = self.owner.manage(user=self.teacher, binding=binding, operation='revoke',
                authorization_ref=reference)
            self.assertEqual(result.code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertIsNone(RecoveryPermission.objects.get().revoked_at)

    def test_actual_ledger_failure_rolls_back_grant_and_revocation(self):
        writer = self.owner.write_permission.__self__
        record = writer.record_event

        def fail_after_record(event, durability):
            self.assertIs(type(record(event, durability)), AuditReceipt)
            raise DatabaseError('synthetic failure after permission event')

        with patch.object(writer, 'record_event', side_effect=fail_after_record):
            self.assertEqual(self.grant().code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertFalse(RecoveryPermission.objects.exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.exists())
        reference, _ = self.grant()
        with patch.object(writer, 'record_event', side_effect=fail_after_record):
            result = self.owner.manage(user=self.teacher, binding=self.binding,
                operation='revoke', authorization_ref=reference)
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertIsNone(RecoveryPermission.objects.get().revoked_at)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)

    def test_invalid_grant_fields_and_inactive_grantee_never_reach_writer(self):
        for changes in ({'expires_at': timezone.now() - timedelta(seconds=1)},
                        {'grantee_id': True}, {'allow_release': False},
                        {'allow_reconcile': 'true'}, {'authorization_ref': 'client/chosen'}):
            with self.subTest(changes=tuple(changes)), patch.object(self.owner, 'write_permission',
                    side_effect=AssertionError('invalid grant wrote permission')):
                self.assertEqual(self.grant(**changes).code, ReasonCode.INVALID_VALUE)
        CTFUser.objects.filter(pk=self.grantee.pk).update(is_active=False)
        self.assertEqual(self.grant().code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(RecoveryPermission.objects.exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.exists())

    def test_legacy_receipt_cannot_commit_permission(self):
        writer = self.owner.write_permission.__self__
        record = writer.record_event

        def downgrade(event, durability):
            return replace(record(event, durability), chain_version='v1')

        with patch.object(writer, 'record_event', side_effect=downgrade):
            self.assertEqual(self.grant().code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertFalse(RecoveryPermission.objects.exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.exists())
        self.assertFalse(SecurityAuditRecord.objects.exists())

    def test_lost_commit_confirmation_preserves_grant_and_returns_its_opaque_reference(self):
        @contextmanager
        def lose_confirmation():
            with transaction.atomic():
                yield
            self.assertFalse(connection.in_atomic_block)
            raise DatabaseError('synthetic permission confirmation lost')

        with patch('data_security.adapters.persistence.recovery.transaction',
                   SimpleNamespace(atomic=lose_confirmation)):
            result = self.grant()
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(result.trace_id, RecoveryPermission.objects.get().authorization_ref)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertIs(type(self.uploads.audit.sink.verify('ds.audit.v2')), AuditReceipt)
        self.assertFalse(QuotaReservation.objects.exists())
