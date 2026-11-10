"""Resource-owned references from real private uploads and authenticated PostgreSQL events."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError, transaction
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import EventKind, ProtectionError, ReasonCode, SecurityEventV2
from users.models import CTFUser

from .models import Resource
from .test_phase6_private_uploads import PrivateResourceUploadFixture


class PrivateResourceReferenceTests(PrivateResourceUploadFixture, TransactionTestCase):
    def test_original_and_cover_references_are_authenticated_without_file_or_publish_work(self):
        self.assertEqual(self.post(data=self.data(cover=True)).status_code, 201)
        resource = Resource.objects.get()
        reviewer = CTFUser.objects.create_user(username='reference-reviewer', role='student', is_staff=True)
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        with patch.object(self.preparation.crypto, 'authenticate', side_effect=AssertionError('read signed')), \
             patch.object(self.preparation.crypto, 'open', side_effect=AssertionError('reference opened')), \
             patch.object(self.preparation.store, 'read', side_effect=AssertionError('reference read file')), \
             patch.object(self.preparation.store, 'publish', side_effect=AssertionError('reference published')), \
             patch('django.db.models.fields.files.FieldFile.open', side_effect=AssertionError('legacy read')):
            for user in (self.teacher, reviewer):
                references = self.uploads.authenticated_references(user=user, resource_id=resource.pk)
                self.assertEqual(tuple(item[0] for item in references), ('file', 'cover_image'))
                for field, context, stored in references:
                    expected, original = self.stored_context(resource, field)
                    self.assertEqual(stored, expected)
                    self.assertEqual(context, replace(original,
                        authorization_ref=f'resource-read/{resource.pk}/user-{user.pk}'))
                    self.assertEqual(stored.state, 'verified')
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(SecurityAuditRecord.objects.count(), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_current_uploader_or_staff_access_precedes_audit_read(self):
        self.assertEqual(self.post().status_code, 201)
        resource = Resource.objects.get()
        other = CTFUser.objects.create_user(username='reference-other', role='teacher')
        admin = CTFUser.objects.create_user(username='reference-admin', role='admin')
        reviewer = CTFUser.objects.create_user(username='reference-staff', is_staff=True)
        with patch.object(self.uploads, 'read_event', side_effect=AssertionError('unauthorized audit read')):
            for user in (AnonymousUser(), other, admin):
                result = self.uploads.authenticated_references(user=user, resource_id=resource.pk)
                self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
            for user, change in ((self.teacher, {'is_active': False}), (reviewer, {'is_staff': False})):
                with self.subTest(change=change), transaction.atomic():
                    CTFUser.objects.filter(pk=user.pk).update(**change)
                    result = self.uploads.authenticated_references(user=user, resource_id=resource.pk)
                    self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
                    transaction.set_rollback(True)
            result = self.uploads.authenticated_references(user=self.teacher, resource_id=resource.pk + 1)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        # Existing uploader access does not depend on retaining permission to upload new files.
        CTFUser.objects.filter(pk=self.teacher.pk).update(role='student')
        self.assertIs(type(self.uploads.authenticated_references(user=self.teacher,
            resource_id=resource.pk)), tuple)

    def test_upload_metadata_and_both_file_references_cannot_be_rebound(self):
        self.assertEqual(self.post(data=self.data(cover=True)).status_code, 201)
        resource = Resource.objects.get()
        self.assertEqual(self.post(data=self.data(cover=True)).status_code, 201)
        other = Resource.objects.exclude(pk=resource.pk).get()
        reviewer = CTFUser.objects.create_user(username='metadata-reviewer', is_staff=True)
        swapped = deepcopy(resource.private_files)
        swapped['files']['cover_image'] = other.private_files['files']['cover_image']
        missing_cover = deepcopy(resource.private_files)
        del missing_cover['files']['cover_image']
        changes = ({'title': '修改标题'}, {'description': '修改描述'}, {'resource_type': 'video'},
            {'category': 'other'}, {'tags': 'changed'}, {'is_tutoring_reserved': True},
            {'status': 'approved'}, {'file_size': resource.file_size + 1}, {'uploader': reviewer},
            {'private_files': other.private_files}, {'private_files': swapped}, {'private_files': missing_cover},
            {'file': 'synthetic/legacy.txt'}, {'cover_image': 'synthetic/legacy.png'})
        for change in changes:
            with self.subTest(field=next(iter(change))), transaction.atomic():
                Resource.objects.filter(pk=resource.pk).update(**change)
                result = self.uploads.authenticated_references(user=reviewer, resource_id=resource.pk)
                self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
                transaction.set_rollback(True)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 4)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)

    def test_malformed_metadata_and_foreign_project_refuse_without_legacy_fallback(self):
        self.assertEqual(self.post().status_code, 201)
        resource = Resource.objects.get()
        for metadata in ({}, [], {'schema_version': 'unknown', 'files': {}},
                         {'schema_version': 'resource.private-upload.v1', 'files': {'file': None}}):
            with self.subTest(metadata=metadata), transaction.atomic():
                Resource.objects.filter(pk=resource.pk).update(private_files=metadata)
                result = self.uploads.authenticated_references(user=self.teacher, resource_id=resource.pk)
                self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
                transaction.set_rollback(True)
        with patch.object(self.uploads, 'project_ref', 'resource/other-project'):
            self.assertEqual(self.uploads.authenticated_references(user=self.teacher,
                resource_id=resource.pk).code, ReasonCode.AUDIT_UNAVAILABLE)

    def test_wrong_event_or_failed_authentication_returns_no_partial_reference_set(self):
        self.assertEqual(self.post(data=self.data(cover=True)).status_code, 201)
        resource = Resource.objects.get()
        read_event = self.uploads.read_event
        stored, context = self.stored_context(resource, 'cover_image')
        event_id = f'resource-upload/{context.object_uuid}/cover_image'
        event = read_event(event_id)
        self.assertIs(type(event), SecurityEventV2)
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
            retryable=False, trace_id='reference/synthetic-key')
        for replacement in (failure, replace(event, event_id='wrong/event'),
                            replace(event, kind=EventKind.POLICY), replace(event, object_ref='resources/other'),
                            replace(event, evidence_hashes=(('ciphertext', 'f' * 64),
                                ('report', dict(event.evidence_hashes)['report'])))):
            with self.subTest(replacement=type(replacement).__name__), \
                 patch.object(self.uploads, 'read_event', side_effect=lambda ref:
                     replacement if ref == event_id else read_event(ref)):
                result = self.uploads.authenticated_references(user=self.teacher, resource_id=resource.pk)
                self.assertIs(type(result), ProtectionError)
                self.assertEqual(result.code, replacement.code if replacement is failure else ReasonCode.AUDIT_UNAVAILABLE)
        with patch.object(self.uploads, 'read_event', side_effect=DatabaseError('synthetic unavailable')):
            self.assertEqual(self.uploads.authenticated_references(user=self.teacher,
                resource_id=resource.pk).code, ReasonCode.AUDIT_UNAVAILABLE)

    def test_raw_event_rows_without_authenticated_chain_are_not_upload_evidence(self):
        self.assertEqual(self.post().status_code, 201)
        resource = Resource.objects.get()
        AuthenticatedAuditEntry.objects.all().delete()
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        result = self.uploads.authenticated_references(user=self.teacher, resource_id=resource.pk)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
