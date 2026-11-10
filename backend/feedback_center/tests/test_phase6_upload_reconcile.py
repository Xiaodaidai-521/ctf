"""Committed upload observations are not delivery receipts or permission to replay."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import ProtectionError, ReasonCode
from users.models import CTFUser
from feedback_center.models import FeedbackAttachment, FeedbackTicket
from .test_phase6_private_uploads import PrivateFeedbackUploadFixture


class FeedbackUploadReconcileTests(PrivateFeedbackUploadFixture, TransactionTestCase):
    def test_confirmation_loss_is_resolved_without_replaying_or_publishing(self):
        @contextmanager
        def lose_confirmation():
            with transaction.atomic():
                yield
            raise DatabaseError('synthetic lost confirmation')

        with patch('feedback_center.private_uploads.transaction', SimpleNamespace(atomic=lose_confirmation)):
            response = self.post()
        self.assertEqual(response.data['code'], ReasonCode.DELIVERY_UNKNOWN.value)
        attachment = FeedbackAttachment.objects.get()
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch.object(self.uploads, 'create', side_effect=AssertionError('replayed upload')), \
             patch.object(self.uploads.audit, 'record', side_effect=AssertionError('replayed event')), \
             patch.object(self.preparation.store, 'publish', side_effect=AssertionError('published')):
            first = self.uploads.reconcile(user=self.student, ticket_id=self.ticket.pk,
                attachment_id=attachment.attachment_id)
            self.assertFalse(connection.in_atomic_block)
            self.assertIs(type(first), tuple)
            self.assertEqual(len(first), 2)
            self.assertEqual(self.uploads.reconcile(user=self.student, ticket_id=self.ticket.pk,
                attachment_id=attachment.attachment_id), first)
        self.assertEqual(FeedbackAttachment.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_outer_uncommitted_upload_cannot_be_confirmed_and_absence_is_not_zero(self):
        with transaction.atomic():
            self.assertEqual(self.post().status_code, 201)
            attachment_id = FeedbackAttachment.objects.get().attachment_id
            with patch.object(self.uploads, 'authenticated_reference',
                              side_effect=AssertionError('read uncommitted evidence')):
                result = self.uploads.reconcile(user=self.student, ticket_id=self.ticket.pk,
                    attachment_id=attachment_id)
            self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
            transaction.set_rollback(True)
        result = self.uploads.reconcile(user=self.student, ticket_id=self.ticket.pk,
            attachment_id=attachment_id)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(FeedbackAttachment.objects.count(), 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_current_ticket_access_and_authenticated_evidence_are_required(self):
        self.assertEqual(self.post().status_code, 201)
        attachment = FeedbackAttachment.objects.get()
        CTFUser.objects.filter(pk=self.student.pk).update(is_active=False)
        result = self.uploads.reconcile(user=self.student, ticket_id=self.ticket.pk,
            attachment_id=attachment.attachment_id)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        CTFUser.objects.filter(pk=self.student.pk).update(is_active=True)
        FeedbackTicket.objects.filter(pk=self.ticket.pk).update(student=self.other, submitter=self.other)
        result = self.uploads.reconcile(user=self.student, ticket_id=self.ticket.pk,
            attachment_id=attachment.attachment_id)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        AuthenticatedAuditEntry.objects.all().delete()
        result = self.uploads.reconcile(user=self.teacher, ticket_id=self.ticket.pk,
            attachment_id=attachment.attachment_id)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_read_transaction_exit_failure_and_manual_transaction_remain_unknown(self):
        self.assertEqual(self.post().status_code, 201)
        attachment = FeedbackAttachment.objects.get()

        @contextmanager
        def fail_read_exit():
            with transaction.atomic():
                yield
            raise DatabaseError('synthetic read exit failure')

        with patch('feedback_center.private_uploads.transaction', SimpleNamespace(atomic=fail_read_exit)):
            result = self.uploads.reconcile(user=self.student, ticket_id=self.ticket.pk,
                attachment_id=attachment.attachment_id)
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        connection.set_autocommit(False)
        try:
            result = self.uploads.reconcile(user=self.student, ticket_id=self.ticket.pk,
                attachment_id=attachment.attachment_id)
            self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        finally:
            connection.rollback()
            connection.set_autocommit(True)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
