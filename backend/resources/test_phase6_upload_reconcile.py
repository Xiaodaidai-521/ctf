"""Observe committed private uploads without replaying writes or treating absence as zero."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import ProtectionError, ReasonCode
from users.models import CTFUser

from .models import Resource
from .test_phase6_private_uploads import PrivateResourceUploadFixture


class ResourceUploadReconcileTests(PrivateResourceUploadFixture, TransactionTestCase):
    def test_confirmation_loss_is_resolved_from_committed_resource_and_both_events(self):
        @contextmanager
        def lose_confirmation():
            with transaction.atomic():
                yield
            raise DatabaseError('synthetic lost confirmation')

        with patch('resources.private_uploads.transaction', SimpleNamespace(atomic=lose_confirmation)):
            response = self.post(data=self.data(cover=True))
        self.assertEqual(response.data[0].code, ReasonCode.DELIVERY_UNKNOWN.value)
        resource = Resource.objects.get()
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch.object(self.uploads, 'create', side_effect=AssertionError('replayed upload')), \
             patch.object(self.uploads.audit, 'record', side_effect=AssertionError('replayed event')), \
             patch.object(self.preparation.store, 'publish', side_effect=AssertionError('published')):
            first = self.uploads.reconcile(user=self.teacher, resource_id=resource.pk)
            self.assertFalse(connection.in_atomic_block)
            self.assertIs(type(first), tuple)
            self.assertEqual(len(first), 2)
            self.assertEqual(self.uploads.reconcile(user=self.teacher, resource_id=resource.pk), first)
        self.assertEqual(Resource.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_outer_uncommitted_upload_cannot_be_confirmed_and_absence_is_not_zero(self):
        with transaction.atomic():
            self.assertEqual(self.post().status_code, 201)
            resource_id = Resource.objects.get().pk
            with patch.object(self.uploads, 'authenticated_references',
                              side_effect=AssertionError('read uncommitted evidence')):
                result = self.uploads.reconcile(user=self.teacher, resource_id=resource_id)
            self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
            transaction.set_rollback(True)
        result = self.uploads.reconcile(user=self.teacher, resource_id=resource_id)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(Resource.objects.count(), 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_current_access_and_authenticated_evidence_are_required_on_every_observation(self):
        self.assertEqual(self.post().status_code, 201)
        resource = Resource.objects.get()
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
        result = self.uploads.reconcile(user=self.teacher, resource_id=resource.pk)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=True)
        AuthenticatedAuditEntry.objects.all().delete()
        result = self.uploads.reconcile(user=self.teacher, resource_id=resource.pk)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_read_transaction_exit_failure_and_manual_transaction_remain_unknown(self):
        self.assertEqual(self.post().status_code, 201)
        resource = Resource.objects.get()
        @contextmanager
        def fail_read_exit():
            with transaction.atomic():
                yield
            raise DatabaseError('synthetic read exit failure')

        with patch('resources.private_uploads.transaction', SimpleNamespace(atomic=fail_read_exit)):
            result = self.uploads.reconcile(user=self.teacher, resource_id=resource.pk)
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        connection.set_autocommit(False)
        try:
            result = self.uploads.reconcile(user=self.teacher, resource_id=resource.pk)
            self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        finally:
            connection.rollback()
            connection.set_autocommit(True)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
