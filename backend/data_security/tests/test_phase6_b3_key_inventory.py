"""Metadata-only inventory checks; synthetic package bytes are not age acceptance."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from data_security.adapters.persistence.backup import PostgresAgeBackup
from data_security.contracts import BASELINE_LIMITS, KeyPurpose, KeyReference, KeyStatus, ProtectionContext, Purpose, ReasonCode
from data_security.tests.fixtures import examples


class RetainedBackupKeyInventoryTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='b3-key-inventory-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', purpose=Purpose.STORAGE)
        self.backups = object.__new__(PostgresAgeBackup)
        self.backups.directory, self.backups.environment = self.root, self.context.environment
        self.backups.domain, self.backups.service_identity = self.context.domain, self.context.actor_ref
        self.recipient = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='backup-recipient/v1',
            purpose=KeyPurpose.BACKUP_PUBLIC, version='v1', status=KeyStatus.ACTIVE)
        self.key = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='enc-data/v1',
            purpose=KeyPurpose.DATA, version='v1', status=KeyStatus.READ_ONLY)

    def register(self, object_id, recipient):
        data, files = b'synthetic database ciphertext', b'synthetic files ciphertext'
        for suffix, raw in (('.age', data), ('.files.age', files)):
            path = self.root / (object_id + suffix)
            path.write_bytes(raw)
            path.chmod(0o600)
        metadata = {'object_ref': 'backup/' + object_id, 'state': 'verified',
            'ciphertext_hash': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data),
            'recovery_manifest': {'environment': self.context.environment.value, 'domain': self.context.domain,
                'recipient_ref': recipient.key_ref, 'required_keys': [self.key.to_wire()],
                'files_archive': {'sha256': hashlib.sha256(files).hexdigest(), 'size_bytes': len(files)},
                'full_inventory': {'recipient': recipient.to_wire()}}}
        path = self.root / (object_id + '.json')
        path.write_text(json.dumps(metadata))
        path.chmod(0o600)

    def test_old_and_new_recipients_and_read_keys_remain_visible_without_retirement_authority(self):
        self.register('a' * 32, self.recipient)
        self.register('b' * 32, replace(self.recipient, key_ref='backup-recipient/v2', version='v2'))
        result = self.backups.key_inventory(self.context, BASELINE_LIMITS)
        self.assertEqual(result['recipient_refs'], ['backup-recipient/v1', 'backup-recipient/v2'])
        self.assertEqual(result['required_key_refs'], ['enc-data/v1'])
        self.assertEqual(len(result['bundles']), 2)
        self.assertFalse(result['retirement_allowed'])
        self.assertFalse(result['metadata_age_authenticated'])
        self.assertTrue(result['offline_identity_mapping_required'])

    def test_opaque_and_older_packages_are_unresolved_not_zero_references(self):
        (self.root / ('c' * 32 + '.age')).write_bytes(b'orphan')
        old = self.root / ('d' * 32 + '.json')
        old.write_text(json.dumps({'object_ref': 'backup/' + 'd' * 32, 'state': 'verified'}))
        old.chmod(0o600)
        result = self.backups.key_inventory(self.context, BASELINE_LIMITS)
        self.assertEqual(result['unresolved_bundles'], 2)
        self.assertFalse(result['retirement_allowed'])
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_damaged_package_and_foreign_scope_never_return_a_successful_inventory(self):
        self.register('a' * 32, self.recipient)
        foreign = replace(self.context, domain='other')
        self.assertEqual(self.backups.key_inventory(foreign, BASELINE_LIMITS).code, ReasonCode.AUTHORIZATION_DENIED)
        (self.root / ('a' * 32 + '.files.age')).write_bytes(b'changed')
        self.assertEqual(self.backups.key_inventory(self.context, BASELINE_LIMITS).code, ReasonCode.HASH_MISMATCH)
