"""Synthetic feedback ownership and ciphertext integration on isolated PostgreSQL."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.db import DatabaseError, connection
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from ctf_backend.security_bootstrap import assemble_feedback_uploads
from data_security.adapters.django.uploads import PrivateUploadBoundary
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import (
    BASELINE_LIMITS, CipherEnvelope, ContractViolation, Environment, ObjectContext,
    ProtectionError, ReasonCode, StoredObject,
)
from data_security.tests.phase3_fixtures import configuration
from users.models import CTFUser
from feedback_center import constants
from feedback_center.models import FeedbackAccessLog, FeedbackAttachment, FeedbackTicket
from feedback_center.serializers import AttachmentUploadSerializer
from feedback_center.views import FeedbackAttachmentDownloadView, FeedbackAttachmentUploadView, _attachment_payload


class PrivateFeedbackUploadFixture:
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        files = configuration(providers=())
        self.config_path, self.config, _, _, _ = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        checkpoints = self.config_path.parent / 'checkpoints'
        checkpoints.mkdir(mode=0o700)
        self.config.update(schema_version='ds.bootstrap.v2',
            policy_repository={'kind': 'file', 'writable': False}, audit_chain={
                'chain_version': 'ds.audit.v2', 'project_ref': 'feedback-upload/synthetic',
                'object_uuid': '00000000-0000-0000-0000-000000000001', 'object_version': '1',
                'authorization_ref': 'authorization/synthetic-audit-owner', 'retained_keys': [],
                'checkpoint_root': str(checkpoints), 'checkpoint_ref': None})
        self.config_path.write_text(json.dumps(self.config))
        self.root = self.config_path.parent / 'private'
        self.root.mkdir(mode=0o700)
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.media = Path(media.name)
        settings = override_settings(MEDIA_ROOT=media.name, FILE_UPLOAD_MAX_MEMORY_SIZE=1)
        settings.enable()
        self.addCleanup(settings.disable)
        self.uploads = assemble_feedback_uploads(config_path=self.config_path,
            private_root=self.root, project_ref='feedback-upload/synthetic')
        self.preparation = self.uploads.prepare.__self__
        self.student = CTFUser.objects.create_user(username='private-feedback-student', role='student')
        self.submitter = CTFUser.objects.create_user(username='private-feedback-submitter', role='student')
        self.other = CTFUser.objects.create_user(username='private-feedback-other', role='student')
        self.teacher = CTFUser.objects.create_user(username='private-feedback-teacher', role='teacher')
        self.ticket = FeedbackTicket.objects.create(client_request_id='private-feedback',
            request_fingerprint='a' * 64, submitter=self.submitter, submitter_role='student',
            student=self.student, category='content', issue_type='synthetic', dispute='合成附件复核',
            dedup_key='b' * 64)
        self.factory = APIRequestFactory()
        self.content = b'synthetic private feedback evidence'

    def data(self, **changes):
        return {'file': SimpleUploadedFile('synthetic.txt', self.content, content_type='text/plain'), **changes}

    def post(self, *, user=None, data=None, enabled=True):
        service = self.uploads if enabled else None

        class ExplicitPrivateFeedbackUploadView(FeedbackAttachmentUploadView):
            private_uploads = service

        request = self.factory.post(f'/api/feedback/{self.ticket.feedback_id}/attachments/',
            data or self.data(), format='multipart')
        force_authenticate(request, user=user or self.student)
        boundary = PrivateUploadBoundary(lambda incoming: ExplicitPrivateFeedbackUploadView.as_view()(
            incoming, feedback_id=self.ticket.feedback_id), limits=BASELINE_LIMITS)
        with patch('django.core.files.uploadhandler.TemporaryUploadedFile',
                   side_effect=AssertionError('ordinary upload spool reached')), \
             patch('django.core.files.storage.FileSystemStorage._save',
                   side_effect=AssertionError('ordinary FileField save reached')):
            response = boundary(request)
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertTrue(all(buffer.closed for buffer in request.upload_handlers[0].buffers))
        return response

    def download(self, attachment, user):
        request = self.factory.get('/synthetic/download/')
        force_authenticate(request, user=user)
        return FeedbackAttachmentDownloadView.as_view()(request,
            feedback_id=self.ticket.feedback_id, attachment_id=attachment.attachment_id)


class PrivateFeedbackUploadTests(PrivateFeedbackUploadFixture, TestCase):
    def test_student_upload_stores_only_verified_ciphertext_and_internal_reference(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        attachment = FeedbackAttachment.objects.get()
        self.assertEqual(attachment.file.name, '')
        self.assertEqual(attachment.size, len(self.content))
        self.assertEqual(attachment.sha256, hashlib.sha256(self.content).hexdigest())
        self.assertEqual(attachment.uploaded_by_id, self.student.pk)
        self.assertEqual(attachment.private_file['schema_version'], 'feedback.private-upload.v1')
        item = attachment.private_file
        context = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})
        stored = StoredObject.from_wire(item['stored'])
        self.assertEqual(context.object_uuid, str(attachment.attachment_id))
        self.assertEqual(context.authorization_ref, f'feedback-upload/{self.ticket.feedback_id}/user-{self.student.pk}')
        self.assertEqual(context.field_ref, 'feedback/attachment')
        self.assertEqual(stored.state, 'verified')
        self.assertEqual(PrivateObject.objects.count(), 1)
        path = self.root / (stored.object_ref.removeprefix('private/') + '.sealed')
        encoded = path.read_bytes()
        self.assertNotIn(self.content, encoded)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        envelope = CipherEnvelope.from_json(encoded)
        opened = self.preparation.crypto.open(envelope, context, envelope.key)
        self.assertIsNot(type(opened), ProtectionError)
        self.assertTrue(opened.binary == self.content)
        self.assertEqual(self.preparation.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)
        for forbidden in ('file', 'private_file', 'context', 'stored', 'object_ref'):
            self.assertNotIn(forbidden, response.data)
        self.assertEqual(response.data['download_url'],
            f'/api/feedback/{self.ticket.feedback_id}/attachments/{attachment.attachment_id}/download/')

    def test_submitter_teacher_admin_and_superuser_keep_existing_upload_roles(self):
        admin = CTFUser.objects.create_user(username='private-feedback-admin', role='admin')
        superuser = CTFUser.objects.create_user(username='private-feedback-super', role='student', is_superuser=True)
        for user in (self.submitter, self.teacher, admin, superuser):
            with self.subTest(role=user.username):
                self.assertEqual(self.post(user=user).status_code, 201)
        self.assertEqual(FeedbackAttachment.objects.count(), 4)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 4)

    def test_other_student_and_student_staff_visibility_are_rejected_before_prepare(self):
        with patch.object(self.uploads, 'prepare', wraps=self.uploads.prepare) as prepare:
            self.assertEqual(self.post(user=self.other).status_code, 403)
            self.assertEqual(self.post(data=self.data(visibility=constants.VISIBILITY_STAFF)).status_code, 403)
            prepare.assert_not_called()
        self.assertEqual(FeedbackAttachment.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.count(), 0)

    def test_current_role_active_state_and_superuser_flag_override_cached_actor(self):
        for original, change in (
            ({'role': 'teacher', 'is_superuser': False}, {'role': 'student'}),
            ({'role': 'teacher', 'is_superuser': False}, {'is_active': False}),
            ({'role': 'student', 'is_superuser': True}, {'is_superuser': False}),
        ):
            with self.subTest(change=change):
                CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=True, **original)
                self.teacher.refresh_from_db()
                CTFUser.objects.filter(pk=self.teacher.pk).update(**change)
                self.assertEqual(self.post(user=self.teacher).status_code, 400)
        self.assertEqual(FeedbackAttachment.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.count(), 0)

    def test_current_ticket_ownership_is_not_taken_from_stale_view_object(self):
        FeedbackTicket.objects.filter(pk=self.ticket.pk).update(student=self.other, submitter=self.other)
        with patch('feedback_center.views._get_ticket', return_value=self.ticket), \
             patch.object(self.uploads, 'prepare', wraps=self.uploads.prepare) as prepare:
            self.assertEqual(self.post().status_code, 400)
            prepare.assert_not_called()
        self.assertEqual(FeedbackAttachment.objects.count(), 0)

    def test_staff_visibility_stays_hidden_and_all_private_downloads_stay_closed(self):
        self.assertEqual(self.post(user=self.teacher, data=self.data(visibility=constants.VISIBILITY_STAFF)).status_code, 201)
        attachment = FeedbackAttachment.objects.get()
        self.assertIsNone(_attachment_payload(attachment, 'student'))
        with patch('django.db.models.fields.files.FieldFile.open', side_effect=AssertionError('legacy read')):
            self.assertEqual(self.download(attachment, self.student).status_code, 403)
            self.assertEqual(self.download(attachment, self.other).status_code, 403)
            self.assertEqual(self.download(attachment, self.teacher).status_code, 503)
            attachment.visibility = constants.VISIBILITY_STUDENT
            attachment.save(update_fields=['visibility'])
            self.assertEqual(self.download(attachment, self.student).status_code, 503)
        self.assertFalse(FeedbackAccessLog.objects.filter(action=constants.ATTACHMENT_DOWNLOAD_ACTION, allowed=True).exists())
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_client_metadata_cannot_select_private_reference_ticket_or_actor(self):
        data = self.data(private_file='forged', private_uploads='forged', ticket=str(self.other.pk),
                         uploaded_by=str(self.teacher.pk), size=1, sha256='forged')
        self.assertEqual(self.post(data=data).status_code, 201)
        attachment = FeedbackAttachment.objects.get()
        self.assertEqual(attachment.ticket_id, self.ticket.pk)
        self.assertEqual(attachment.uploaded_by_id, self.student.pk)
        self.assertEqual(attachment.size, len(self.content))
        self.assertEqual(attachment.private_file['schema_version'], 'feedback.private-upload.v1')

    def test_prepare_error_does_not_create_attachment_or_success_access_log(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
            retryable=False, trace_id='feedback-upload/synthetic-failure')
        with patch.object(self.uploads, 'prepare', return_value=failure):
            self.assertEqual(self.post().status_code, 400)
        self.assertEqual(FeedbackAttachment.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.count(), 0)
        self.assertFalse(FeedbackAccessLog.objects.filter(action='upload_attachment', allowed=True).exists())

    def test_database_failure_retains_unreadable_ciphertext_without_attachment(self):
        with patch.object(FeedbackAttachment.objects, 'create', side_effect=DatabaseError('synthetic failure')):
            self.assertEqual(self.post().status_code, 400)
        self.assertEqual(FeedbackAttachment.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.assertNotIn(self.content, next(self.root.iterdir()).read_bytes())

    def test_explicit_missing_service_never_falls_back_to_filefield(self):
        self.assertEqual(self.post(enabled=False).status_code, 503)
        self.assertEqual(FeedbackAttachment.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.count(), 0)

    def test_original_extension_and_ten_mib_business_limit_remain_before_prepare(self):
        for name, content in (('synthetic.exe', b'synthetic'),
                              ('synthetic.txt', b'x' * (constants.ATTACHMENT_MAX_BYTES + 1))):
            with self.subTest(name=name), patch.object(self.uploads, 'prepare', wraps=self.uploads.prepare) as prepare:
                self.assertEqual(self.post(data={'file': SimpleUploadedFile(name, content)}).status_code, 400)
                prepare.assert_not_called()
        self.assertEqual(constants.ATTACHMENT_MAX_BYTES, 10 * 1024 * 1024)
        self.assertEqual(FeedbackAttachment.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.count(), 0)

    def test_disk_upload_is_rejected_even_after_business_validation(self):
        upload = TemporaryUploadedFile('synthetic.txt', 'text/plain', len(self.content), None)
        self.addCleanup(upload.close)
        upload.write(self.content)
        upload.seek(0)
        serializer = AttachmentUploadSerializer(data={'file': upload})
        self.assertTrue(serializer.is_valid())
        with patch.object(self.uploads, 'prepare', wraps=self.uploads.prepare) as prepare:
            result = self.uploads.create(serializer.validated_data, user=self.student, ticket_id=self.ticket.pk)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
            prepare.assert_not_called()
        self.assertEqual(FeedbackAttachment.objects.count(), 0)

    def test_bootstrap_rejects_nonprivate_root(self):
        self.root.chmod(0o755)
        with self.assertRaises(ContractViolation):
            assemble_feedback_uploads(config_path=self.config_path,
                private_root=self.root, project_ref='feedback-upload/synthetic')
        self.assertEqual(PrivateObject.objects.count(), 0)
