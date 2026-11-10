"""Real PG audit metadata and mock restore orchestration; neither is a pg_restore result."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from django.db import connection, transaction
from django.test import SimpleTestCase, TransactionTestCase

from audit.models import AuditEvent, AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend import security_bootstrap as bootstrap
from data_security.adapters.persistence.recovery_state import RecoveryJournal, recovery_admission
from data_security.application.backup_recovery import RecoveryFlow
from data_security.contracts import (
    AuditCheckpoint, AuditReceipt, BASELINE_LIMITS, Durability, Environment, EventKind, FrozenJSON,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, SecurityEventV2, StoredObject, content_hash,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase3_fixtures import configuration


class LifecycleAuditRecoveryTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        path, config, _, _, _ = self.enterContext(configuration(providers=()))
        self.checkpoints = path.parent / 'lifecycle-checkpoints'
        self.checkpoints.mkdir(mode=0o700)
        config.update(schema_version='ds.bootstrap.v2', policy_repository={'kind': 'file', 'writable': False},
            audit_chain={'chain_version': 'ds.audit.v2', 'project_ref': 'ctf',
                'object_uuid': '00000000-0000-4000-8000-000000000071', 'object_version': 'v1',
                'authorization_ref': 'authorization/lifecycle-fixture', 'retained_keys': [],
                'checkpoint_root': str(self.checkpoints), 'checkpoint_ref': None})
        path.write_text(json.dumps(config))
        self.components = bootstrap.assemble(config_path=path)
        self.sink = self.components['audit'].sink
        self.now = self.components['clock']()
        self.sink.clock = lambda: self.now
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security',
            environment=Environment.EVALUATION, domain='ctf', purpose=Purpose.STORAGE,
            authorization_ref='authorization/lifecycle-fixture')
        root = path.parent / 'lifecycle-restore-target'
        root.mkdir(mode=0o700)
        self.journal = RecoveryJournal(root=root, target_identity=content_hash({'fixture': 'lifecycle'}),
            code_version='lifecycle-fixture-v1', environment=Environment.EVALUATION, domain='ctf',
            service_identity='service/security', clock=lambda: self.now, limits=BASELINE_LIMITS)
        self.journal.start(self.context)
        self.first = self.emit('event/lifecycle-before')

    def emit(self, event_id):
        self.now += timedelta(seconds=1)
        event = replace(examples()[SecurityEventV2], event_id=event_id, kind=EventKind.AUTHORIZATION,
            actor_ref='service/security', object_ref='lifecycle/fixture', occurred_at=self.now,
            policy_binding=self.components['binding'], algorithm_versions=('lifecycle-fixture.v1',),
            key_versions=(self.sink.key.key_ref,), correlation_ref='lifecycle/fixture')
        receipt = self.components['audit'].record(event, Durability.LEDGER_CONFIRMED)
        self.assertIsInstance(receipt, AuditReceipt)
        return receipt

    def capture(self):
        bundle = self.sink.capture_recovery(BASELINE_LIMITS)
        self.assertIsInstance(bundle, FrozenJSON)
        return bundle

    def restored_fixture(self):
        # Only the original journal's stage is staged here, not a backup or restore invocation.
        state = self.journal.read(self.context)
        state['state'] = 'restored'
        self.journal.save(state, self.context)

    def rewind_fixture(self, sequence):
        # Remove only this test's synthetic suffix to model a database restored to an earlier point.
        rows = list(AuthenticatedAuditEntry.objects.filter(chain_identity=self.sink.chain_identity,
            sequence__gt=sequence).values_list('pk', 'record_id', 'record__audit_event_id'))
        AuthenticatedAuditEntry.objects.filter(pk__in=[row[0] for row in rows]).delete()
        SecurityAuditRecord.objects.filter(pk__in=[row[1] for row in rows]).delete()
        AuditEvent.objects.filter(pk__in=[row[2] for row in rows]).delete()

    def test_selected_checkpoint_cannot_be_replaced_by_an_older_mirror(self):
        older = self.capture()
        second = self.emit('event/lifecycle-second')
        newer = self.capture()
        self.sink.checkpoint_ref = newer.to_value()['checkpoint_ref']
        self.rewind_fixture(self.first.sequence)
        self.restored_fixture()
        result = self.sink.restore_recovery(older, BASELINE_LIMITS, self.context, journal=self.journal)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(self.sink.checkpoint_ref, newer.to_value()['checkpoint_ref'])
        result = self.sink.restore_recovery(newer, BASELINE_LIMITS, self.context, journal=self.journal)
        self.assertEqual(result, replace(second, checkpoint_ref=self.sink.checkpoint_ref))
        self.assertEqual(self.sink.verify('ds.audit.v2'), result)

    def test_capture_contains_only_bounded_authenticated_metadata(self):
        self.emit('event/lifecycle-after')
        document = self.capture().to_value()
        self.assertEqual(set(document), {'schema_version', 'checkpoint_ref', 'chain_identity',
                                        'entries', 'key', 'authentication'})
        self.assertEqual(len(document['entries']), 2)
        self.assertEqual(document['entries'][0]['entry_id'], int(self.first.entry_ref.rsplit('/', 1)[1]))
        self.assertEqual(document['entries'][0]['current_hash'], self.first.entry_hash)
        self.assertEqual(document['entries'][0]['event']['event_id'], self.first.event_id)
        self.assertEqual(len(bytes.fromhex(document['authentication'])), 32)
        checkpoint = self.checkpoints / (document['checkpoint_ref'].rsplit('/', 1)[1] + '.json')
        self.assertEqual(checkpoint.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('fixture body', json.dumps(document))
        self.assertNotIn('ciphertext_and_tag', json.dumps(document))

    def test_missing_suffix_preserves_receipts_and_is_idempotent(self):
        second = self.emit('event/lifecycle-second')
        third = self.emit('event/lifecycle-third')
        bundle = self.capture()
        checkpoint = self.checkpoints / (bundle.to_value()['checkpoint_ref'].rsplit('/', 1)[1] + '.json')
        original_checkpoint = checkpoint.read_bytes()
        self.rewind_fixture(self.first.sequence)
        self.restored_fixture()
        result = self.sink.restore_recovery(bundle, BASELINE_LIMITS, self.context, journal=self.journal)
        self.assertEqual(result, replace(third, checkpoint_ref=bundle.to_value()['checkpoint_ref']))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
        for receipt in (self.first, second, third):
            entry = AuthenticatedAuditEntry.objects.select_related('record').get(
                pk=int(receipt.entry_ref.rsplit('/', 1)[1]))
            self.assertEqual(self.sink._receipt_v2(entry), receipt)
            self.assertEqual(self.sink.read_authenticated(receipt.event_id).event_id, receipt.event_id)
        self.assertEqual(self.sink.restore_recovery(bundle, BASELINE_LIMITS, self.context,
                                                   journal=self.journal), result)
        self.assertEqual(SecurityAuditRecord.objects.count(), 3)
        self.assertEqual(checkpoint.read_bytes(), original_checkpoint)
        later = self.emit('event/lifecycle-later')
        self.assertEqual(later.sequence, third.sequence + 1)
        self.assertGreater(int(later.entry_ref.rsplit('/', 1)[1]), int(third.entry_ref.rsplit('/', 1)[1]))
        self.assertEqual(self.sink.verify('ds.audit.v2'), later)
        self.assertEqual(self.journal.read(self.context)['state'], 'restored')
        self.assertIsInstance(recovery_admission(self.journal.root, self.journal.target_identity,
                                                limits=BASELINE_LIMITS), ProtectionError)

    def test_modified_mirror_including_unsigned_entry_ids_is_denied(self):
        self.emit('event/lifecycle-second')
        bundle = self.capture()
        self.rewind_fixture(self.first.sequence)
        self.restored_fixture()
        for field in ('entry_id', 'event', 'sequence', 'checkpoint_ref', 'chain_identity', 'extra'):
            with self.subTest(field=field):
                document = bundle.to_value()
                if field == 'entry_id':
                    document['entries'][0]['entry_id'] += 100
                elif field == 'event':
                    document['entries'][0]['event']['object_ref'] = 'object/changed'
                elif field == 'sequence':
                    document['entries'][0]['sequence'] += 1
                elif field == 'checkpoint_ref':
                    document[field] = 'audit/checkpoint/' + '0' * 64
                elif field == 'chain_identity':
                    document[field] = '0' * 64
                else:
                    document[field] = True
                result = self.sink.restore_recovery(FrozenJSON(document), BASELINE_LIMITS,
                                                    self.context, journal=self.journal)
                self.assertIsInstance(result, ProtectionError)
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
                self.assertEqual(SecurityAuditRecord.objects.count(), 1)

    def test_valid_mirror_mac_does_not_replace_original_entry_authentication(self):
        self.emit('event/lifecycle-second')
        document = self.capture().to_value()
        self.rewind_fixture(self.first.sequence)
        self.restored_fixture()
        document.pop('authentication')
        document['entries'][1]['event']['object_ref'] = 'object/changed'
        encoded = json.dumps(document, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
        document['authentication'] = self.sink.crypto.authenticate(encoded,
            replace(self.sink.context, field_ref='audit/recovery.v1'), self.sink.key).hex()
        result = self.sink.restore_recovery(FrozenJSON(document), BASELINE_LIMITS,
                                            self.context, journal=self.journal)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)

    def test_newer_or_different_target_is_not_overwritten(self):
        bundle = self.capture()
        self.emit('event/lifecycle-second')
        self.restored_fixture()
        result = self.sink.restore_recovery(bundle, BASELINE_LIMITS, self.context, journal=self.journal)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.rewind_fixture(self.first.sequence)
        SecurityAuditRecord.objects.filter(event_id=self.first.event_id).update(
            stored_at=self.first.stored_at + timedelta(seconds=1))
        result = self.sink.restore_recovery(bundle, BASELINE_LIMITS, self.context, journal=self.journal)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(SecurityAuditRecord.objects.get(event_id=self.first.event_id).stored_at,
                         self.first.stored_at + timedelta(seconds=1))

    def test_only_restored_original_journal_and_no_outer_transaction(self):
        bundle = self.capture()
        for stage in ('closed', 'restoring', 'verified', 'opened'):
            with self.subTest(stage=stage):
                state = self.journal.read(self.context)
                state['state'] = stage
                self.journal.save(state, self.context)
                result = self.sink.restore_recovery(bundle, BASELINE_LIMITS, self.context, journal=self.journal)
                self.assertIsInstance(result, ProtectionError)
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.restored_fixture()
        wrong_actor = replace(self.context, actor_ref='actor/unapproved')
        denied = self.sink.restore_recovery(bundle, BASELINE_LIMITS, wrong_actor, journal=self.journal)
        self.assertEqual(denied.code, ReasonCode.AUTHORIZATION_DENIED)
        with transaction.atomic():
            self.assertIsInstance(self.sink.capture_recovery(BASELINE_LIMITS), ProtectionError)
            self.assertIsInstance(self.sink.restore_recovery(bundle, BASELINE_LIMITS,
                self.context, journal=self.journal), ProtectionError)

    def test_original_checkpoint_is_required_and_never_recreated(self):
        self.emit('event/lifecycle-second')
        bundle = self.capture()
        checkpoint = self.checkpoints / (bundle.to_value()['checkpoint_ref'].rsplit('/', 1)[1] + '.json')
        self.assertEqual(checkpoint.stat().st_mode & 0o777, 0o600)
        checkpoint.unlink()
        self.rewind_fixture(self.first.sequence)
        self.restored_fixture()
        result = self.sink.restore_recovery(bundle, BASELINE_LIMITS, self.context, journal=self.journal)
        self.assertIsInstance(result, ProtectionError)
        self.assertFalse(checkpoint.exists())
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_bounds_fail_before_target_mutation(self):
        self.emit('event/lifecycle-second')
        limited = replace(BASELINE_LIMITS, max_actions=1)
        result = self.sink.capture_recovery(limited)
        self.assertEqual(result.code, ReasonCode.LIMIT_EXCEEDED)
        self.assertEqual(list(self.checkpoints.iterdir()), [])
        bundle = self.capture()
        self.rewind_fixture(self.first.sequence)
        self.restored_fixture()
        result = self.sink.restore_recovery(bundle, limited, self.context, journal=self.journal)
        self.assertEqual(result.code, ReasonCode.LIMIT_EXCEEDED)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)


class LifecycleRecoveryFlowTests(SimpleTestCase):
    """Original flow and real journal, with mock backup/owner ports; no database restore."""
    def setUp(self):
        self.now = datetime(2026, 11, 10, tzinfo=timezone.utc)
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security',
            environment=Environment.EVALUATION, domain='ctf', purpose=Purpose.STORAGE)
        root = Path(self.enterContext(TemporaryDirectory()))
        root.chmod(0o700)
        self.journal = RecoveryJournal(root=root, target_identity=content_hash({'fixture': 'replay-flow'}),
            code_version='replay-flow-v1', environment=Environment.EVALUATION, domain='ctf',
            service_identity='service/security', clock=lambda: self.now, limits=BASELINE_LIMITS)
        self.initial = {
            'schema': {'table/public/fixture': {'records': 1, 'sha256': content_hash({'rows': 'before'})}},
            'private_files': {'records': 1, 'sha256': content_hash({'files': 'before'})},
            'pending_files': {'records': 0, 'sha256': content_hash({'pending': 'none'})},
        }
        self.governed = {
            'schema': {'table/public/fixture': {'records': 2, 'sha256': content_hash({'rows': 'after'})}},
            'private_files': {'records': 0, 'sha256': content_hash({'files': 'after'})},
            'pending_files': self.initial['pending_files'],
        }
        self.backup = replace(examples()[StoredObject], object_ref='backup/' + '7' * 32,
                              version='v2', state='verified')
        self.backups = Mock()
        self.backups.restore.return_value = examples()[AuditReceipt]
        self.backups.read_restoration.return_value = {
            'backup_ref': self.backup.object_ref, 'ciphertext_hash': self.backup.ciphertext_hash,
            'private_files': self.initial['private_files'], 'full_inventory': {
                'schema': self.initial['schema'], 'pending_files': self.initial['pending_files'],
                'snapshot_at': (self.now - timedelta(hours=1)).isoformat()},
        }
        self.backups.source_inventory.return_value = self.initial
        self.calls = []
        self.replay_receipt = examples()[AuditCheckpoint].receipt

        def replay(context):
            self.calls.append('replay')
            self.backups.source_inventory.return_value = self.governed
            return self.replay_receipt

        def verify(context):
            self.calls.append('owners')
            return {'complete': True, 'opening_allowed': True}

        self.replay, self.verifier = Mock(side_effect=replay), Mock(side_effect=verify)
        self.flow = RecoveryFlow(backups=self.backups, journal=self.journal, verify_owners=self.verifier,
                                 clock=lambda: self.now, replay_governance=self.replay)
        self.run_ref = self.flow.run('close', self.context)
        self.assertIsInstance(self.run_ref, str)
        self.assertIsInstance(self.flow.run('restore', self.context, backup=self.backup), AuditReceipt)

    def test_replay_between_original_inventory_and_owner_verification(self):
        self.assertIsInstance(self.flow.run('verify', self.context), AuditReceipt)
        self.assertEqual(self.calls, ['replay', 'owners'])
        state = self.journal.read(self.context)
        self.assertEqual(state['governance'], {'state': 'applied', 'receipt': self.replay_receipt.to_wire(),
                                               'inventory': self.governed})
        self.assertEqual(state['restoration']['full_inventory']['schema'], self.initial['schema'])
        self.assertIsInstance(self.flow.run('open', self.context, approved_run_ref=self.run_ref), AuditReceipt)
        self.assertEqual(self.calls, ['replay', 'owners', 'owners'])
        self.replay.assert_called_once_with(self.context)
        self.assertIs(recovery_admission(self.journal.root, self.journal.target_identity,
                                         limits=BASELINE_LIMITS), True)
        self.assertEqual(self.journal.read(self.context)['metrics']['rpo_seconds'], 3600)

    def test_original_inventory_mismatch_blocks_replay(self):
        self.backups.source_inventory.return_value = {**self.initial, 'schema': {}}
        result = self.flow.run('verify', self.context)
        self.assertEqual(result.code, ReasonCode.REPORT_MISMATCH)
        self.replay.assert_not_called()
        self.verifier.assert_not_called()
        self.assertNotIn('governance', self.journal.read(self.context))

    def test_partial_replay_cannot_be_retried_as_an_approved_inventory(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.DELIVERY_UNKNOWN, retryable=False, trace_id='lifecycle/partial')

        def partial(context):
            self.backups.source_inventory.return_value = self.governed
            return failure

        self.replay.side_effect = partial
        self.assertEqual(self.flow.run('verify', self.context), failure)
        self.assertEqual(self.journal.read(self.context)['governance'], {'state': 'applying'})
        self.assertEqual(self.flow.run('verify', self.context).code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertIsInstance(self.flow.run('open', self.context, approved_run_ref=self.run_ref), ProtectionError)
        self.replay.assert_called_once_with(self.context)
        self.verifier.assert_not_called()
        self.assertIsInstance(recovery_admission(self.journal.root, self.journal.target_identity,
                                                limits=BASELINE_LIMITS), ProtectionError)

    def test_owner_failure_does_not_record_a_new_inventory(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.SOURCE_NOT_APPROVED, retryable=False, trace_id='lifecycle/owners')
        self.verifier.side_effect = None
        self.verifier.return_value = failure
        self.assertEqual(self.flow.run('verify', self.context), failure)
        self.assertEqual(self.journal.read(self.context)['governance'], {'state': 'applying'})
        self.assertEqual(self.backups.source_inventory.call_count, 1)
        self.assertEqual(self.flow.run('verify', self.context).code, ReasonCode.SOURCE_NOT_APPROVED)
        self.replay.assert_called_once_with(self.context)

    def test_post_governance_drift_is_still_rejected_at_open(self):
        self.assertIsInstance(self.flow.run('verify', self.context), AuditReceipt)
        self.backups.source_inventory.return_value = {**self.governed,
            'pending_files': {'records': 1, 'sha256': content_hash({'pending': 'unexpected'})}}
        result = self.flow.run('open', self.context, approved_run_ref=self.run_ref)
        self.assertEqual(result.code, ReasonCode.REPORT_MISMATCH)
        self.assertEqual(self.journal.read(self.context)['state'], 'verified')
        self.assertEqual(self.calls, ['replay', 'owners'])

    def test_governed_recovery_cannot_drop_the_replay_capability(self):
        self.assertIsInstance(self.flow.run('verify', self.context), AuditReceipt)
        downgraded = RecoveryFlow(backups=self.backups, journal=self.journal, verify_owners=self.verifier,
                                  clock=lambda: self.now)
        result = downgraded.run('open', self.context, approved_run_ref=self.run_ref)
        self.assertEqual(result.code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.journal.read(self.context)['state'], 'verified')

    def test_admission_rejects_partial_or_unconfirmed_governance(self):
        self.assertIsInstance(self.flow.run('verify', self.context), AuditReceipt)
        self.assertIsInstance(self.flow.run('open', self.context, approved_run_ref=self.run_ref), AuditReceipt)
        state = self.journal.read(self.context)
        for governance in ({'state': 'applying'}, {'state': 'applied', 'inventory': self.governed,
                            'receipt': examples()[AuditReceipt].to_wire()}):
            with self.subTest(governance_state=governance['state']):
                state['governance'] = governance
                self.journal.save(state, self.context)
                self.assertIsInstance(recovery_admission(self.journal.root, self.journal.target_identity,
                                                        limits=BASELINE_LIMITS), ProtectionError)

    def test_unbound_legacy_flow_keeps_the_original_inventory_rule(self):
        legacy = RecoveryFlow(backups=self.backups, journal=self.journal, verify_owners=self.verifier,
                              clock=lambda: self.now)
        self.assertIsInstance(legacy.run('verify', self.context), AuditReceipt)
        self.assertIsInstance(legacy.run('open', self.context, approved_run_ref=self.run_ref), AuditReceipt)
        self.replay.assert_not_called()
        self.assertNotIn('governance', self.journal.read(self.context))
        self.assertIs(recovery_admission(self.journal.root, self.journal.target_identity,
                                         limits=BASELINE_LIMITS), True)
