"""Feedback-owned reference reads: actual private uploads and authenticated PostgreSQL events."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from django.db import DatabaseError, transaction
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.contracts import EventKind, ProtectionError, ReasonCode, SecurityEventV2
from data_security.adapters.persistence.models import PrivateObject
from feedback_center import constants
from feedback_center.models import FeedbackAttachment, FeedbackTicket
from users.models import CTFUser
from .test_phase6_private_uploads import PrivateFeedbackUploadFixture


class PrivateFeedbackReferenceTests(PrivateFeedbackUploadFixture, TransactionTestCase):
    def test_current_authorized_users_get_bound_metadata_without_opening_or_publishing(self):
        self.assertEqual(self.post().status_code, 201)
        attachment = FeedbackAttachment.objects.get()
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        admin = CTFUser.objects.create_user(username='reference-admin', role='admin')
        superuser = CTFUser.objects.create_user(username='reference-super', role='student', is_superuser=True)
        with patch.object(self.preparation.crypto, 'authenticate', side_effect=AssertionError('read signed')), \
             patch.object(self.preparation.crypto, 'open', side_effect=AssertionError('metadata opened file')), \
             patch.object(self.preparation.store, 'read', side_effect=AssertionError('metadata read file')), \
             patch.object(self.preparation.store, 'publish', side_effect=AssertionError('metadata published')), \
             patch('django.db.models.fields.files.FieldFile.open', side_effect=AssertionError('legacy file read')):
            for user in (self.student, self.submitter, self.teacher, admin, superuser):
                with self.subTest(user=user.username):
                    context, stored = self.uploads.authenticated_reference(user=user,
                        ticket_id=self.ticket.pk, attachment_id=attachment.attachment_id)
                    self.assertEqual(context.object_uuid, str(attachment.attachment_id))
                    self.assertEqual(context.field_ref, 'feedback/attachment')
                    self.assertEqual(context.project_ref, self.uploads.project_ref)
                    self.assertEqual(context.authorization_ref,
                        f'feedback-read/{self.ticket.feedback_id}/user-{user.pk}')
                    self.assertEqual(stored.to_wire(), attachment.private_file['stored'])
                    self.assertEqual(stored.state, 'verified')
                    self.assertEqual(self.download(attachment, user).status_code, 503)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_current_user_and_ticket_permissions_are_checked_before_audit_read(self):
        self.assertEqual(self.post().status_code, 201)
        attachment = FeedbackAttachment.objects.get()
        with patch.object(self.uploads, 'read_event', side_effect=AssertionError('unauthorized audit read')):
            for user, change in ((self.student, {'is_active': False}),
                                 (self.teacher, {'role': 'student'})):
                with self.subTest(change=change), transaction.atomic():
                    CTFUser.objects.filter(pk=user.pk).update(**change)
                    result = self.uploads.authenticated_reference(user=user, ticket_id=self.ticket.pk,
                        attachment_id=attachment.attachment_id)
                    self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
                    transaction.set_rollback(True)
            result = self.uploads.authenticated_reference(user=self.other, ticket_id=self.ticket.pk,
                attachment_id=attachment.attachment_id)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
            FeedbackTicket.objects.filter(pk=self.ticket.pk).update(student=self.other, submitter=self.other)
            result = self.uploads.authenticated_reference(user=self.student, ticket_id=self.ticket.pk,
                attachment_id=attachment.attachment_id)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        context, _ = self.uploads.authenticated_reference(user=self.other, ticket_id=self.ticket.pk,
            attachment_id=attachment.attachment_id)
        self.assertTrue(context.authorization_ref.endswith(f'/user-{self.other.pk}'))

    def test_staff_visibility_is_not_a_student_reference_permission(self):
        self.assertEqual(self.post(user=self.teacher,
            data=self.data(visibility=constants.VISIBILITY_STAFF)).status_code, 201)
        attachment = FeedbackAttachment.objects.get()
        with patch.object(self.uploads, 'read_event', side_effect=AssertionError('staff metadata leaked')):
            for user in (self.student, self.submitter):
                result = self.uploads.authenticated_reference(user=user, ticket_id=self.ticket.pk,
                    attachment_id=attachment.attachment_id)
                self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        context, _ = self.uploads.authenticated_reference(user=self.teacher, ticket_id=self.ticket.pk,
            attachment_id=attachment.attachment_id)
        self.assertTrue(context.authorization_ref.endswith(f'/user-{self.teacher.pk}'))

    def test_every_persisted_upload_field_and_reference_remain_bound_to_original_event(self):
        self.assertEqual(self.post().status_code, 201)
        first = FeedbackAttachment.objects.get()
        self.assertEqual(self.post().status_code, 201)
        second = FeedbackAttachment.objects.exclude(pk=first.pk).get()
        altered_context = deepcopy(first.private_file)
        altered_context['context']['object_version'] = '2'
        changes = ({'original_name': 'changed.txt'}, {'content_type': 'image/png'}, {'size': first.size + 1},
                   {'sha256': 'f' * 64}, {'visibility': constants.VISIBILITY_STAFF},
                   {'uploaded_by': self.teacher}, {'private_file': second.private_file},
                   {'private_file': altered_context}, {'private_file': {}},
                   {'file': 'synthetic/legacy.txt'})
        for change in changes:
            with self.subTest(field=next(iter(change))), transaction.atomic():
                FeedbackAttachment.objects.filter(pk=first.pk).update(**change)
                result = self.uploads.authenticated_reference(user=self.teacher, ticket_id=self.ticket.pk,
                    attachment_id=first.attachment_id)
                self.assertIs(type(result), ProtectionError)
                self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
                transaction.set_rollback(True)
        self.assertIs(type(self.uploads.authenticated_reference(user=self.student,
            ticket_id=self.ticket.pk, attachment_id=first.attachment_id)), tuple)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_moved_attachment_or_other_project_cannot_reuse_authenticated_upload(self):
        self.assertEqual(self.post().status_code, 201)
        attachment = FeedbackAttachment.objects.get()
        other_ticket = FeedbackTicket.objects.create(client_request_id='reference-other',
            request_fingerprint='c' * 64, submitter=self.submitter, submitter_role='student',
            student=self.student, category='content', issue_type='synthetic', dispute='合成引用检查',
            dedup_key='d' * 64)
        with transaction.atomic():
            FeedbackAttachment.objects.filter(pk=attachment.pk).update(ticket=other_ticket)
            result = self.uploads.authenticated_reference(user=self.teacher, ticket_id=other_ticket.pk,
                attachment_id=attachment.attachment_id)
            self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
            transaction.set_rollback(True)
        with patch.object(self.uploads, 'project_ref', 'feedback/other-project'):
            result = self.uploads.authenticated_reference(user=self.teacher, ticket_id=self.ticket.pk,
                attachment_id=attachment.attachment_id)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        result = self.uploads.authenticated_reference(user=self.teacher, ticket_id=other_ticket.pk,
            attachment_id=attachment.attachment_id)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)

    def test_audit_refusal_and_wrong_authenticated_event_never_fall_back_to_raw_metadata(self):
        self.assertEqual(self.post().status_code, 201)
        attachment = FeedbackAttachment.objects.get()
        original = SecurityEventV2.from_wire(SecurityAuditRecord.objects.get().event)
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
            retryable=False, trace_id='reference/synthetic-key')
        with patch.object(self.uploads, 'read_event', return_value=failure):
            self.assertIs(self.uploads.authenticated_reference(user=self.teacher, ticket_id=self.ticket.pk,
                attachment_id=attachment.attachment_id), failure)
        for changed in (replace(original, event_id='wrong/event'), replace(original, kind=EventKind.POLICY),
                        replace(original, object_ref='feedback/attachment/other'),
                        replace(original, evidence_hashes=(('ciphertext', 'f' * 64),
                                                          ('report', dict(original.evidence_hashes)['report'])))):
            with self.subTest(event=changed.event_id), patch.object(self.uploads, 'read_event', return_value=changed):
                result = self.uploads.authenticated_reference(user=self.teacher, ticket_id=self.ticket.pk,
                    attachment_id=attachment.attachment_id)
                self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        with patch.object(self.uploads, 'read_event', side_effect=DatabaseError('synthetic unavailable')):
            result = self.uploads.authenticated_reference(user=self.teacher, ticket_id=self.ticket.pk,
                attachment_id=attachment.attachment_id)
            self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        AuthenticatedAuditEntry.objects.all().delete()
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        result = self.uploads.authenticated_reference(user=self.teacher, ticket_id=self.ticket.pk,
            attachment_id=attachment.attachment_id)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
