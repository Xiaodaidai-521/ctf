"""B3 owner/M6 tests for the isolated PostgreSQL session, never SQLite.

The recovery callable below is a synthetic trusted-verifier fixture. These tests
exercise its precise source binding and refusal, not a real backup/restore or
6-F06/RPO/RTO. The independent full-recovery suite must supply that evidence.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.db import DatabaseError, connection
from django.test import TransactionTestCase

from audit.models import SecurityAuditRecord
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject
from data_security.adapters.persistence.private_maintenance import DjangoPrivateMaintenance
from data_security.application.crypto_service import CryptoService
from data_security.contracts import (
    AuditReceipt, CipherEnvelope, Durability, Environment, EventKind, KeyStatus, ObjectContext, Outcome,
    ProtectionError, ReasonCode, SecurityEventV2, StoredObject,
)
from users.models import CTFUser

from .models import Resource
from .test_phase6_b2_fixtures import PrivateFileHTTPFixture


class LegacyMaintenanceFixture(PrivateFileHTTPFixture):
    def setUp(self):
        super().setUp()
        self.covered = {}
        self.maintenance = DjangoPrivateMaintenance(operations=self.uploads.operations,
            legacy_root=self.media, limits=self.preparation.limits, verify_recovery=self.trusted_recovery)
        self.uploads.maintenance = self.maintenance

    def trusted_recovery(self, principal):
        covered = self.covered.get(principal.source_ref)
        if covered is None or (principal.source_hash, principal.actor_ref) != covered[:2]:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.SOURCE_NOT_APPROVED,
                retryable=False, trace_id='b3/synthetic-recovery')
        return covered[2]

    def cover_staging(self, operation, *, owner=None):
        """Synthetic DURABLE journal receipt, not an authenticated ledger or real backup claim."""
        owner = owner or self.uploads
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        source_hash = self.maintenance.source_hash(row)
        receipt = AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id='recovery-verify/' + uuid4().hex,
            durability=Durability.DURABLE, stored_at=owner.clock(), chain_version=None,
            entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
        self.assertIs(type(receipt), AuditReceipt)
        self.covered[operation.operation_ref] = (source_hash, operation.actor_ref, receipt)
        return source_hash

    def legacy(self, *, cover=False):
        token = str(uuid4())
        names = {'file': 'resources/' + token + '.txt'}
        if cover:
            names['cover_image'] = 'resource_covers/' + token + '.png'
        paths = {}
        for field, name in names.items():
            path = self.media / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(self.content if field == 'file' else b'B3 synthetic old cover')
            paths[field] = path
        resource = Resource.objects.create(title='合成旧资料', description='隔离旧源', resource_type='document',
            category='security', uploader=self.teacher, file_size=len(self.content), **names)
        return resource, paths

    def maintain(self, resource, action, *, operation_id=None, user=None, replaces=None):
        return self.uploads.maintain_legacy(user=user or self.teacher, resource_id=resource.pk,
            operation_id=operation_id or self.operation_id, action=action, replaces=replaces)

    def rotate_manifest(self, owner):
        preparation = owner.prepare.__self__
        old = preparation.data_key
        read_only, new = replace(old, status=KeyStatus.READ_ONLY), replace(old, key_ref='enc-data/v2', version='v2')
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_text())
        for entry in manifest['entries']:
            if entry['reference']['key_ref'] == old.key_ref:
                entry['reference'] = read_only.to_wire()
        path = manifest_path.parent / 'b3-new-data.key'
        path.write_bytes(os.urandom(32))
        path.chmod(0o600)
        manifest['entries'].append({'reference': new.to_wire(), 'file': path.name,
                                   'identities': [preparation.crypto.service_identity]})
        manifest_path.write_text(json.dumps(manifest))
        crypto = CryptoService(keys=preparation.crypto.keys, service_identity=preparation.crypto.service_identity,
            random_bytes=os.urandom, environment=preparation.crypto.environment, limits=preparation.limits,
            retained_data_keys=(read_only,))
        preparation.crypto = preparation.store.crypto = crypto
        preparation.data_key, owner.data_key_ref = new, new.key_ref
        return old, new


class PrivateLegacyResourceTests(LegacyMaintenanceFixture, TransactionTestCase):
    def test_stage_preserves_old_files_and_registers_recoverable_candidates_only(self):
        resource, paths = self.legacy(cover=True)
        operation = self.maintain(resource, 'stage')
        self.assertNotIsInstance(operation, ProtectionError)
        self.assertEqual(operation.state, 'prepared')
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        resource.refresh_from_db()
        self.assertEqual(resource.private_files, {})
        self.assertEqual(resource.file.name, paths['file'].relative_to(self.media).as_posix())
        self.assertEqual(row.legacy_sources['phase'], 'staged')
        self.assertEqual(set(row.files), {'resources/file', 'resources/cover_image'})
        self.assertFalse(SecurityAuditRecord.objects.exists())
        for field, path in paths.items():
            item = row.files['resources/' + field]
            descriptor = row.legacy_sources['sources']['resources/' + field]
            self.assertEqual(descriptor['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(item['input_hash'], descriptor['sha256'])
            stored, context = StoredObject.from_wire(item['stored']), ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})
            self.assertEqual(stored.state, 'verified')
            self.assertEqual(self.preparation.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(PrivateObject.objects.count(), 2)

    def test_missing_recovery_boolean_or_staging_mismatch_never_cuts_or_deletes(self):
        resource, paths = self.legacy()
        operation = self.maintain(resource, 'stage')
        self.assertEqual(self.maintain(resource, 'migrate').code, ReasonCode.SOURCE_NOT_APPROVED)
        with patch.object(self.maintenance, 'verify_recovery', return_value=True):
            self.assertEqual(self.maintain(resource, 'migrate').code, ReasonCode.AUDIT_UNAVAILABLE)
        self.cover_staging(operation)
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        row.legacy_sources['replaces'] = 'uncovered/previous-operation'
        row.save(update_fields=['legacy_sources'])
        self.assertEqual(self.maintain(resource, 'migrate').code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertIsInstance(self.maintain(resource, 'delete'), ProtectionError)
        resource.refresh_from_db()
        self.assertEqual(resource.private_files, {})
        self.assertTrue(paths['file'].exists())

    def test_migrate_then_explicit_exact_delete_reuses_v2_binding_and_keeps_ciphertext(self):
        resource, paths = self.legacy(cover=True)
        operation = self.maintain(resource, 'stage')
        source_hash = self.cover_staging(operation)
        self.assertEqual(self.maintain(resource, 'migrate').state, 'committed')
        resource.refresh_from_db()
        self.assertEqual((resource.file.name, resource.cover_image.name), ('', ''))
        self.assertEqual(resource.uploader_id, self.teacher.pk)
        self.assertEqual(resource.private_files['schema_version'], 'resource.private-upload.v2')
        references = self.uploads.authenticated_references(user=self.teacher, resource_id=resource.pk)
        self.assertEqual(len(references), 2)
        self.assertEqual(self.uploads.open_download(user=self.teacher, resource_id=resource.pk).binary, self.content)
        before = {stored.object_ref: (self.root / (stored.object_ref[8:] + '.sealed')).read_bytes()
                  for _, _, stored in references}
        for field in ('file', 'cover_image'):
            event = self.uploads.read_event(f'resource-upload/{operation.object_uuid}/{field}')
            self.assertEqual(dict(event.evidence_hashes)['archive'], source_hash)
        self.assertTrue(all(path.exists() for path in paths.values()))
        self.assertEqual(self.maintain(resource, 'delete').state, 'committed')
        self.assertTrue(all(not path.exists() for path in paths.values()))
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        self.assertEqual(row.legacy_sources['phase'], 'deleted')
        self.assertEqual(self.maintenance.source_hash(row), source_hash)
        self.assertEqual({ref: (self.root / (ref[8:] + '.sealed')).read_bytes() for ref in before}, before)
        self.assertEqual(PrivateObject.objects.count(), 2)

    def test_quarantine_retires_access_but_preserves_encrypted_copy_after_plaintext_deletion(self):
        resource, paths = self.legacy()
        operation = self.maintain(resource, 'stage')
        self.cover_staging(operation)
        self.assertEqual(self.maintain(resource, 'quarantine').state, 'retired')
        self.assertIsInstance(self.uploads.authenticated_references(user=self.teacher, resource_id=resource.pk),
                              ProtectionError)
        self.assertTrue(paths['file'].exists())
        self.assertEqual(self.maintain(resource, 'delete').state, 'retired')
        self.assertFalse(paths['file'].exists())
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_current_original_owner_required_even_for_staff_and_cached_user(self):
        resource, paths = self.legacy()
        self.assertEqual(self.maintain(resource, 'stage', user=self.reviewer).code, ReasonCode.AUTHORIZATION_DENIED)
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
        self.assertEqual(self.maintain(resource, 'stage').code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(PrivateFileOperation.objects.exists())
        self.assertTrue(paths['file'].exists())

    def test_revocation_during_protection_audit_rolls_back_owner_cutover(self):
        resource, paths = self.legacy()
        operation = self.maintain(resource, 'stage')
        self.cover_staging(operation)
        record = self.uploads.audit.record

        def revoked(event, durability):
            result = record(event, durability)
            if event.kind is EventKind.PROTECTION:
                CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
            return result

        with patch.object(self.uploads.audit, 'record', side_effect=revoked):
            self.assertEqual(self.maintain(resource, 'migrate').code, ReasonCode.AUTHORIZATION_DENIED)
        resource.refresh_from_db()
        self.assertEqual(resource.private_files, {})
        self.assertTrue(paths['file'].exists())
        self.assertEqual(PrivateFileOperation.objects.get().state, 'prepared')
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)

    def test_fsync_registration_loss_resumes_exact_staging_without_reencryption(self):
        resource, paths = self.legacy()
        with patch.object(PrivateObject.objects, 'get_or_create', side_effect=DatabaseError('synthetic lost row')):
            self.assertEqual(self.maintain(resource, 'stage').code, ReasonCode.DELIVERY_UNKNOWN)
        row = PrivateFileOperation.objects.get()
        before = deepcopy(row.files)
        self.assertFalse(PrivateObject.objects.exists())
        with patch.object(self.preparation.crypto, 'seal', side_effect=AssertionError('staging reencrypted')):
            self.assertEqual(self.maintain(resource, 'stage').state, 'prepared')
        row.refresh_from_db()
        self.assertEqual(row.files['resources/file']['stored']['object_ref'],
                         before['resources/file']['stored']['object_ref'])
        self.assertTrue(paths['file'].exists())

    def test_commit_ack_loss_keeps_source_and_replays_no_new_binding(self):
        resource, paths = self.legacy()
        operation = self.maintain(resource, 'stage')
        self.cover_staging(operation)
        commit, lost = connection.commit, False

        def commit_then_lose():
            nonlocal lost
            should_lose = not lost and PrivateFileOperation.objects.filter(state='committed').exists()
            result = commit()
            if should_lose:
                lost = True
                raise DatabaseError('synthetic cutover confirmation lost')
            return result

        with patch.object(connection, 'commit', side_effect=commit_then_lose):
            self.assertEqual(self.maintain(resource, 'migrate').code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertTrue(lost)
        self.assertTrue(paths['file'].exists())
        with patch.object(self.uploads.audit, 'record', side_effect=AssertionError('replayed protection')):
            self.assertEqual(self.maintain(resource, 'migrate').state, 'committed')
        self.assertEqual(PrivateObject.objects.count(), 1)

    def test_changed_source_is_not_deleted_and_unrelated_exact_name_survives(self):
        resource, paths = self.legacy()
        operation = self.maintain(resource, 'stage')
        self.cover_staging(operation)
        self.maintain(resource, 'migrate')
        neighbor = paths['file'].with_suffix('.other')
        neighbor.write_bytes(b'B3 unrelated synthetic file')
        paths['file'].write_bytes(b'B3 changed legacy source')
        self.assertEqual(self.maintain(resource, 'delete').code, ReasonCode.HASH_MISMATCH)
        self.assertTrue(paths['file'].exists())
        self.assertTrue(neighbor.exists())
        self.assertEqual(PrivateFileOperation.objects.get().legacy_sources['phase'], 'delete-authorized')

    def test_shared_legacy_filefield_name_blocks_deletion(self):
        resource, paths = self.legacy()
        operation = self.maintain(resource, 'stage')
        self.cover_staging(operation)
        self.maintain(resource, 'migrate')
        Resource.objects.create(title='共享旧路径', description='合成重复引用', resource_type='document',
            category='security', uploader=self.teacher, file=paths['file'].relative_to(self.media).as_posix())
        self.assertEqual(self.maintain(resource, 'delete').code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertTrue(paths['file'].exists())

    def test_missing_new_audit_or_damaged_candidate_blocks_source_deletion(self):
        resource, paths = self.legacy()
        operation = self.maintain(resource, 'stage')
        self.cover_staging(operation)
        self.maintain(resource, 'migrate')
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
            retryable=False, trace_id='b3/synthetic-audit')
        with patch.object(self.uploads, 'read_event', return_value=failure):
            self.assertEqual(self.maintain(resource, 'delete').code, ReasonCode.AUDIT_UNAVAILABLE)
        row = PrivateObject.objects.get()
        path = self.root / (row.object_ref[8:] + '.sealed')
        path.write_bytes(path.read_bytes()[:-1])
        self.assertIsInstance(self.maintain(resource, 'delete'), ProtectionError)
        self.assertTrue(paths['file'].exists())

    def test_delete_ack_loss_retains_tombstone_and_retries_without_new_audit(self):
        resource, paths = self.legacy()
        operation = self.maintain(resource, 'stage')
        self.cover_staging(operation)
        self.maintain(resource, 'migrate')
        unlink = Path.unlink

        def lost(path, *args, **kwargs):
            result = unlink(path, *args, **kwargs)
            if path == paths['file']:
                raise OSError('synthetic unlink confirmation lost')
            return result

        with patch.object(Path, 'unlink', lost):
            self.assertEqual(self.maintain(resource, 'delete').code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertFalse(paths['file'].exists())
        self.assertEqual(PrivateFileOperation.objects.get().legacy_sources['phase'], 'delete-authorized')
        with patch.object(self.uploads.audit, 'record', side_effect=AssertionError('delete audit replay')):
            self.assertEqual(self.maintain(resource, 'delete').state, 'committed')
        self.assertEqual(PrivateFileOperation.objects.get().legacy_sources['phase'], 'deleted')

    def test_replacement_staging_reencrypts_with_new_root_and_needs_new_recovery(self):
        resource, paths = self.legacy()
        original = self.maintain(resource, 'stage')
        self.cover_staging(original)
        before = PrivateFileOperation.objects.get(operation_ref=original.operation_ref)
        old_files = deepcopy(before.files)
        old_item = old_files['resources/file']
        old_path = self.root / (old_item['stored']['object_ref'][8:] + '.sealed')
        old_bytes = old_path.read_bytes()
        old, new = self.rotate_manifest(self.uploads)
        replacement_id = uuid4()
        result = self.maintain(resource, 'rotate', operation_id=replacement_id, replaces=self.operation_id)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result.state, 'prepared')
        replacement = PrivateFileOperation.objects.get(operation_ref=result.operation_ref)
        new_item = replacement.files['resources/file']
        self.assertEqual(new_item['context'], old_item['context'])
        self.assertNotEqual(new_item['stored']['object_ref'], old_item['stored']['object_ref'])
        new_bytes = (self.root / (new_item['stored']['object_ref'][8:] + '.sealed')).read_bytes()
        new_envelope = CipherEnvelope.from_json(new_bytes)
        self.assertEqual(new_envelope.key, new)
        self.assertEqual(CipherEnvelope.from_json(old_bytes).key, old)
        self.assertNotEqual(new_envelope.ciphertext_and_tag, CipherEnvelope.from_json(old_bytes).ciphertext_and_tag)
        context = ObjectContext(**{**old_item['context'], 'environment': Environment(old_item['context']['environment'])})
        self.assertEqual(self.preparation.crypto.open(new_envelope, context, new).binary, self.content)
        before.refresh_from_db()
        self.assertEqual(before.files, old_files)
        self.assertEqual(before.state, 'prepared')
        self.assertEqual(old_path.read_bytes(), old_bytes)
        self.assertTrue(paths['file'].exists())
        self.assertEqual(self.maintain(resource, 'migrate', operation_id=replacement_id).code,
                         ReasonCode.SOURCE_NOT_APPROVED)
        self.cover_staging(result)
        self.assertEqual(self.maintain(resource, 'migrate', operation_id=replacement_id).state, 'committed')
        self.assertEqual(PrivateObject.objects.count(), 2)

    def test_signed_upload_is_not_rekeyed_and_old_key_retirement_remains_blocked(self):
        uploaded = self.upload()
        self.assertEqual(uploaded.status_code, 201)
        resource = Resource.objects.get()
        original = deepcopy(resource.private_files)
        operation = PrivateFileOperation.objects.get()
        files = deepcopy(operation.files)
        records = list(SecurityAuditRecord.objects.values())
        self.rotate_manifest(self.uploads)
        result = self.maintain(resource, 'rotate', operation_id=uuid4(), replaces=self.operation_id)
        self.assertEqual(result.code, ReasonCode.SOURCE_NOT_APPROVED)
        resource.refresh_from_db()
        operation.refresh_from_db()
        self.assertEqual(resource.private_files, original)
        self.assertEqual(operation.files, files)
        self.assertEqual(list(SecurityAuditRecord.objects.values()), records)
        self.assertEqual(self.uploads.open_download(user=self.teacher, resource_id=resource.pk).binary, self.content)
        inventory = self.maintenance.key_inventory('enc-data/v1')
        self.assertEqual(inventory['references'], (PrivateObject.objects.get().object_ref,))
        self.assertFalse(inventory['retirement_allowed'])
        self.assertIn('retained-backups', inventory['uninspected'])

    def test_unknown_and_unsafe_legacy_paths_never_authorize_staging_or_cleanup(self):
        resource, paths = self.legacy()
        self.assertEqual(self.maintain(resource, 'delete').code, ReasonCode.DELIVERY_UNKNOWN)
        outside = self.media.parent / ('b3-outside-' + str(uuid4()))
        outside.write_bytes(b'B3 unapproved synthetic source')
        self.addCleanup(outside.unlink, missing_ok=True)
        paths['file'].unlink()
        paths['file'].symlink_to(outside)
        self.assertEqual(self.maintain(resource, 'stage').code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(PrivateFileOperation.objects.exists())
        self.assertTrue(outside.exists())
