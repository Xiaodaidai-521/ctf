"""Private originals and covers commit with their v2 events on isolated PostgreSQL."""
from contextlib import contextmanager
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase
from rest_framework.test import force_authenticate

from audit.models import AuditEvent, AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble_resource_uploads
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import (
    AuditReceipt, Durability, EventKind, Outcome, ProtectionError, ReasonCode,
    SecurityEventV2, content_hash,
)
from .models import Resource
from .test_phase6_private_uploads import PrivateResourceUploadFixture
from .views import resource_download_view


class ResourceUploadAuditTests(PrivateResourceUploadFixture, TransactionTestCase):
    def test_both_files_precede_transaction_and_resource_and_two_v2_events_commit_together(self):
        prepare = self.uploads.prepare
        record = self.uploads.audit.record
        receipts = []

        def prepared(payload, context):
            self.assertFalse(connection.in_atomic_block)
            return prepare(payload, context)

        def recorded(event, durability):
            self.assertTrue(connection.in_atomic_block)
            self.assertEqual(Resource.objects.count(), 1)
            self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
            receipt = record(event, durability)
            receipts.append(receipt)
            return receipt

        with patch.object(self.uploads, 'prepare', side_effect=prepared), \
             patch.object(self.uploads.audit, 'record', side_effect=recorded):
            self.assertEqual(self.post(data=self.data(cover=True)).status_code, 201)
        self.assertFalse(connection.in_atomic_block)
        resource = Resource.objects.get()
        expected_hash = content_hash({
            'resource_id': str(resource.pk), 'uploader': str(self.teacher.pk),
            'title': resource.title, 'description': resource.description,
            'resource_type': resource.resource_type, 'category': resource.category,
            'tags': resource.tags, 'is_tutoring_reserved': resource.is_tutoring_reserved,
            'status': resource.status, 'file_size': resource.file_size,
            'private_files': resource.private_files})
        events = [SecurityEventV2.from_wire(item.event) for item in SecurityAuditRecord.objects.all()]
        self.assertEqual(len(events), 2)
        self.assertEqual({event.object_ref for event in events},
                         {f'resources/{resource.pk}/file', f'resources/{resource.pk}/cover_image'})
        sizes = {'file': len(self.content), 'cover_image': len(self.cover_bytes)}
        for event in events:
            field = event.object_ref.rsplit('/', 1)[1]
            stored, context = self.stored_context(resource, field)
            self.assertEqual(event.event_id, f'resource-upload/{context.object_uuid}/{field}')
            self.assertEqual((event.kind, event.outcome), (EventKind.PROTECTION, Outcome.SUCCEEDED))
            self.assertEqual(event.actor_ref, 'user/' + str(self.teacher.pk))
            self.assertEqual(event.policy_binding, self.uploads.policy_binding)
            self.assertEqual(event.key_versions, (self.uploads.data_key_ref,))
            self.assertEqual(event.counts, (('bytes', sizes[field]), ('processed', 1)))
            self.assertEqual(event.evidence_hashes,
                             (('ciphertext', stored.ciphertext_hash), ('report', expected_hash)))
            self.assertEqual(self.preparation.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(isinstance(receipt, AuditReceipt) for receipt in receipts))
        self.assertEqual(self.uploads.audit.sink.verify('ds.audit.v2'), receipts[-1])
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 2)
        encoded = json.dumps(list(SecurityAuditRecord.objects.values_list('event', flat=True)),
                             ensure_ascii=False).encode('utf-8')
        for value in (self.content, self.cover_bytes, resource.title.encode(), resource.description.encode(),
                      b'synthetic.txt', b'synthetic.png'):
            self.assertNotIn(value, encoded)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)

    def test_second_file_audit_refusal_rolls_back_resource_and_first_event(self):
        record = self.uploads.audit.record
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
            retryable=False, trace_id='resource-upload/synthetic-audit-failure')

        def refuse_cover(event, durability):
            if event.object_ref.endswith('/cover_image'):
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
                return failure
            return record(event, durability)

        with patch.object(self.uploads.audit, 'record', side_effect=refuse_cover):
            response = self.post(data=self.data(cover=True))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data[0].code, ReasonCode.AUDIT_UNAVAILABLE.value)
        for model in (Resource, SecurityAuditRecord, AuthenticatedAuditEntry, AuditEvent):
            self.assertEqual(model.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_database_failure_after_second_actual_append_rolls_back_both_events(self):
        record = self.uploads.audit.record

        def fail_after_cover(event, durability):
            receipt = record(event, durability)
            self.assertIsInstance(receipt, AuditReceipt)
            if event.object_ref.endswith('/cover_image'):
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
                raise DatabaseError('synthetic failure after second ledger append')
            return receipt

        with patch.object(self.uploads.audit, 'record', side_effect=fail_after_cover):
            response = self.post(data=self.data(cover=True))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data[0].code, ReasonCode.DELIVERY_UNKNOWN.value)
        self.assertFalse(connection.in_atomic_block)
        for model in (Resource, SecurityAuditRecord, AuthenticatedAuditEntry, AuditEvent):
            self.assertEqual(model.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_legacy_or_outbox_receipt_cannot_commit_resource(self):
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
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data[0].code, ReasonCode.AUDIT_UNAVAILABLE.value)
                for model in (Resource, SecurityAuditRecord, AuthenticatedAuditEntry, AuditEvent):
                    self.assertEqual(model.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_actual_bootstrap_without_v2_audit_refuses_instead_of_falling_back(self):
        self.config.pop('audit_chain')
        self.config.pop('policy_repository')
        self.config['schema_version'] = 'ds.bootstrap.v1'
        self.config_path.write_text(json.dumps(self.config))
        self.uploads = assemble_resource_uploads(config_path=self.config_path,
            private_root=self.root, project_ref='resource-upload/synthetic')
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data[0].code, ReasonCode.AUDIT_UNAVAILABLE.value)
        for model in (Resource, SecurityAuditRecord, AuthenticatedAuditEntry, AuditLedgerEntry, AuditEvent):
            self.assertEqual(model.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_commit_confirmation_loss_preserves_resource_and_both_events_without_publishing(self):
        @contextmanager
        def lose_confirmation():
            with transaction.atomic():
                yield
            self.assertFalse(connection.in_atomic_block)
            raise DatabaseError('synthetic confirmation lost after commit')

        with patch('resources.private_uploads.transaction', SimpleNamespace(atomic=lose_confirmation)):
            response = self.post(data=self.data(cover=True))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data[0].code, ReasonCode.DELIVERY_UNKNOWN.value)
        self.assertEqual(Resource.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertIsInstance(self.uploads.audit.sink.verify('ds.audit.v2'), AuditReceipt)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(len(list(self.root.iterdir())), 2)
        resource = Resource.objects.get()
        resource.status = 'approved'
        resource.save(update_fields=['status'])
        request = self.factory.get(f'/api/resources/{resource.pk}/download/')
        force_authenticate(request, user=self.teacher)
        self.assertEqual(resource_download_view(request, resource.pk).status_code, 404)
        resource.refresh_from_db()
        self.assertEqual(resource.download_count, 0)
