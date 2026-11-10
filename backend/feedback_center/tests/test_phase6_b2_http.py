"""Feedback private HTTP lifecycle, ticket ACLs and unknown recovery on isolated PostgreSQL."""
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import TransactionTestCase

from data_security.adapters.persistence.models import PrivateFileOperation, PrivateFileShare, PrivateObject
from data_security.contracts import ProtectionError, ReasonCode
from resources.test_phase6_b2_fixtures import PrivateFileHTTPFixture
from users.models import CTFUser

from feedback_center import constants
from feedback_center.models import FeedbackAttachment, FeedbackTicket


class PrivateFeedbackHTTPTests(PrivateFileHTTPFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.student = CTFUser.objects.create_user(username='b2-feedback-student', role='student')
        self.submitter = CTFUser.objects.create_user(username='b2-feedback-submitter', role='student')
        self.ticket = FeedbackTicket.objects.create(client_request_id='b2-feedback',
            request_fingerprint='a' * 64, submitter=self.submitter, submitter_role='student',
            student=self.student, category='content', issue_type='synthetic', dispute='合成附件复核', dedup_key='b' * 64)
        self.base = f'/api/feedback/{self.ticket.feedback_id}/'
        self.client.force_authenticate(self.student)
        self.feedback = self.components['private_uploads']['feedback']
        self.preparation = self.feedback.prepare.__self__
        self.content = b'b2 synthetic feedback private attachment'

    def attachment(self, *, visibility=constants.VISIBILITY_STUDENT, operation_id=None):
        with patch('django.core.files.uploadhandler.TemporaryUploadedFile', side_effect=AssertionError('disk spool')), \
             patch('django.core.files.storage.FileSystemStorage._save', side_effect=AssertionError('FileField save')):
            return self.client.post(self.base + 'attachments/', {'visibility': visibility,
                'file': SimpleUploadedFile('synthetic.txt', self.content, content_type='text/plain')},
                format='multipart', HTTP_X_FILE_OPERATION_ID=str(operation_id or self.operation_id))

    def feedback_operation(self, *, cleanup=False):
        return (self.client.delete if cleanup else self.client.post)(self.base + f'file-operations/{self.operation_id}/')

    def attachment_share(self, attachment):
        return self.client.post(self.base + f'attachments/{attachment.attachment_id}/shares/',
            HTTP_X_FILE_OPERATION_ID=str(uuid4()))

    def test_upload_retry_download_reference_share_and_cleanup(self):
        uploaded = self.attachment()
        self.assertEqual(uploaded.status_code, 201, uploaded.data)
        attachment = FeedbackAttachment.objects.get()
        self.assertEqual(attachment.file.name, '')
        self.assertEqual(attachment.private_file['schema_version'], 'feedback.private-upload.v2')
        row = PrivateFileOperation.objects.get()
        self.assertEqual(row.result_ref, str(attachment.attachment_id))
        self.assertNotEqual(row.result_ref, str(self.operation_id))
        for key in ('private_file', 'context', 'stored', 'object_ref'):
            self.assertNotIn(key, uploaded.data)
        with patch.object(self.preparation.crypto, 'seal', side_effect=AssertionError('retry reencrypted')):
            retry = self.attachment()
        self.assertEqual(uploaded.data, retry.data)
        downloaded = self.client.get(uploaded.data['download_url'])
        self.assertEqual(downloaded.content, self.content)
        self.assertFalse(downloaded.streaming)
        shared = self.attachment_share(attachment)
        self.assertEqual(shared.status_code, 201, shared.data)
        self.client.force_authenticate(self.submitter)
        self.assertEqual(self.client.get(shared.data['download_url']).content, self.content)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(shared.data['download_url']).status_code, 403)
        self.client.force_authenticate(self.student)
        self.assertFalse(self.feedback_operation().data['network_delivery_confirmed'])
        self.assertEqual(self.feedback_operation(cleanup=True).data['state'], 'cleaned')
        self.assertEqual(self.client.get(shared.data['download_url']).status_code, 403)
        self.assertEqual(list(self.root.glob('*.sealed')), [])
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertEqual(FeedbackAttachment.objects.count(), 1)
        self.assertEqual(PrivateObject.objects.get().state, 'retired')

    def test_staff_only_visibility_is_enforced_for_original_and_share(self):
        self.assertEqual(self.attachment(visibility=constants.VISIBILITY_STAFF).status_code, 403)
        self.assertFalse(PrivateFileOperation.objects.exists())
        self.client.force_authenticate(self.teacher)
        uploaded = self.attachment(visibility=constants.VISIBILITY_STAFF)
        self.assertEqual(uploaded.status_code, 201, uploaded.data)
        shared = self.attachment_share(FeedbackAttachment.objects.get())
        self.assertEqual(shared.status_code, 201, shared.data)
        for user in (self.student, self.submitter, self.other):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(uploaded.data['download_url']).status_code, 403)
            self.assertEqual(self.client.get(shared.data['download_url']).status_code, 403)
        self.client.force_authenticate(self.reviewer)
        self.assertEqual(self.client.get(shared.data['download_url']).content, self.content)

    def test_ticket_membership_is_reloaded_after_audit_wait(self):
        uploaded = self.attachment()
        self.assertEqual(uploaded.status_code, 201)
        record = self.feedback.audit.record

        def changed(event, durability):
            receipt = record(event, durability)
            if event.algorithm_versions == ('private-download.authorized.v1',):
                FeedbackTicket.objects.filter(pk=self.ticket.pk).update(student=self.other, submitter=self.other)
            return receipt

        with patch.object(self.feedback.audit, 'record', side_effect=changed):
            response = self.client.get(uploaded.data['download_url'])
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(self.content, response.content)

    def test_other_ticket_cannot_rebind_operation_or_attachment(self):
        uploaded = self.attachment()
        self.assertEqual(uploaded.status_code, 201)
        other = FeedbackTicket.objects.create(client_request_id='b2-another-ticket', request_fingerprint='c' * 64,
            submitter=self.student, submitter_role='student', student=self.student, category='content',
            issue_type='synthetic', dispute='另一份合成复核', dedup_key='d' * 64)
        attachment = FeedbackAttachment.objects.get()
        wrong_base = f'/api/feedback/{other.feedback_id}/'
        self.assertEqual(self.client.get(wrong_base + f'attachments/{attachment.attachment_id}/download/').status_code, 403)
        self.assertEqual(self.client.delete(wrong_base + f'file-operations/{self.operation_id}/').status_code, 403)
        self.assertEqual(PrivateFileOperation.objects.get().state, 'committed')
        self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)

    def test_fsync_before_registration_is_recovered_without_guessing_business_id(self):
        with patch.object(PrivateObject.objects, 'get_or_create', side_effect=DatabaseError('synthetic row loss')):
            result = self.attachment()
        self.assertEqual(result.data['code'], 'DELIVERY_UNKNOWN')
        self.assertFalse(FeedbackAttachment.objects.exists())
        self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)
        self.assertEqual(self.feedback_operation().data['state'], 'prepared')
        with patch.object(self.preparation.crypto, 'seal', side_effect=AssertionError('recovery reencrypted')):
            self.assertEqual(self.attachment().status_code, 201)
        self.assertEqual((FeedbackAttachment.objects.count(), PrivateObject.objects.count()), (1, 1))

    def test_audit_refusal_keeps_preparation_until_authorized_cleanup(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
            retryable=False, trace_id='b2/feedback-audit-refusal')
        with patch.object(self.feedback.audit, 'record', return_value=failure):
            self.assertEqual(self.attachment().data['code'], 'AUDIT_UNAVAILABLE')
            self.assertEqual(self.feedback_operation(cleanup=True).data['code'], 'AUDIT_UNAVAILABLE')
        self.assertFalse(FeedbackAttachment.objects.exists())
        self.assertEqual(PrivateFileOperation.objects.get().state, 'prepared')
        self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)
        self.assertEqual(self.feedback_operation(cleanup=True).data['state'], 'cleaned')
        self.assertEqual(list(self.root.glob('*.sealed')), [])

    def test_share_revocation_is_issuer_only_and_does_not_remove_evidence(self):
        self.assertEqual(self.attachment().status_code, 201)
        shared = self.attachment_share(FeedbackAttachment.objects.get())
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.delete(shared.data['download_url']).status_code, 403)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.delete(shared.data['download_url']).status_code, 204)
        self.assertEqual(self.client.get(shared.data['download_url']).status_code, 403)
        self.assertIsNotNone(PrivateFileShare.objects.get().revoked_at)
        self.assertEqual(PrivateFileOperation.objects.get().state, 'committed')

    def test_ten_mib_feedback_limit_rejects_before_preparation(self):
        self.content = b'x' * (10 * 1024 * 1024 + 1)
        with patch.object(self.feedback, 'prepare', side_effect=AssertionError('oversize attachment prepared')):
            result = self.attachment()
        self.assertEqual(result.status_code, 400)
        self.assertFalse(PrivateFileOperation.objects.exists())
        self.assertEqual(list(self.root.iterdir()), [])
