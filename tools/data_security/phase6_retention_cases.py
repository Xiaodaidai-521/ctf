"""Opt-in D8 tests: fresh synthetic PostgreSQL databases, real age, isolated files only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from unittest.mock import patch

from data_security.application.backup_retention import BackupRetention
from data_security.contracts import BASELINE_LIMITS, AuditReceipt, ProtectionError, ReasonCode, StoredObject
from tools.data_security import phase6_backup_cases


class BackupRetentionAcceptance(phase6_backup_cases.PrivateBackupFixture):
    def setUp(self):
        super().setUp()
        self.owner = BackupRetention(backups=self.online, limits=BASELINE_LIMITS)
        self.start = datetime(2026, 9, 1, tzinfo=timezone.utc)

    def managed(self, number, cadence='daily'):
        self.online.clock = lambda: self.start + timedelta(days=number)
        result = self.online.create('snapshot/retention', self.public_ref, self.online_context, cadence=cadence)
        self.assertIsInstance(result, StoredObject)
        return result

    def test_real_bundles_retain_seven_daily_four_weekly_and_restore_retained_snapshot(self):
        daily = [self.managed(i) for i in range(9)]
        weekly = [self.managed(7 * i, 'weekly') for i in range(6)]
        legacy = self.create()
        orphan = self.work / ('f' * 32 + '.age')
        orphan.write_bytes(b'synthetic orphan ciphertext placeholder')
        orphan.chmod(0o600)
        before = {path.name: path.read_bytes() for path in self.work.glob('*.age')}
        approved = self.owner.preview(self.online_context)
        self.assertEqual({record.backup for record in approved}, set(daily[:2] + weekly[:2]))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.work.glob('*.age')})
        receipts = self.owner.apply(approved, self.online_context)
        self.assertEqual(len(receipts), 4)
        self.assertTrue(all(type(receipt) is AuditReceipt and receipt.chain_version is None for receipt in receipts))
        inventory = self.online.retention_inventory(self.online_context, BASELINE_LIMITS)
        self.assertEqual({record.backup for record in inventory}, set(daily[2:] + weekly[2:]))
        self.assertEqual(sum(record.cadence == 'daily' for record in inventory), 7)
        self.assertEqual(sum(record.cadence == 'weekly' for record in inventory), 4)
        for record in approved:
            stem = record.backup.object_ref.split('/')[1]
            self.assertFalse((self.work / (stem + '.age')).exists())
            self.assertFalse((self.work / (stem + '.files.age')).exists())
            metadata = json.loads((self.work / (stem + '.json')).read_text())
            self.assertEqual(metadata['state'], 'retired')
            self.assertEqual(metadata['event_id'], 'backup-retire/' + stem)
        for result in daily[2:] + weekly[2:] + [legacy]:
            stem = result.object_ref.split('/')[1]
            for suffix in ('.age', '.files.age'):
                self.assertEqual((self.work / (stem + suffix)).read_bytes(), before[stem + suffix])
        self.assertEqual(orphan.read_bytes(), before[orphan.name])
        self.assertEqual(self.owner.preview(self.online_context), ())
        self.assertIsInstance(self.offline.restore(weekly[2], self.offline_context), AuditReceipt)
        self.assertEqual(len(list(self.target_files.iterdir())), 2)

    def test_bad_newer_bundle_missing_part_or_registration_never_authorizes_retirement(self):
        records = [self.managed(i) for i in range(8)]
        approved = self.owner.preview(self.online_context)
        stem = records[-1].object_ref.split('/')[1]
        part = self.work / (stem + '.files.age')
        original = part.read_bytes()
        part.write_bytes(original[:-1])
        self.assertEqual(self.owner.apply(approved, self.online_context).code, ReasonCode.HASH_MISMATCH)
        part.unlink()
        self.assertIsInstance(self.owner.preview(self.online_context), ProtectionError)
        part.write_bytes(original)
        part.chmod(0o600)
        registration = self.work / (stem + '.json')
        raw = registration.read_bytes()
        metadata = json.loads(raw)
        metadata['retention']['cadence'] = 'monthly'
        registration.write_text(json.dumps(metadata))
        self.assertIsInstance(self.owner.preview(self.online_context), ProtectionError)
        registration.write_bytes(raw)
        self.assertEqual(len(list(self.work.glob('*.age'))), 16)
        self.assertEqual(self.owner.preview(self.online_context), approved)

    def test_bounds_and_current_service_context_deny_without_deleting(self):
        self.managed(0)
        self.managed(1)
        limited = BackupRetention(backups=self.online, limits=replace(BASELINE_LIMITS, max_actions=1))
        self.assertEqual(limited.preview(self.online_context).code, ReasonCode.LIMIT_EXCEEDED)
        wrong = replace(self.online_context, actor_ref='service/other')
        self.assertEqual(self.owner.apply((), wrong).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.offline.retention_inventory(self.offline_context, BASELINE_LIMITS).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(len(list(self.work.glob('*.age'))), 4)

    def test_interrupted_pair_retirement_keeps_intent_and_blocks_automatic_continuation(self):
        records = [self.managed(i) for i in range(9)]
        approved = self.owner.preview(self.online_context)
        stem = approved[0].backup.object_ref.split('/')[1]
        blocked = self.work / (stem + '.files.age')
        unlink = Path.unlink
        def fail_second_part(path, *args, **kwargs):
            if path == blocked:
                raise OSError('synthetic unlink failure')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_second_part):
            result = self.owner.apply(approved, self.online_context)
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertFalse((self.work / (stem + '.age')).exists())
        self.assertTrue(blocked.exists())
        metadata = json.loads((self.work / (stem + '.json')).read_text())
        self.assertEqual(metadata['state'], 'retiring')
        self.assertNotIn('retired_at', metadata)
        self.assertEqual(self.owner.preview(self.online_context).code, ReasonCode.DELIVERY_UNKNOWN)
        for record in records:
            if record.object_ref == approved[0].backup.object_ref:
                continue
            self.assertTrue((self.work / (record.object_ref.split('/')[1] + '.age')).exists())
        self.assertFalse(list(self.work.glob('*.partial')))

    def test_failed_creation_is_not_enrolled_and_v1_cannot_be_managed(self):
        with patch.object(self.online, 'pg_dump', '/bin/false'):
            failure = self.online.create('snapshot/failed', self.public_ref, self.online_context, cadence='daily')
        self.assertIsInstance(failure, ProtectionError)
        self.assertEqual(self.owner.preview(self.online_context), ())
        self.assertFalse(list(self.work.glob('*.age')))
        self.assertFalse(list(self.work.glob('*.json')))
        with patch.object(self.online, 'private_root', None):
            self.assertEqual(self.online.create('snapshot/v1', self.public_ref,
                self.online_context, cadence='daily').code, ReasonCode.INVALID_VALUE)
            self.assertEqual(self.create().version, 'v1')
        self.assertEqual(self.owner.preview(self.online_context), ())

    def test_formal_b_entry_uses_file_recipient_only_and_explicit_preview_apply(self):
        import django
        from ctf_backend.security_bootstrap import assemble_backup_retention
        from data_security.adapters.keys import FileKeyResolver
        from data_security.contracts import ContractViolation, Environment, KeyPurpose
        from data_security.tests.phase3_fixtures import configuration

        os.environ.update(DB_HOST='127.0.0.1', DB_PORT=str(self.database['port']),
                          DB_USER=self.database['user'], DB_NAME=self.source, DB_PASSWORD='')
        django.setup()
        with configuration(providers=()) as fixture:
            path, config = fixture[:2]
            with self.assertRaises(ContractViolation):
                assemble_backup_retention(config_path=path)
            recipient = path.parent / 'backup-recipient.key'
            recipient.write_bytes(self.recipient_file.read_bytes())
            recipient.chmod(0o600)
            manifest_path = Path(config['key_manifest'])
            manifest = json.loads(manifest_path.read_text())
            manifest['entries'].append({'reference': self.public_ref.to_wire(),
                'file': recipient.name, 'identities': ['service/security']})
            manifest_path.write_text(json.dumps(manifest))
            config.update(schema_version='ds.bootstrap.v2', policy_repository={'kind': 'file', 'writable': False})
            config['backup'] = dict(database=dict(self.database, host='127.0.0.1', dbname=self.source, password=''),
                directory=str(self.work), checks=self.checks, age=str(self.tools / 'usr/bin/age'),
                pg_dump=str(self.repo.parent / '.state/pg-install/bin/pg_dump'),
                pg_restore=str(self.repo.parent / '.state/pg-install/bin/pg_restore'),
                private_root=str(self.source_files), code_version='isolated/phase6',
                required_keys=[key.to_wire() for key in self.required])
            path.write_text(json.dumps(config))
            owner = assemble_backup_retention(config_path=path)
            self.assertIs(type(owner), BackupRetention)
            self.assertIs(type(owner.backups.resolver), FileKeyResolver)
            self.assertIsNone(owner.backups.identity_ref)
            self.assertIsInstance(owner.backups.resolver.resolve(self.private_ref, KeyPurpose.BACKUP_PRIVATE,
                                                                 'service/security'), ProtectionError)
            context = replace(self.online_context, actor_ref='service/security',
                              environment=Environment.EVALUATION, domain='ctf')
            for day in range(8):
                owner.backups.clock = lambda: self.start + timedelta(days=day)
                self.assertIsInstance(owner.backups.create('snapshot/formal-retention', self.public_ref,
                                                          context, cadence='daily'), StoredObject)
            approved = owner.preview(context)
            self.assertEqual(len(approved), 1)
            self.assertEqual(len(owner.apply(approved, context)), 1)
            self.assertEqual(len(owner.backups.retention_inventory(context, BASELINE_LIMITS)), 7)
