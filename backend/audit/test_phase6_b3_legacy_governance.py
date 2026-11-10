"""Real-PG/age governance cases with a synthetic source-bound recovery receipt.

The receipt injection tests governance only; it is not a complete recovery or
RPO/RTO measurement. Run this class only in the independent isolated test session.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.db.models import Q
from django.test import TransactionTestCase

from ctf_backend.security_bootstrap import assemble_legacy_archives
from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, KeyPurpose, KeyStatus, ProtectionError, ReasonCode,
)
from legal.models import DataProcessingActivity
from users.models import CTFUser
from .models import AuditEvent, AuditLedgerEntry, AuditLedgerLock, AuthenticatedAuditEntry, SecurityAuditRecord
from .services import AuditLedgerService
from .test_phase6_legacy_archive import LegacyArchiveFixture


class LegacySourceGovernanceTests(LegacyArchiveFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.private_ref = replace(self.public_ref, key_ref='backup-identity/v1', purpose=KeyPurpose.BACKUP_PRIVATE,
            status=KeyStatus.READ_ONLY)
        private_path = self.config_path.parent / 'b3-archive-private.key'
        private_path.write_bytes(next(line for line in self.identity.read_bytes().splitlines()
            if line.startswith(b'AGE-SECRET-KEY-')) + b'\n')
        private_path.chmod(0o600)
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_text())
        manifest['entries'].append({'reference': self.private_ref.to_wire(), 'file': private_path.name,
            'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))
        self.permissions = {name: Permission.objects.get(content_type__app_label='audit', codename=name) for name in (
            'archive_auditledgerentry', 'delete_auditledgerentry', 'delete_securityauditrecord')}
        self.teacher.user_permissions.add(*self.permissions.values())
        self.owner = assemble_legacy_archives(config_path=self.config_path, directory=self.archive_root,
            age=self.age, recipient=self.public_ref, identity=self.private_ref)
        self.flow = self.owner.verify_content.__self__
        self.covered = {}
        self.flow.verify_recovery = self.trusted_recovery
        self.flow.checkpoint = self.flow.audit.sink.checkpoint
        self.owner.govern = self.flow.govern

    def trusted_recovery(self, principal):
        covered = self.covered.get(principal.source_ref)
        if covered is None or (principal.source_hash, principal.actor_ref) != covered[:2]:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.SOURCE_NOT_APPROVED,
                retryable=False, trace_id='b3/synthetic-recovery')
        return covered[2]

    def capture(self):
        result = self.owner.run(user=self.teacher, operation='capture', expected_count=2,
            expected_tail=self.tail.current_hash)
        self.assertNotIsInstance(result, ProtectionError)
        return result[0]

    def cover(self, stored):
        _, bridge, _ = self.flow.archives.load(stored.object_ref, self.context)
        result = self.flow.archives.verify_content(stored, bridge, self.private_ref, self.context, with_source=True)
        self.assertNotIsInstance(result, ProtectionError)
        source = result[1]
        receipt = AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id='recovery-verify/' + uuid4().hex,
            durability=Durability.DURABLE, stored_at=self.flow.clock(), chain_version=None,
            entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
        self.covered['audit/legacy-v1'] = source['content_hash'], 'user/' + str(self.teacher.pk), receipt
        return source

    def govern(self, stored, operation, *, user=None):
        return self.owner.run(user=user or self.teacher, operation=operation, archive_ref=stored.object_ref)

    def sources(self):
        return (list(AuditLedgerEntry._base_manager.order_by('id').values()),
            list(SecurityAuditRecord._base_manager.filter(Q(ledger_entry__isnull=False) |
                Q(event__schema_version='ds.security-event.v1')).order_by('id').values()))

    def test_quarantine_preserves_raw_payload_and_time_but_closes_online_v1(self):
        AuditLedgerEntry.objects.filter(pk=self.first.pk).update(created_at=self.first.created_at.replace(year=2020))
        old = SecurityAuditRecord.objects.get(event_id='legacy/archive-source')
        SecurityAuditRecord.objects.filter(pk=old.pk).update(event={**old.event, 'historical_unverified': self.secret})
        before = self.sources()
        stored = self.capture()
        source = self.cover(stored)
        result = self.govern(stored, 'quarantine')
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result[0], stored)
        self.assertEqual(result[1].chain_version, 'ds.audit.v2')
        self.assertEqual(self.sources(), before)
        self.assertFalse(AuditLedgerEntry.objects.exists())
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id='legacy/archive-source').exists())
        self.assertEqual(SecurityAuditRecord._base_manager.get(pk=old.pk).event['historical_unverified'], self.secret)
        metadata = AuditLedgerLock.objects.get(key='default').legacy_archive
        self.assertEqual(metadata['state'], 'quarantined')
        self.assertEqual(metadata['source'], source)
        self.assertEqual(metadata['operations']['quarantine']['recovery']['durability'], 'durable')
        lines = self.decrypt(stored)
        self.assertFalse(lines[0]['legacy_timestamps_authenticated'])
        self.assertFalse(lines[0]['security_records_authenticated'])
        self.assertEqual(lines[1]['row']['created_at'][:4], '2020')
        verification = AuditLedgerService.verify_chain()
        self.assertFalse(verification.is_valid)
        self.assertEqual(verification.errors[0].actual, 'quarantined')
        with self.assertRaises(ContractViolation):
            AuditLedgerService._append_entry(event_category='synthetic-denied', payload={}, chain_version='v1')

    def test_explicit_delete_retains_archive_v2_evidence_and_never_creates_empty_genesis(self):
        stored = self.capture()
        self.cover(stored)
        self.assertNotIsInstance(self.govern(stored, 'quarantine'), ProtectionError)
        retained_audit_ids = set(AuditEvent.objects.values_list('pk', flat=True))
        archive_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.archive_root.iterdir()}
        result = self.govern(stored, 'delete')
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(self.sources(), ([], []))
        self.assertTrue(retained_audit_ids <= set(AuditEvent.objects.values_list('pk', flat=True)))
        self.assertEqual({path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.archive_root.iterdir()}, archive_hashes)
        metadata = AuditLedgerLock.objects.get(key='default').legacy_archive
        self.assertEqual(metadata['state'], 'deleted')
        self.assertEqual(set(metadata['operations']), {'quarantine', 'delete'})
        verification = AuditLedgerService.verify_chain()
        self.assertFalse(verification.is_valid)
        self.assertEqual(verification.errors[0].actual, 'deleted')
        before = list(AuthenticatedAuditEntry.objects.order_by('pk').values())
        self.assertEqual(self.govern(stored, 'delete'), result)
        self.assertEqual(list(AuthenticatedAuditEntry.objects.order_by('pk').values()), before)
        self.assertIsInstance(self.flow.audit.sink.verify('ds.audit.v2'), AuditReceipt)

    def test_no_recovery_boolean_or_unquarantined_delete_leaves_source_unchanged(self):
        stored = self.capture()
        before = self.sources()
        self.assertEqual(self.govern(stored, 'quarantine').code, ReasonCode.SOURCE_NOT_APPROVED)
        with patch.object(self.flow, 'verify_recovery', return_value=True):
            self.assertEqual(self.govern(stored, 'quarantine').code, ReasonCode.SOURCE_NOT_APPROVED)
        self.cover(stored)
        self.assertEqual(self.govern(stored, 'delete').code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.sources(), before)
        self.assertEqual(AuditLedgerLock.objects.get(key='default').legacy_archive, {})

    def test_changed_unbound_timestamp_prevents_quarantine(self):
        stored = self.capture()
        self.cover(stored)
        AuditLedgerEntry.objects.filter(pk=self.first.pk).update(created_at=self.first.created_at.replace(year=2020))
        before = self.sources()
        self.assertTrue(AuditLedgerService.verify_chain().is_valid)  # v1 never authenticated this timestamp.
        self.assertEqual(self.govern(stored, 'quarantine').code, ReasonCode.REPORT_MISMATCH)
        self.assertEqual(self.sources(), before)
        self.assertEqual(AuditLedgerLock.objects.get(key='default').legacy_archive, {})

    def test_current_delete_permissions_and_active_user_are_rechecked(self):
        stored = self.capture()
        self.cover(stored)
        self.assertNotIsInstance(self.govern(stored, 'quarantine'), ProtectionError)
        cached = CTFUser.objects.get(pk=self.teacher.pk)
        self.assertTrue(cached.has_perm('audit.delete_securityauditrecord'))
        before = self.sources()
        self.teacher.user_permissions.remove(self.permissions['delete_securityauditrecord'])
        with patch.object(self.flow.archives, 'load') as load:
            self.assertEqual(self.govern(stored, 'delete', user=cached).code, ReasonCode.AUTHORIZATION_DENIED)
            self.teacher.user_permissions.add(self.permissions['delete_securityauditrecord'])
            CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
            self.assertEqual(self.govern(stored, 'delete', user=cached).code, ReasonCode.AUTHORIZATION_DENIED)
            load.assert_not_called()
        self.assertEqual(self.sources(), before)
        self.assertEqual(AuditLedgerLock.objects.get(key='default').legacy_archive['state'], 'quarantined')

    def test_legal_fk_rejects_delete_without_set_null_or_partial_source_removal(self):
        activity = DataProcessingActivity.objects.create(name='合成处理记录', processing_type='store',
            purpose='合成关联保留', ledger_entry=self.first, created_by=self.teacher)
        stored = self.capture()
        self.cover(stored)
        self.assertNotIsInstance(self.govern(stored, 'quarantine'), ProtectionError)
        before = self.sources()
        metadata = AuditLedgerLock.objects.get(key='default').legacy_archive
        entries = list(AuthenticatedAuditEntry.objects.order_by('pk').values())
        self.assertEqual(self.govern(stored, 'delete').code, ReasonCode.DELIVERY_UNKNOWN)
        activity.refresh_from_db()
        self.assertEqual(activity.ledger_entry_id, self.first.pk)
        self.assertEqual(self.sources(), before)
        self.assertEqual(AuditLedgerLock.objects.get(key='default').legacy_archive, metadata)
        self.assertEqual(list(AuthenticatedAuditEntry.objects.order_by('pk').values()), entries)

    def test_missing_checkpoint_or_damaged_archive_never_mutates_source(self):
        stored = self.capture()
        self.cover(stored)
        before = self.sources()
        with patch.object(self.flow, 'checkpoint', return_value=ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='b3/synthetic-checkpoint')):
            self.assertEqual(self.govern(stored, 'quarantine').code, ReasonCode.AUDIT_UNAVAILABLE)
        path = self.archive_root / (stored.object_ref.split('/')[-1] + '.legacy.age')
        path.write_bytes(path.read_bytes()[:-1])
        self.assertEqual(self.govern(stored, 'quarantine').code, ReasonCode.CIPHERTEXT_INVALID)
        self.assertEqual(self.sources(), before)
        self.assertEqual(AuditLedgerLock.objects.get(key='default').legacy_archive, {})
