"""Local journal and pure orchestration tests, not PostgreSQL/age recovery measurements."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

from data_security.adapters.persistence.recovery_state import (
    RecoveryJournal, VerifiedRecoveryPoint, recovery_admission,
)
from data_security.application.backup_recovery import BackupCycle, RecoveryFlow
from data_security.contracts import (
    AuditReceipt, BASELINE_LIMITS, Durability, Environment, KeyPurpose, KeyReference, KeyStatus,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, StoredObject,
)
from data_security.contracts.ports import BackupRetentionRecord
from data_security.tests.fixtures import examples


class RecoveryStateTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='ds-b3-journal-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.now = datetime(2026, 11, 8, tzinfo=timezone.utc)
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security',
            domain='ctf', purpose=Purpose.STORAGE)
        self.journal = RecoveryJournal(root=self.root, target_identity='1' * 64, code_version='b3-test',
            environment=Environment.TEST, domain='ctf', service_identity='service/security',
            clock=lambda: self.now, limits=BASELINE_LIMITS)
        self.backup = StoredObject(schema_version=StoredObject.SCHEMA, object_ref='backup/' + 'a' * 32,
            version='v2', ciphertext_hash='2' * 64, size_bytes=100, state='verified')
        self.source_ref, self.source_hash = 'resource-legacy/12/' + 'b' * 32, '3' * 64
        self.manifest = {'schema': {'table/public/test': {'records': 1, 'sha256': '4' * 64}},
            'source_identity': '5' * 64, 'snapshot_at': (self.now - timedelta(hours=1)).isoformat(),
            'pending_files': {'records': 1, 'sha256': '6' * 64}}
        self.restored = {'backup_ref': self.backup.object_ref, 'ciphertext_hash': self.backup.ciphertext_hash,
            'full_inventory': self.manifest, 'private_files': {'records': 1, 'sha256': '7' * 64}}
        self.restore_receipt = AuditReceipt(schema_version=AuditReceipt.SCHEMA,
            event_id='backup-restore/' + 'c' * 32, durability=Durability.DURABLE, stored_at=self.now,
            chain_version=None, entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
        self.backups = Mock()
        self.backups.restore.return_value = self.restore_receipt
        self.backups.read_restoration.return_value = self.restored
        self.backups.source_inventory.return_value = {
            'schema': self.manifest['schema'], 'private_files': self.restored['private_files'],
            'pending_files': self.manifest['pending_files']}
        self.verifier = Mock(return_value={'complete': True, 'opening_allowed': True,
            'governance': {self.source_ref: self.source_hash}, 'unknown_objects': 1})
        self.flow = RecoveryFlow(backups=self.backups, journal=self.journal,
            verify_owners=self.verifier, clock=lambda: self.now)

    def close_restore_verify(self):
        run_ref = self.flow.run('close', self.context)
        self.now += timedelta(minutes=5)
        self.assertIs(self.flow.run('restore', self.context, backup=self.backup), self.restore_receipt)
        self.now += timedelta(minutes=10)
        receipt = self.flow.run('verify', self.context)
        self.assertIsInstance(receipt, AuditReceipt)
        self.assertEqual(self.journal.read(self.context)['state'], 'verified')
        return run_ref, receipt

    def admit(self):
        return recovery_admission(self.root, '1' * 64, limits=BASELINE_LIMITS)

    def proof(self):
        return VerifiedRecoveryPoint(**self.journal.proof(self.context), source_identity='5' * 64,
            code_version='b3-test', environment=Environment.TEST, domain='ctf', limits=BASELINE_LIMITS)

    def test_default_deployment_is_unchanged_but_close_survives_fresh_journal(self):
        self.assertIs(self.admit(), True)
        self.flow.run('close', self.context)
        self.assertEqual(self.admit().code, ReasonCode.SOURCE_NOT_APPROVED)
        another = RecoveryJournal(root=self.root, target_identity='1' * 64, code_version='b3-test',
            environment=Environment.TEST, domain='ctf', service_identity='service/security',
            clock=lambda: self.now, limits=BASELINE_LIMITS)
        self.assertEqual(another.read(self.context)['state'], 'closed')
        self.backups.restore.assert_not_called()

    def test_verified_is_not_open_and_explicit_open_covers_entire_outage(self):
        run_ref, verified = self.close_restore_verify()
        self.assertEqual(self.admit().code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.flow.run('open', self.context, approved_run_ref='recovery/wrong').code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.now += timedelta(minutes=15)
        self.assertEqual(self.flow.run('open', self.context, approved_run_ref=run_ref), verified)
        state = self.journal.read(self.context)
        self.assertEqual(state['state'], 'opened')
        self.assertEqual(state['metrics']['rpo_seconds'], 3600)
        self.assertEqual(state['metrics']['rto_seconds'], 1800)
        self.assertEqual(state['metrics']['outage_to_restore_seconds'], 300)
        self.assertEqual(state['metrics']['verification_seconds'], 600)
        self.assertEqual(state['metrics']['review_and_open_seconds'], 900)
        self.assertIs(self.admit(), True)
        self.assertEqual(self.verifier.call_count, 2)

    def test_failed_restore_preserves_closed_uncertainty_and_no_verification(self):
        self.flow.run('close', self.context)
        error = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
            retryable=False, trace_id='synthetic/restore')
        self.backups.restore.return_value = error
        self.assertIs(self.flow.run('restore', self.context, backup=self.backup), error)
        self.assertEqual(self.journal.read(self.context)['state'], 'restoring')
        self.assertEqual(self.admit().code, ReasonCode.SOURCE_NOT_APPROVED)
        self.verifier.assert_not_called()
        self.backups.read_restoration.assert_not_called()

    def test_changed_inventory_blocks_open_without_mutating_verification_proof(self):
        run_ref, _ = self.close_restore_verify()
        before = self.journal.proof(self.context)
        self.backups.source_inventory.return_value = {'schema': {}, 'private_files': {}, 'pending_files': {}}
        result = self.flow.run('open', self.context, approved_run_ref=run_ref)
        self.assertEqual(result.code, ReasonCode.REPORT_MISMATCH)
        self.assertEqual(self.journal.proof(self.context), before)
        self.assertEqual(self.admit().code, ReasonCode.SOURCE_NOT_APPROVED)

    def test_legacy_source_drill_can_prove_recovery_without_opening_unsafe_online_sources(self):
        self.verifier.return_value['opening_allowed'] = False
        run_ref, verified = self.close_restore_verify()
        principal = replace(self.context, source_ref=self.source_ref, source_version='1', source_hash=self.source_hash)
        self.assertEqual(self.proof()(principal), verified)
        self.assertEqual(self.flow.run('open', self.context, approved_run_ref=run_ref).code,
                         ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.admit().code, ReasonCode.SOURCE_NOT_APPROVED)

    def test_source_specific_proof_rejects_wrong_source_deployment_and_changed_file(self):
        self.close_restore_verify()
        proof = self.proof()
        principal = replace(self.context, source_ref=self.source_ref, source_version='1', source_hash=self.source_hash)
        self.assertIsInstance(proof(principal), AuditReceipt)
        for changed in (replace(principal, source_hash='8' * 64), replace(principal, source_ref='other/source'),
                        replace(principal, domain='other/domain')):
            self.assertIsInstance(proof(changed), ProtectionError)
        other = VerifiedRecoveryPoint(**self.journal.proof(self.context), source_identity='9' * 64,
            code_version='b3-test', environment=Environment.TEST, domain='ctf', limits=BASELINE_LIMITS)
        self.assertEqual(other(principal).code, ReasonCode.SOURCE_NOT_APPROVED)
        state = self.journal.read(self.context)
        state['verification']['governance'][self.source_ref] = '8' * 64
        self.journal.save(state, self.context)
        self.assertEqual(proof(principal).code, ReasonCode.HASH_MISMATCH)

    def test_overdue_rpo_and_rto_never_open(self):
        for delay in ('rpo', 'rto'):
            with self.subTest(delay=delay):
                # Each drill uses a new isolated root, never erases a failed target.
                with TemporaryDirectory(prefix='ds-b3-late-') as root:
                    journal = RecoveryJournal(root=Path(root), target_identity='1' * 64, code_version='b3-test',
                        environment=Environment.TEST, domain='ctf', service_identity='service/security',
                        clock=lambda: self.now, limits=BASELINE_LIMITS)
                    flow = RecoveryFlow(backups=self.backups, journal=journal, verify_owners=self.verifier,
                        clock=lambda: self.now)
                    self.manifest['snapshot_at'] = (self.now - timedelta(hours=25 if delay == 'rpo' else 1)).isoformat()
                    run_ref = flow.run('close', self.context)
                    flow.run('restore', self.context, backup=self.backup)
                    flow.run('verify', self.context)
                    if delay == 'rto':
                        self.now += timedelta(hours=5)
                    self.assertEqual(flow.run('open', self.context, approved_run_ref=run_ref).code,
                                     ReasonCode.SOURCE_NOT_APPROVED)
                    self.assertFalse(journal.read(self.context)['metrics']['passed'])
                    self.assertEqual(journal.read(self.context)['state'], 'verified')


class BackupCycleTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, tzinfo=timezone.utc)
        self.context = examples()[ProtectionContext]
        self.recipient = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='backup-recipient/v2',
            purpose=KeyPurpose.BACKUP_PUBLIC, version='v2', status=KeyStatus.ACTIVE)
        self.backup = StoredObject(schema_version=StoredObject.SCHEMA, object_ref='backup/' + 'a' * 32,
            version='v2', ciphertext_hash='1' * 64, size_bytes=10, state='verified')
        self.port = Mock(full_inventory=True)
        self.port.create.return_value = self.backup
        self.cycle = BackupCycle(backups=self.port, recipient=self.recipient, limits=BASELINE_LIMITS,
            clock=lambda: self.now, identity=lambda: 'b' * 32)

    def record(self, cadence, age):
        return BackupRetentionRecord(schema_version=BackupRetentionRecord.SCHEMA, backup=self.backup,
            created_at=self.now - age, cadence=cadence, files_hash='2' * 64, files_size=10)

    def test_empty_inventory_creates_daily_and_weekly_without_retiring_anything(self):
        self.port.retention_inventory.return_value = ()
        self.assertEqual(self.cycle.run_due(self.context), (self.backup, self.backup))
        self.assertEqual([call.kwargs['cadence'] for call in self.port.create.call_args_list], ['daily', 'weekly'])
        self.port.retention_inventory.assert_called_once_with(self.context, BASELINE_LIMITS, full_only=True)
        self.port.retire.assert_not_called()

    def test_due_is_calculated_from_each_actual_cadence(self):
        self.port.retention_inventory.return_value = (
            self.record('daily', timedelta(hours=23)), self.record('weekly', timedelta(days=7)))
        self.assertEqual(self.cycle.run_due(self.context), (self.backup,))
        self.assertEqual(self.port.create.call_args.kwargs['cadence'], 'weekly')

    def test_inventory_or_create_error_never_invents_a_successful_cycle(self):
        error = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.HASH_MISMATCH,
            retryable=False, trace_id='synthetic/backup')
        self.port.retention_inventory.return_value = error
        self.assertIs(self.cycle.run_due(self.context), error)
        self.port.create.assert_not_called()
        self.port.retention_inventory.return_value = ()
        self.port.create.return_value = error
        self.assertIs(self.cycle.run_due(self.context), error)
        self.assertEqual(self.port.create.call_count, 1)
        self.port.retire.assert_not_called()
