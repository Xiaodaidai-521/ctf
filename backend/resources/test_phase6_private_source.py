"""Opt-in internal source reads through real owners, file keys and isolated PostgreSQL."""
from dataclasses import replace
import json
import secrets
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import connection, transaction
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble_resource_uploads
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import (
    BoundedPayload, ContractViolation, KeyPurpose, MediaType, PayloadKind, ProtectionError,
    ReasonCode, SecretMaterial,
)
from users.models import CTFUser

from .models import Resource
from .test_phase6_private_uploads import PrivateResourceUploadFixture


class PrivateResourceSourceTests(PrivateResourceUploadFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.content = b'source-read@example.invalid,198.51.100.83,4111111111111111\n'
        self.assertEqual(self.post(data=self.data(cover=True)).status_code, 201)
        self.resource = Resource.objects.get()
        self.reader = assemble_resource_uploads(config_path=self.config_path,
            private_root=self.root, project_ref='resource-upload/synthetic', source_reads=True)
        self.store = self.reader.read_source.__self__

    def test_source_read_requires_explicit_opt_in_and_authenticated_audit_config(self):
        self.assertIsNone(self.uploads.read_source)
        with patch.object(self.uploads, 'authenticated_references', side_effect=AssertionError('disabled read')):
            result = self.uploads.read_original(user=self.teacher, resource_id=self.resource.pk)
        self.assertEqual(result.code, ReasonCode.SOURCE_NOT_APPROVED)
        for value in ('true', 1, None):
            with self.subTest(value=value), self.assertRaises(ContractViolation) as error:
                assemble_resource_uploads(config_path=self.config_path,
                    private_root=self.root, project_ref='resource-upload/synthetic', source_reads=value)
            self.assertEqual(error.exception.code, ReasonCode.INVALID_TYPE)
        self.config.pop('audit_chain')
        self.config.pop('policy_repository')
        self.config['schema_version'] = 'ds.bootstrap.v1'
        self.config_path.write_text(json.dumps(self.config))
        disabled = assemble_resource_uploads(config_path=self.config_path,
            private_root=self.root, project_ref='resource-upload/synthetic')
        self.assertIsNone(disabled.read_source)
        with self.assertRaises(ContractViolation) as error:
            assemble_resource_uploads(config_path=self.config_path,
                private_root=self.root, project_ref='resource-upload/synthetic', source_reads=True)
        self.assertEqual(error.exception.code, ReasonCode.SOURCE_NOT_APPROVED)

    def test_original_is_opened_fully_outside_transactions_without_publication(self):
        stored, context = self.stored_context(self.resource, 'file')
        files = {path.name: path.read_bytes() for path in self.root.iterdir()}
        rows = list(PrivateObject.objects.order_by('object_ref').values())
        resource = Resource.objects.values().get(pk=self.resource.pk)
        read_file, crypto_open = self.store._read_file, self.store.crypto.open

        def read_original_file(object_ref, *args):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(connection.get_autocommit())
            self.assertEqual(object_ref, stored.object_ref)
            return read_file(object_ref, *args)

        def fully_open(envelope, current, key):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(connection.get_autocommit())
            self.assertEqual(current, replace(context,
                authorization_ref=f'resource-read/{self.resource.pk}/user-{self.teacher.pk}'))
            return crypto_open(envelope, current, key)

        with patch.object(self.store, '_read_file', side_effect=read_original_file) as read, \
             patch.object(self.store.crypto, 'open', side_effect=fully_open) as opened, \
             patch.object(self.store, 'publish', side_effect=AssertionError('source published')), \
             patch.object(self.store, 'verify', side_effect=AssertionError('source changed state')), \
             patch.object(self.reader.audit, 'record', side_effect=AssertionError('source wrote event')), \
             patch('django.db.models.fields.files.FieldFile.open', side_effect=AssertionError('legacy read')):
            result = self.reader.read_original(user=self.teacher, resource_id=self.resource.pk)
        self.assertIs(type(result), BoundedPayload)
        self.assertEqual((result.kind, result.media_type), (PayloadKind.BINARY, MediaType.BINARY))
        self.assertTrue(result.binary == self.content)
        read.assert_called_once()
        opened.assert_called_once()
        self.assertEqual(files, {path.name: path.read_bytes() for path in self.root.iterdir()})
        self.assertEqual(rows, list(PrivateObject.objects.order_by('object_ref').values()))
        self.assertEqual(resource, Resource.objects.values().get(pk=self.resource.pk))
        self.assertEqual((SecurityAuditRecord.objects.count(), AuthenticatedAuditEntry.objects.count()), (2, 2))
        self.assertEqual(self.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(list(self.media.iterdir()), [])
        for path in self.root.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for marker in self.content.strip().split(b','):
                self.assertNotIn(marker, files[path.name])

    def test_reassembled_source_reader_uses_current_uploader_or_staff(self):
        reviewer = CTFUser.objects.create_user(username='source-staff', role='student', is_staff=True)
        CTFUser.objects.filter(pk=self.teacher.pk).update(role='student')
        for user in (self.teacher, reviewer):
            with self.subTest(user=user.pk):
                result = self.reader.read_original(user=user, resource_id=self.resource.pk)
                self.assertIs(type(result), BoundedPayload)
                self.assertTrue(result.binary == self.content)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.resource.refresh_from_db()
        self.assertEqual((self.resource.status, self.resource.download_count), ('pending', 0))

    def test_disabled_users_and_nonowners_never_reach_source_files(self):
        other = CTFUser.objects.create_user(username='source-other', role='teacher')
        admin = CTFUser.objects.create_user(username='source-admin', role='admin')
        reviewer = CTFUser.objects.create_user(username='source-revoked-staff', is_staff=True)
        with patch.object(self.reader, 'read_event', side_effect=AssertionError('unauthorized audit read')), \
             patch.object(self.store, '_read_file', side_effect=AssertionError('unauthorized file read')):
            for user in (AnonymousUser(), other, admin):
                with self.subTest(user=type(user).__name__):
                    result = self.reader.read_original(user=user, resource_id=self.resource.pk)
                    self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
            result = self.reader.read_original(user=self.teacher, resource_id=self.resource.pk + 1)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
            CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
            CTFUser.objects.filter(pk=reviewer.pk).update(is_staff=False)
            for user in (self.teacher, reviewer):
                self.assertFalse(connection.in_atomic_block)
                result = self.reader.read_original(user=user, resource_id=self.resource.pk)
                self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)

    def test_missing_authentication_or_changed_metadata_refuses_before_open(self):
        with patch.object(self.store, '_read_file', side_effect=AssertionError('unauthenticated file read')):
            Resource.objects.filter(pk=self.resource.pk).update(file_size=self.resource.file_size + 1)
            result = self.reader.read_original(user=self.teacher, resource_id=self.resource.pk)
            self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
            Resource.objects.filter(pk=self.resource.pk).update(file_size=self.resource.file_size)
            with patch.object(self.reader, 'project_ref', 'source/foreign-project'):
                result = self.reader.read_original(user=self.teacher, resource_id=self.resource.pk)
                self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
            AuthenticatedAuditEntry.objects.all().delete()
            self.assertEqual(SecurityAuditRecord.objects.count(), 2)
            result = self.reader.read_original(user=self.teacher, resource_id=self.resource.pk)
            self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)

    def test_wrong_or_missing_data_keys_do_not_return_original(self):
        resolve = self.store.crypto.keys.resolve
        missing = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
            retryable=False, trace_id='source/synthetic-missing-data-key')
        wrong = SecretMaterial(secrets.token_bytes(32), KeyPurpose.DATA)
        for material, expected in ((missing, ReasonCode.KEY_UNAVAILABLE), (wrong, ReasonCode.CIPHERTEXT_INVALID)):
            purposes = []

            def resolve_data(key, purpose, identity):
                purposes.append(purpose)
                return material if purpose is KeyPurpose.DATA else resolve(key, purpose, identity)

            with self.subTest(expected=expected), patch.object(self.store.crypto.keys, 'resolve', side_effect=resolve_data):
                result = self.reader.read_original(user=self.teacher, resource_id=self.resource.pk)
            self.assertIs(type(result), ProtectionError)
            self.assertEqual(result.code, expected)
            self.assertIn(KeyPurpose.AUDIT, purposes)
            self.assertEqual(purposes.count(KeyPurpose.DATA), 1)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_mutated_or_missing_ciphertext_is_not_returned_or_repaired(self):
        stored, _ = self.stored_context(self.resource, 'file')
        path = self.root / (stored.object_ref.removeprefix('private/') + '.sealed')
        encoded = path.read_bytes()
        changed = bytes([encoded[0] ^ 1]) + encoded[1:]
        for content, expected in ((changed, ReasonCode.HASH_MISMATCH),
                                  (encoded[:-1], ReasonCode.CIPHERTEXT_INVALID)):
            with self.subTest(expected=expected):
                path.write_bytes(content)
                result = self.reader.read_original(user=self.teacher, resource_id=self.resource.pk)
                self.assertIs(type(result), ProtectionError)
                self.assertEqual(result.code, expected)
                self.assertEqual(path.read_bytes(), content)
        path.write_bytes(encoded)
        path.chmod(0o640)
        self.assertEqual(self.reader.read_original(user=self.teacher,
            resource_id=self.resource.pk).code, ReasonCode.AUTHORIZATION_DENIED)
        path.chmod(0o600)
        path.unlink()
        self.assertEqual(self.reader.read_original(user=self.teacher,
            resource_id=self.resource.pk).code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertFalse(path.exists())
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_candidate_or_published_rows_and_foreign_context_are_not_source_reads(self):
        stored, context = self.stored_context(self.resource, 'file')
        row = PrivateObject.objects.filter(object_ref=stored.object_ref)
        with patch.object(self.store, '_read_file', side_effect=AssertionError('unapproved source file read')):
            for state in ('candidate', 'published'):
                with self.subTest(state=state):
                    row.update(state=state)
                    self.assertEqual(self.reader.read_original(user=self.teacher,
                        resource_id=self.resource.pk).code, ReasonCode.AUTHORIZATION_DENIED)
            row.update(state='verified')
            for state in ('candidate', 'published'):
                self.assertEqual(self.store.open_verified_source(replace(stored, state=state),
                    context).code, ReasonCode.AUTHORIZATION_DENIED)
            foreign = replace(context, field_ref='resources/cover_image')
            self.assertEqual(self.store.open_verified_source(stored, foreign).code, ReasonCode.HASH_MISMATCH)
            row.delete()
            self.assertEqual(self.reader.read_original(user=self.teacher,
                resource_id=self.resource.pk).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(len(list(self.root.iterdir())), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_outer_transaction_is_rejected_before_authentication_or_file_work(self):
        with patch.object(self.reader, 'read_event', side_effect=AssertionError('transactional audit read')), \
             patch.object(self.store, '_read_file', side_effect=AssertionError('transactional file read')), \
             transaction.atomic():
            result = self.reader.read_original(user=self.teacher, resource_id=self.resource.pk)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(connection.in_atomic_block)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
