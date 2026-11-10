"""Real-PG feedback governance; synthetic recovery receipts do not prove backup/RPO/RTO."""
import hashlib
from unittest.mock import patch
from uuid import uuid4

from django.test import TransactionTestCase

from audit.models import SecurityAuditRecord
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject
from data_security.adapters.persistence.private_maintenance import DjangoPrivateMaintenance
from data_security.contracts import ProtectionError, ReasonCode
from resources.test_phase6_b3_private_maintenance import LegacyMaintenanceFixture
from users.models import CTFUser
from feedback_center import constants
from feedback_center.models import FeedbackAttachment, FeedbackTicket


class PrivateLegacyFeedbackTests(LegacyMaintenanceFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.uploads = self.components['private_uploads']['feedback']
        self.preparation = self.uploads.prepare.__self__
        self.maintenance = DjangoPrivateMaintenance(operations=self.uploads.operations,
            legacy_root=self.media, limits=self.preparation.limits, verify_recovery=self.trusted_recovery)
        self.uploads.maintenance = self.maintenance
        self.ticket = FeedbackTicket.objects.create(client_request_id='b3-feedback-legacy',
            request_fingerprint='a' * 64, submitter=self.other, submitter_role='student', student=self.other,
            category='content', issue_type='synthetic', dispute='合成旧附件', dedup_key='b' * 64)

    def legacy(self):
        name = 'feedback/' + str(uuid4()) + '.txt'
        path = self.media / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(self.content)
        attachment = FeedbackAttachment.objects.create(ticket=self.ticket, file=name, original_name='synthetic.txt',
            content_type='text/plain', size=len(self.content), sha256=hashlib.sha256(self.content).hexdigest(),
            uploaded_by=self.other, visibility=constants.VISIBILITY_STUDENT)
        return attachment, path

    def maintain(self, attachment, action, *, user=None, operation_id=None, replaces=None):
        return self.uploads.maintain_legacy(user=user or self.other, ticket_id=self.ticket.feedback_id,
            attachment_id=attachment.attachment_id, operation_id=operation_id or self.operation_id,
            action=action, replaces=replaces)

    def test_stage_preserves_legacy_attachment_and_has_no_read_or_delete_grant(self):
        attachment, path = self.legacy()
        operation = self.maintain(attachment, 'stage')
        self.assertNotIsInstance(operation, ProtectionError)
        self.assertEqual(operation.state, 'prepared')
        attachment.refresh_from_db()
        self.assertEqual(attachment.private_file, {})
        self.assertEqual(attachment.file.name, path.relative_to(self.media).as_posix())
        self.assertEqual(path.read_bytes(), self.content)
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        self.assertEqual(set(row.files), {'feedback/attachment'})
        self.assertEqual(row.legacy_sources['sources']['feedback/attachment']['sha256'], attachment.sha256)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertFalse(SecurityAuditRecord.objects.exists())
        self.assertIsInstance(self.maintain(attachment, 'delete'), ProtectionError)
        self.assertTrue(path.exists())

    def test_migrate_and_separate_exact_delete_preserve_binding_and_ciphertext(self):
        attachment, path = self.legacy()
        operation = self.maintain(attachment, 'stage')
        source_hash = self.cover_staging(operation)
        self.assertEqual(self.maintain(attachment, 'migrate').state, 'committed')
        attachment.refresh_from_db()
        self.assertEqual(attachment.file.name, '')
        self.assertEqual(attachment.uploaded_by_id, self.other.pk)
        self.assertEqual(attachment.private_file['schema_version'], 'feedback.private-upload.v2')
        download = self.uploads.open_download(user=self.other, ticket_id=self.ticket.feedback_id,
            attachment_id=attachment.attachment_id)
        self.assertEqual(download.binary, self.content)
        event = self.uploads.read_event('feedback-upload/' + str(attachment.attachment_id))
        self.assertEqual(dict(event.evidence_hashes)['archive'], source_hash)
        ciphertext = {item.name: item.read_bytes() for item in self.root.glob('*.sealed')}
        neighbor = path.with_suffix('.other')
        neighbor.write_bytes(b'unrelated synthetic attachment')
        self.assertTrue(path.exists())
        self.assertEqual(self.maintain(attachment, 'delete').state, 'committed')
        self.assertFalse(path.exists())
        self.assertTrue(neighbor.exists())
        self.assertEqual({item.name: item.read_bytes() for item in self.root.glob('*.sealed')}, ciphertext)
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        self.assertEqual(row.legacy_sources['phase'], 'deleted')
        self.assertEqual(self.maintenance.source_hash(row), source_hash)
        with patch.object(self.uploads.audit, 'record', side_effect=AssertionError('replayed deletion audit')):
            self.assertEqual(self.maintain(attachment, 'delete').state, 'committed')

    def test_quarantine_blocks_original_access_and_keeps_encrypted_copy_after_delete(self):
        attachment, path = self.legacy()
        operation = self.maintain(attachment, 'stage')
        self.cover_staging(operation)
        self.assertEqual(self.maintain(attachment, 'quarantine').state, 'retired')
        denied = self.uploads.authenticated_reference(user=self.other, ticket_id=self.ticket.feedback_id,
            attachment_id=attachment.attachment_id)
        self.assertIsInstance(denied, ProtectionError)
        self.assertTrue(path.exists())
        self.assertEqual(self.maintain(attachment, 'delete').state, 'retired')
        self.assertFalse(path.exists())
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)

    def test_missing_boolean_or_wrong_source_recovery_cannot_cut_over(self):
        attachment, path = self.legacy()
        operation = self.maintain(attachment, 'stage')
        self.assertEqual(self.maintain(attachment, 'migrate').code, ReasonCode.SOURCE_NOT_APPROVED)
        with patch.object(self.maintenance, 'verify_recovery', return_value=True):
            self.assertEqual(self.maintain(attachment, 'quarantine').code, ReasonCode.AUDIT_UNAVAILABLE)
        self.cover_staging(operation)
        source_hash, actor, receipt = self.covered[operation.operation_ref]
        self.covered[operation.operation_ref] = ('f' * 64, actor, receipt)
        self.assertNotEqual(source_hash, 'f' * 64)
        self.assertEqual(self.maintain(attachment, 'migrate').code, ReasonCode.SOURCE_NOT_APPROVED)
        attachment.refresh_from_db()
        self.assertEqual(attachment.private_file, {})
        self.assertTrue(path.exists())
        self.assertFalse(SecurityAuditRecord.objects.exists())

    def test_current_uploader_and_ticket_visibility_are_required_even_for_staff(self):
        attachment, path = self.legacy()
        self.assertEqual(self.maintain(attachment, 'stage', user=self.reviewer).code, ReasonCode.AUTHORIZATION_DENIED)
        FeedbackAttachment.objects.filter(pk=attachment.pk).update(visibility=constants.VISIBILITY_STAFF)
        self.assertEqual(self.maintain(attachment, 'stage').code, ReasonCode.AUTHORIZATION_DENIED)
        FeedbackAttachment.objects.filter(pk=attachment.pk).update(visibility=constants.VISIBILITY_STUDENT)
        CTFUser.objects.filter(pk=self.other.pk).update(is_active=False)
        self.assertEqual(self.maintain(attachment, 'stage').code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(PrivateFileOperation.objects.exists())
        self.assertTrue(path.exists())

    def test_changed_original_refuses_deletion_and_retains_authorized_tombstone(self):
        attachment, path = self.legacy()
        operation = self.maintain(attachment, 'stage')
        self.cover_staging(operation)
        self.assertEqual(self.maintain(attachment, 'migrate').state, 'committed')
        path.write_bytes(b'changed old attachment')
        self.assertEqual(self.maintain(attachment, 'delete').code, ReasonCode.HASH_MISMATCH)
        self.assertEqual(path.read_bytes(), b'changed old attachment')
        self.assertEqual(PrivateFileOperation.objects.get().legacy_sources['phase'], 'delete-authorized')

    def test_shared_legacy_name_blocks_deletion_without_rewriting_other_attachment(self):
        attachment, path = self.legacy()
        original_name = attachment.file.name
        operation = self.maintain(attachment, 'stage')
        self.cover_staging(operation)
        self.assertEqual(self.maintain(attachment, 'migrate').state, 'committed')
        other = FeedbackAttachment.objects.create(ticket=self.ticket, file=original_name,
            original_name='other.txt', uploaded_by=self.other)
        self.assertEqual(self.maintain(attachment, 'delete').code, ReasonCode.SOURCE_NOT_APPROVED)
        other.refresh_from_db()
        self.assertEqual(other.file.name, original_name)
        self.assertEqual(other.private_file, {})
        self.assertTrue(path.exists())
