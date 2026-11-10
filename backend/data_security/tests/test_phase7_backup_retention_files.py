"""Real retention file operations on opaque synthetic packages, not age/PG recovery."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from data_security.adapters.persistence.backup import PostgresAgeBackup
from data_security.application.backup_retention import BackupRetention
from data_security.contracts import (
    AuditReceipt, BASELINE_LIMITS, Environment, KeyPurpose, KeyReference, KeyStatus,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, Role,
)
from data_security.tests.fixtures import examples


class BackupRetentionFileTests(TestCase):
    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        self.packages, self.private = root / 'packages', root / 'private'
        for directory in (self.packages, self.private):
            directory.mkdir(mode=0o700)
            directory.chmod(0o700)
        self.now = datetime(2026, 11, 10, tzinfo=timezone.utc)
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', role=Role.SERVICE,
            environment=Environment.EVALUATION, domain='ctf', purpose=Purpose.STORAGE)
        key = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='enc-data/v1', purpose=KeyPurpose.DATA,
                           version='v1', status=KeyStatus.ACTIVE)
        self.resolver = Mock()
        self.port = PostgresAgeBackup(resolver=self.resolver, service_identity='service/security', database={},
            directory=self.packages, checks=(('fixture/count', 'SELECT 1'),), environment=Environment.EVALUATION,
            domain='ctf', age=Path('/unexecuted/age'), pg_dump=Path('/unexecuted/pg_dump'),
            pg_restore=Path('/unexecuted/pg_restore'), private_root=self.private,
            code_version='phase7-retention-files/v1', required_keys=(key,), clock=lambda: self.now)
        self.owner = BackupRetention(backups=self.port, limits=BASELINE_LIMITS)

    def package(self, number, created_at, cadence='daily'):
        object_id = format(number, '032x')
        database = b'opaque synthetic database package/' + object_id.encode()
        files = b'opaque synthetic private archive copy/' + object_id.encode()
        for suffix, data in (('.age', database), ('.files.age', files)):
            path = self.packages / (object_id + suffix)
            path.write_bytes(data)
            path.chmod(0o600)
        metadata = {'object_ref': 'backup/' + object_id, 'version': 'v2', 'state': 'verified',
            'ciphertext_hash': hashlib.sha256(database).hexdigest(), 'size_bytes': len(database),
            'environment': 'evaluation', 'domain': 'ctf',
            'recovery_manifest': {'fixture': 'not-a-restore-manifest'}}
        if cadence is not None:
            metadata['retention'] = {'created_at': created_at.isoformat(), 'cadence': cadence,
                'files_hash': hashlib.sha256(files).hexdigest(), 'files_size': len(files)}
        self.port._persist(object_id + '.json', metadata)
        return object_id

    def test_approved_eviction_removes_both_packages_but_keeps_registration_and_unenrolled_files(self):
        start = self.now - timedelta(days=8)
        oldest = self.package(1, start)
        for number in range(2, 9):
            self.package(number, start + timedelta(days=number - 1))
        legacy = self.package(99, start - timedelta(days=300), cadence=None)
        unrelated = self.private / 'unrelated.sealed'
        unrelated.write_bytes(b'untouched synthetic source')
        before = {path.name: path.read_bytes() for path in self.packages.iterdir()}
        approved = self.owner.preview(self.context)
        self.assertIsInstance(approved, tuple)
        self.assertEqual([record.backup.object_ref for record in approved], ['backup/' + oldest])
        self.assertEqual({path.name: path.read_bytes() for path in self.packages.iterdir()}, before)
        receipts = self.owner.apply(approved, self.context)
        self.assertIsInstance(receipts, tuple)
        self.assertEqual(len(receipts), 1)
        self.assertIsInstance(receipts[0], AuditReceipt)
        self.assertEqual(receipts[0].durability.value, 'durable')
        self.assertIsNone(receipts[0].chain_version)
        for suffix in ('.age', '.files.age'):
            self.assertFalse((self.packages / (oldest + suffix)).exists())
        retired = json.loads((self.packages / (oldest + '.json')).read_bytes())
        self.assertEqual((retired['state'], retired['event_id'], retired['retired_at']),
            ('retired', receipts[0].event_id, self.now.isoformat()))
        self.assertEqual(retired['recovery_manifest'], {'fixture': 'not-a-restore-manifest'})
        for name, data in before.items():
            if not name.startswith(oldest + '.'):
                self.assertEqual((self.packages / name).read_bytes(), data)
        self.assertTrue((self.packages / (legacy + '.files.age')).exists())
        self.assertEqual(unrelated.read_bytes(), b'untouched synthetic source')
        self.resolver.resolve.assert_not_called()

    def test_retained_archive_outlives_elapsed_days_until_new_slots_and_explicit_apply(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        daily = self.package(1, start)
        weekly = self.package(20, start, 'weekly')
        self.now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(self.owner.preview(self.context), ())
        self.assertEqual(self.owner.apply((), self.context), ())
        for object_id in (daily, weekly):
            self.assertTrue((self.packages / (object_id + '.files.age')).exists())
        for number in range(2, 9):
            self.package(number, start + timedelta(days=number * 30))
        for number in range(1, 5):
            self.package(20 + number, start + timedelta(weeks=number * 8), 'weekly')
        approved = self.owner.preview(self.context)
        self.assertIsInstance(approved, tuple)
        self.assertEqual({record.backup.object_ref for record in approved}, {'backup/' + daily, 'backup/' + weekly})
        for object_id in (daily, weekly):
            self.assertTrue((self.packages / (object_id + '.files.age')).exists())
        self.assertEqual(len(self.owner.apply(approved, self.context)), 2)
        for object_id in (daily, weekly):
            self.assertFalse((self.packages / (object_id + '.files.age')).exists())

    def test_stale_approval_and_corrupt_newer_archive_cannot_evict_the_older_copy(self):
        start = self.now - timedelta(days=10)
        oldest = self.package(1, start)
        for number in range(2, 9):
            self.package(number, start + timedelta(days=number - 1))
        approved = self.owner.preview(self.context)
        self.assertIsInstance(approved, tuple)
        newest = self.package(9, start + timedelta(days=9))
        self.assertEqual(self.owner.apply(approved, self.context).code, ReasonCode.REPORT_MISMATCH)
        path = self.packages / (newest + '.files.age')
        original = path.read_bytes()
        path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        self.assertEqual(self.owner.preview(self.context).code, ReasonCode.HASH_MISMATCH)
        self.assertEqual(self.owner.apply(approved, self.context).code, ReasonCode.HASH_MISMATCH)
        for suffix in ('.age', '.files.age'):
            self.assertTrue((self.packages / (oldest + suffix)).exists())
        self.assertEqual(json.loads((self.packages / (oldest + '.json')).read_bytes())['state'], 'verified')

    def test_second_archive_unlink_failure_keeps_intent_and_refuses_to_claim_retired(self):
        start = self.now - timedelta(days=8)
        oldest = self.package(1, start)
        for number in range(2, 9):
            self.package(number, start + timedelta(days=number - 1))
        approved = self.owner.preview(self.context)
        self.assertIsInstance(approved, tuple)
        target = self.packages / (oldest + '.files.age')
        unlink = Path.unlink

        def fail_second_archive(path, *args, **kwargs):
            if path == target:
                raise OSError('synthetic archive unlink failure')
            return unlink(path, *args, **kwargs)

        with patch.object(Path, 'unlink', fail_second_archive):
            result = self.owner.apply(approved, self.context)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        metadata = json.loads((self.packages / (oldest + '.json')).read_bytes())
        self.assertEqual((metadata['state'], metadata['event_id']), ('retiring', 'backup-retire/' + oldest))
        self.assertNotIn('retired_at', metadata)
        self.assertFalse((self.packages / (oldest + '.age')).exists())
        self.assertTrue(target.exists())
        self.assertEqual(self.owner.preview(self.context).code, ReasonCode.DELIVERY_UNKNOWN)
        for number in range(2, 9):
            for suffix in ('.age', '.files.age'):
                self.assertTrue((self.packages / (format(number, '032x') + suffix)).exists())
