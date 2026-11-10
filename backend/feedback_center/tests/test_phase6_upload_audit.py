"""Actual PostgreSQL commit/rollback for private uploads and the single v2 audit entry."""
from contextlib import contextmanager
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase

from audit.models import AuditEvent, AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble_feedback_uploads
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import (
    AuditReceipt, Durability, EventKind, Outcome, ProtectionError, ReasonCode,
    SecurityEventV2, content_hash,
)
from feedback_center.models import FeedbackAccessLog, FeedbackAttachment
from .test_phase6_private_uploads import PrivateFeedbackUploadFixture


class FeedbackUploadAuditTests(PrivateFeedbackUploadFixture, TransactionTestCase):
    def test_ciphertext_precedes_short_transaction_and_attachment_and_v2_event_commit_together(self):
        prepare = self.uploads.prepare
        record = self.uploads.audit.record
        receipts = []

        def prepared(payload, context):
            self.assertFalse(connection.in_atomic_block)
            return prepare(payload, context)

        def recorded(event, durability):
            self.assertTrue(connection.in_atomic_block)
            self.assertEqual(FeedbackAttachment.objects.count(), 1)
            self.assertEqual(PrivateObject.objects.get().state, 'verified')
            receipt = record(event, durability)
            receipts.append(receipt)
            return receipt

        with patch.object(self.uploads, 'prepare', side_effect=prepared), \
             patch.object(self.uploads.audit, 'record', side_effect=recorded):
            self.assertEqual(self.post().status_code, 201)
        self.assertFalse(connection.in_atomic_block)
        attachment = FeedbackAttachment.objects.get()
        event = SecurityEventV2.from_wire(SecurityAuditRecord.objects.get().event)
        self.assertEqual((event.kind, event.outcome), (EventKind.PROTECTION, Outcome.SUCCEEDED))
        self.assertEqual(event.event_id, 'feedback-upload/' + str(attachment.attachment_id))
        self.assertEqual(event.actor_ref, 'user/' + str(self.student.pk))
        self.assertEqual(event.object_ref, 'feedback/attachment/' + str(attachment.attachment_id))
        self.assertEqual(event.policy_binding, self.uploads.policy_binding)
        self.assertEqual(event.key_versions, (self.uploads.data_key_ref,))
        self.assertEqual(event.counts, (('bytes', len(self.content)), ('processed', 1)))
        self.assertEqual(event.evidence_hashes, (
            ('ciphertext', attachment.private_file['stored']['ciphertext_hash']),
            ('report', content_hash({
                'attachment_id': str(attachment.attachment_id), 'ticket_id': str(self.ticket.feedback_id),
                'uploaded_by': str(self.student.pk), 'original_name': attachment.original_name,
                'content_type': attachment.content_type, 'size': attachment.size, 'sha256': attachment.sha256,
                'visibility': attachment.visibility, 'private_file': attachment.private_file})),
        ))
        self.assertIsInstance(receipts[0], AuditReceipt)
        self.assertEqual(self.uploads.audit.sink.verify('ds.audit.v2'), receipts[0])
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 1)
        encoded = json.dumps(SecurityAuditRecord.objects.get().event,
                             sort_keys=True, ensure_ascii=False).encode('utf-8')
        self.assertNotIn(self.content, encoded)
        self.assertNotIn(attachment.original_name.encode(), encoded)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(self.download(attachment, self.student).status_code, 503)

    def test_audit_refusal_rolls_back_attachment_but_retains_unreadable_ciphertext(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
            retryable=False, trace_id='feedback-upload/synthetic-audit-failure')
        with patch.object(self.uploads.audit, 'record', return_value=failure):
            response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], ReasonCode.AUDIT_UNAVAILABLE.value)
        self.assertEqual(FeedbackAttachment.objects.count(), 0)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.assertFalse(FeedbackAccessLog.objects.filter(action='upload_attachment', allowed=True).exists())

    def test_database_failure_after_actual_ledger_append_rolls_back_all_database_upload_records(self):
        record = self.uploads.audit.record

        def fail_after_append(event, durability):
            self.assertIsInstance(record(event, durability), AuditReceipt)
            self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
            raise DatabaseError('synthetic failure after ledger append')

        with patch.object(self.uploads.audit, 'record', side_effect=fail_after_append):
            response = self.post()
        self.assertEqual(response.data['code'], ReasonCode.DELIVERY_UNKNOWN.value)
        self.assertFalse(connection.in_atomic_block)
        for model in (FeedbackAttachment, SecurityAuditRecord, AuthenticatedAuditEntry, AuditEvent):
            self.assertEqual(model.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_legacy_or_outbox_only_receipt_cannot_commit_a_private_attachment(self):
        record = self.uploads.audit.record
        for mode in ('legacy', 'outbox'):
            with self.subTest(mode=mode):
                def weaker_receipt(event, durability):
                    receipt = record(event, durability)
                    self.assertIsInstance(receipt, AuditReceipt)
                    if mode == 'legacy':
                        return replace(receipt, chain_version='v1')
                    return replace(receipt, durability=Durability.DURABLE, chain_version=None,
                                   entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)

                with patch.object(self.uploads.audit, 'record', side_effect=weaker_receipt):
                    response = self.post()
                self.assertEqual(response.data['code'], ReasonCode.AUDIT_UNAVAILABLE.value)
                for model in (FeedbackAttachment, SecurityAuditRecord, AuthenticatedAuditEntry, AuditEvent):
                    self.assertEqual(model.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_actual_bootstrap_without_v2_audit_refuses_instead_of_falling_back(self):
        self.config.pop('audit_chain')
        self.config.pop('policy_repository')
        self.config['schema_version'] = 'ds.bootstrap.v1'
        self.config_path.write_text(json.dumps(self.config))
        self.uploads = assemble_feedback_uploads(config_path=self.config_path,
            private_root=self.root, project_ref='feedback-upload/synthetic')
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], ReasonCode.AUDIT_UNAVAILABLE.value)
        self.assertEqual(FeedbackAttachment.objects.count(), 0)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_commit_confirmation_loss_preserves_attachment_and_ledger_without_publishing(self):
        @contextmanager
        def lose_confirmation():
            with transaction.atomic():
                yield
            self.assertFalse(connection.in_atomic_block)
            raise DatabaseError('synthetic confirmation lost after commit')

        with patch('feedback_center.private_uploads.transaction', SimpleNamespace(atomic=lose_confirmation)):
            response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], ReasonCode.DELIVERY_UNKNOWN.value)
        self.assertEqual(FeedbackAttachment.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertIsInstance(self.uploads.audit.sink.verify('ds.audit.v2'), AuditReceipt)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.assertFalse(FeedbackAccessLog.objects.filter(action='upload_attachment', allowed=True).exists())
        self.assertEqual(self.download(FeedbackAttachment.objects.get(), self.student).status_code, 503)
