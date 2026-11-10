"""Opt-in B3 full-inventory PG/age cases. Run only in a sealed independent test snapshot.

These exercise the backup adapter, not complete business-owner verification or RPO/RTO acceptance.
The existing default-v2 backup/retention suites remain independent regression requirements.
"""
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
import json
import subprocess

import psycopg2

from data_security.adapters.persistence.backup import PostgresAgeBackup
from data_security.adapters.persistence.recovery_state import RecoveryJournal, recovery_admission
from data_security.application.backup_recovery import BackupCycle
from data_security.contracts import AuditReceipt, BASELINE_LIMITS, ProtectionError, ReasonCode
from tools.data_security.phase6_backup_cases import PrivateBackupFixture


class FullInventoryBackupAcceptance(PrivateBackupFixture):
    def setUp(self):
        super().setUp()
        for name in ('online', 'offline'):
            previous = getattr(self, name)
            setattr(self, name, PostgresAgeBackup(resolver=previous.resolver, service_identity=previous.service_identity,
                database=previous.database, directory=previous.directory, checks=previous.checks,
                environment=previous.environment, domain=previous.domain, age=previous.age, pg_dump=previous.pg_dump,
                pg_restore=previous.pg_restore, identity_ref=previous.identity_ref, private_root=previous.private_root,
                code_version=previous.code_version, required_keys=previous.required_keys,
                full_inventory=True, limits=BASELINE_LIMITS))
        self.journal = RecoveryJournal(root=self.target_files, target_identity=self.offline.source_identity,
            code_version=self.offline.code_version, environment=self.offline.environment, domain=self.offline.domain,
            service_identity=self.offline.service_identity, clock=lambda: datetime.now(timezone.utc), limits=BASELINE_LIMITS)
        self.journal.start(self.offline_context)

    def test_all_tables_and_opaque_pending_files_survive_without_opening_traffic(self):
        pending = self.source_files / ('e' * 64 + '.sealed')
        pending.write_bytes(b'partial ciphertext, deliberately not decodable')
        pending.chmod(0o600)
        with psycopg2.connect(**dict(self.database, dbname=self.source)) as connection:
            with connection.cursor() as cursor:
                cursor.execute('CREATE TABLE additional_owner (value text NOT NULL)')
                cursor.execute("INSERT INTO additional_owner VALUES ('synthetic extra owner row')")
        before = datetime.now(timezone.utc)
        backup = self.create()
        after = datetime.now(timezone.utc)
        receipt = self.offline.restore(backup, self.offline_context)
        self.assertIsInstance(receipt, AuditReceipt)
        registration = self.offline.read_restoration(receipt, self.offline_context)
        self.assertNotIsInstance(registration, ProtectionError)
        full = registration['full_inventory']
        self.assertTrue(before <= datetime.fromisoformat(full['snapshot_at']) <= after)
        self.assertEqual(full['source_identity'], self.online.source_identity)
        self.assertEqual(full['schema']['table/public/additional_owner']['records'], 1)
        self.assertEqual(full['pending_files']['records'], 1)
        self.assertEqual((self.target_files / pending.name).read_bytes(), pending.read_bytes())
        self.assertEqual(self.offline.source_inventory(self.offline_context), {
            'schema': full['schema'], 'private_files': registration['private_files'], 'pending_files': full['pending_files']})
        with closing(psycopg2.connect(**dict(self.database, dbname=self.target))) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT state FROM security_policies_privateobject ORDER BY object_ref')
                self.assertEqual(cursor.fetchall(), [('candidate',), ('published',)])
        self.assertEqual(recovery_admission(self.target_files, self.offline.source_identity, limits=BASELINE_LIMITS).code,
                         ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.journal.read(self.offline_context)['state'], 'closed')

    def test_full_bundle_requires_explicit_reader_and_closed_empty_target(self):
        backup = self.create()
        self.offline.full_inventory = False
        self.assert_no_restore(self.offline.restore(backup, self.offline_context))
        self.offline.full_inventory = True
        unrelated = self.target_files / ('f' * 64 + '.sealed')
        unrelated.write_bytes(b'retained target evidence')
        unrelated.chmod(0o600)
        self.assert_no_restore(self.offline.restore(backup, self.offline_context))
        self.assertEqual(unrelated.read_bytes(), b'retained target evidence')

    def test_damaged_files_part_fails_before_sql_and_preserves_closed_journal(self):
        backup = self.create()
        part = self.work / (backup.object_ref.split('/')[1] + '.files.age')
        part.write_bytes(part.read_bytes()[:-1])
        before = (self.target_files / '.restore-state.json').read_bytes()
        self.assert_no_restore(self.offline.restore(backup, self.offline_context))
        self.assertEqual((self.target_files / '.restore-state.json').read_bytes(), before)
        self.assertEqual(len(list(self.target_files.iterdir())), 1)

    def test_missing_required_key_never_restores_or_relabels_failure_as_success(self):
        backup = self.create()
        self.offline_resolver.grants.pop((self.data_key.key_ref, self.data_key.purpose, self.offline.service_identity))
        result = self.offline.restore(backup, self.offline_context)
        self.assertEqual(result.code, ReasonCode.KEY_UNAVAILABLE)
        self.assert_no_restore(result)
        self.assertEqual(len(list(self.target_files.iterdir())), 1)

    def test_retained_unknown_file_change_is_detected_after_restore(self):
        pending = self.source_files / ('e' * 64 + '.sealed')
        pending.write_bytes(b'opaque pending ciphertext')
        pending.chmod(0o600)
        backup = self.create()
        receipt = self.offline.restore(backup, self.offline_context)
        self.assertIsInstance(receipt, AuditReceipt)
        original = self.offline.source_inventory(self.offline_context)
        restored = self.target_files / pending.name
        restored.write_bytes(restored.read_bytes() + b'changed')
        current = self.offline.source_inventory(self.offline_context)
        self.assertNotEqual(current['pending_files'], original['pending_files'])
        self.assertEqual(current['schema'], original['schema'])
        self.assertTrue(restored.exists())

    def test_restore_receipt_is_bound_to_selected_target_and_code(self):
        receipt = self.offline.restore(self.create(), self.offline_context)
        self.assertIsInstance(receipt, AuditReceipt)
        self.assertIsNone(receipt.chain_version)
        self.offline.source_identity = 'a' * 64
        self.assertIsInstance(self.offline.read_restoration(receipt, self.offline_context), ProtectionError)

    def test_nonfull_daily_registration_does_not_satisfy_full_backup_cadence(self):
        from uuid import uuid4
        self.online.full_inventory = False
        old = self.online.create('snapshot/old-daily', self.public_ref, self.online_context, cadence='daily')
        self.assertNotIsInstance(old, ProtectionError)
        self.online.full_inventory = True
        cycle = BackupCycle(backups=self.online, recipient=self.public_ref, limits=BASELINE_LIMITS,
            clock=lambda: datetime.now(timezone.utc), identity=lambda: uuid4().hex)
        created = cycle.run_due(self.online_context)
        self.assertIsInstance(created, tuple)
        self.assertEqual(len(created), 2)
        inventory = self.online.retention_inventory(self.online_context, BASELINE_LIMITS, full_only=True)
        self.assertEqual({record.cadence for record in inventory}, {'daily', 'weekly'})
        self.assertNotIn(old.object_ref, {record.backup.object_ref for record in inventory})
        self.assertEqual(cycle.run_due(self.online_context), ())
        self.assertTrue((self.work / (old.object_ref.split('/')[1] + '.age')).exists())

    def test_recipient_rotation_preserves_old_packages_and_requires_the_matching_offline_identity(self):
        old = self.create()
        new_recipient = replace(self.public_ref, key_ref='backup-recipient/v2', version='v2')
        recipient_file = self.work / 'recipient-v2'
        with recipient_file.open('wb') as output:
            subprocess.run([str(self.tools / 'usr/bin/age-keygen'), '-y', str(self.wrong_identity)],
                stdout=output, stderr=subprocess.DEVNULL, check=True)
        recipient_file.chmod(0o600)
        self.online_resolver.grants[(new_recipient.key_ref, new_recipient.purpose, self.online.service_identity)] = recipient_file
        new = self.online.create('snapshot/new-recipient', new_recipient, self.online_context)
        self.assertNotIsInstance(new, ProtectionError)
        inventory = self.online.key_inventory(self.online_context, BASELINE_LIMITS)
        self.assertEqual(inventory['recipient_refs'], [self.public_ref.key_ref, new_recipient.key_ref])
        self.assertFalse(inventory['retirement_allowed'])
        old_identity = (self.private_ref.key_ref, self.private_ref.purpose, self.offline.service_identity)
        self.offline_resolver.grants[old_identity] = self.wrong_identity
        self.assert_no_restore(self.offline.restore(old, self.offline_context))
        self.offline_resolver.grants[old_identity] = self.identity
        self.assertIsInstance(self.offline.restore(old, self.offline_context), AuditReceipt)
        self.assertTrue((self.work / (new.object_ref.split('/')[1] + '.age')).exists())

    def test_new_recipient_bundle_rejects_old_identity_then_restores_with_explicit_new_reference(self):
        recipient = replace(self.public_ref, key_ref='backup-recipient/v2', version='v2')
        identity = replace(self.private_ref, key_ref='backup-identity/v2', version='v2')
        path = self.work / 'recipient-v2'
        with path.open('wb') as output:
            subprocess.run([str(self.tools / 'usr/bin/age-keygen'), '-y', str(self.wrong_identity)],
                stdout=output, stderr=subprocess.DEVNULL, check=True)
        path.chmod(0o600)
        self.online_resolver.grants[(recipient.key_ref, recipient.purpose, self.online.service_identity)] = path
        backup = self.online.create('snapshot/new-recipient', recipient, self.online_context)
        self.assertNotIsInstance(backup, ProtectionError)
        self.assert_no_restore(self.offline.restore(backup, self.offline_context))
        self.offline_resolver.grants[(identity.key_ref, identity.purpose, self.offline.service_identity)] = self.wrong_identity
        self.offline.identity_ref = identity
        self.assertIsInstance(self.offline.restore(backup, self.offline_context), AuditReceipt)
        self.assertEqual(self.journal.read(self.offline_context)['state'], 'closed')
