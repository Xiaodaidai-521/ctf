"""Fresh synthetic PG and real age; a captured archive is not source migration approval."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from django.db import close_old_connections, transaction
from django.test import TransactionTestCase

from ctf_backend.security_bootstrap import assemble
from data_security.adapters.keys import FileKeyResolver
from data_security.adapters.persistence.legacy_archive import DjangoLegacyAuditArchive
from data_security.contracts import (
    BASELINE_LIMITS, AuditReceipt, Durability, Environment, KeyPurpose, KeyReference,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, Role, SecurityEvent,
)
from data_security.tests.fixtures import examples
from resources.test_phase6_private_uploads import PrivateResourceUploadFixture
from .models import AuditLedgerEntry, SecurityAuditRecord
from .services import AuditLedgerService


class LegacyArchiveFixture(PrivateResourceUploadFixture):
    def setUp(self):
        super().setUp()
        self.archive_root = self.config_path.parent / 'archives'
        self.archive_root.mkdir(mode=0o700)
        self.age = Path('/home/hatch/workspace/data-security-seven-phases/isolated-tools/phase3-age-extracted/usr/bin/age')
        self.identity = self.config_path.parent / 'offline-archive-identity'
        subprocess.run([str(self.age.with_name('age-keygen')), '-o', str(self.identity)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        recipient = self.config_path.parent / 'archive-recipient.key'
        with recipient.open('wb') as output:
            subprocess.run([str(self.age.with_name('age-keygen')), '-y', str(self.identity)],
                           stdout=output, stderr=subprocess.DEVNULL, check=True)
        recipient.chmod(0o600)
        self.public_ref = replace(examples()[KeyReference], key_ref='backup-recipient/v1',
                                  purpose=KeyPurpose.BACKUP_PUBLIC, version='v1')
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_text())
        manifest['entries'].append({'reference': self.public_ref.to_wire(), 'file': recipient.name,
                                    'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))
        components = assemble(config_path=self.config_path)
        self.gateway = components['audit']
        self.archive = DjangoLegacyAuditArchive(directory=self.archive_root, age=self.age,
            keys=FileKeyResolver(manifest_path=manifest_path, environment=Environment.EVALUATION,
                                 repository_root=Path(__file__).resolve().parents[2]),
            service_identity='service/security', environment=Environment.EVALUATION, domain='ctf',
            policy_binding=components['binding'], limits=BASELINE_LIMITS, clock=components['clock'])
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', role=Role.SERVICE,
            purpose=Purpose.STORAGE, environment=Environment.EVALUATION, domain='ctf',
            authorization_ref='approval/synthetic-legacy-archive')
        self.secret = 'archive-student@example.invalid'
        self.first = AuditLedgerService._append_entry(event_category='synthetic-archive',
                                                      payload={'synthetic': self.secret}, chain_version='v1')
        old_event = replace(examples()[SecurityEvent], event_id='legacy/archive-source')
        self.assertIsInstance(self.gateway.record(old_event, Durability.LEDGER_CONFIRMED), AuditReceipt)
        self.tail = AuditLedgerEntry.objects.order_by('-id').first()

    def create(self, **changes):
        return self.archive.create(**{**dict(expected_count=2, expected_tail=self.tail.current_hash,
            recipient=self.public_ref, context=self.context), **changes})

    def decrypt(self, stored):
        path = self.archive_root / (stored.object_ref.split('/')[-1] + '.legacy.age')
        result = subprocess.run([str(self.age), '--decrypt', '--identity', str(self.identity), str(path)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
        return [json.loads(line) for line in result.stdout.splitlines()]


class LegacyArchiveTests(LegacyArchiveFixture, TransactionTestCase):
    def test_real_encrypted_archive_preserves_source_and_bridges_via_only_gateway(self):
        before = list(AuditLedgerEntry.objects.values())
        stored, event = self.create()
        lines = self.decrypt(stored)
        self.assertEqual(lines[0]['chain_length'], 2)
        self.assertEqual(lines[0]['tail_hash'], self.tail.current_hash)
        self.assertFalse(lines[0]['legacy_timestamps_authenticated'])
        self.assertFalse(lines[0]['security_records_authenticated'])
        self.assertEqual([line['kind'] for line in lines[1:]], ['ledger', 'ledger', 'security-record'])
        self.assertEqual(lines[1]['row']['payload'], {'synthetic': self.secret})
        self.assertEqual(list(AuditLedgerEntry.objects.values()), before)
        for path in self.archive_root.iterdir():
            self.assertNotIn(self.secret.encode(), path.read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        receipt = self.gateway.record(event, Durability.LEDGER_CONFIRMED)
        self.assertIsInstance(receipt, AuditReceipt)
        self.assertEqual(receipt.chain_version, 'ds.audit.v2')
        self.assertEqual(dict(event.evidence_hashes), {'archive': stored.ciphertext_hash, 'report': self.tail.current_hash})
        self.assertEqual(dict(event.counts)['records'], 2)
        self.assertEqual(self.gateway.record(event, Durability.LEDGER_CONFIRMED), receipt)
        self.assertIsInstance(self.gateway.sink.verify('ds.audit.v2'), AuditReceipt)
        self.assertTrue(AuditLedgerService.verify_chain().is_valid)

    def test_tampered_old_chain_or_changed_approved_tail_is_not_archived(self):
        self.assertEqual(self.create(expected_count=1).code, ReasonCode.REPORT_MISMATCH)
        self.assertEqual(self.create(expected_tail='0' * 64).code, ReasonCode.REPORT_MISMATCH)
        AuditLedgerEntry.objects.filter(pk=self.first.pk).update(payload={'tampered': True})
        self.assertEqual(self.create().code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertFalse(list(self.archive_root.iterdir()))

    def test_uncommitted_or_wrong_service_context_cannot_capture(self):
        with transaction.atomic():
            self.assertEqual(self.create().code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(self.create(context=replace(self.context, actor_ref='service/other')).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(list(self.archive_root.iterdir()))

    def test_limits_bound_row_count_and_serialized_row_before_capture(self):
        self.archive.limits = replace(BASELINE_LIMITS, max_actions=1)
        self.assertEqual(self.create(expected_count=1).code, ReasonCode.LIMIT_EXCEEDED)
        self.archive.limits = replace(BASELINE_LIMITS, max_json_bytes=100)
        self.assertEqual(self.create().code, ReasonCode.LIMIT_EXCEEDED)
        self.assertFalse(list(self.archive_root.iterdir()))

    def test_snapshot_excludes_later_append_without_locking_encryption(self):
        verify = AuditLedgerService.verify_chain
        def append_later():
            close_old_connections()
            try:
                return AuditLedgerService._append_entry(event_category='later', payload={'synthetic': 'later'},
                                                        chain_version='v1').pk
            finally:
                close_old_connections()
        def verify_and_append(**kwargs):
            result = verify(**kwargs)
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertGreater(pool.submit(append_later).result(timeout=10), self.tail.pk)
            return result
        with patch.object(AuditLedgerService, 'verify_chain', side_effect=verify_and_append):
            stored, event = self.create()
        lines = self.decrypt(stored)
        self.assertEqual(sum(line.get('kind') == 'ledger' for line in lines), 2)
        self.assertEqual(AuditLedgerEntry.objects.count(), 3)
        self.assertEqual(dict(event.evidence_hashes)['report'], self.tail.current_hash)

    def test_age_failure_has_no_success_archive_or_bridge_and_keeps_source(self):
        self.archive.age = '/bin/false'
        result = self.create()
        self.assertIsInstance(result, ProtectionError)
        self.assertTrue(result.trace_id.startswith('audit/archive/'))
        self.assertFalse(list(self.archive_root.glob('*.legacy.age')))
        self.assertFalse(list(self.archive_root.glob('*.legacy.json')))
        self.assertEqual(AuditLedgerEntry.objects.count(), 2)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        for path in self.archive_root.iterdir():
            self.assertNotIn(self.secret.encode(), path.read_bytes())

    def test_missing_public_key_and_wrong_purpose_never_create_output(self):
        for reference in (replace(self.public_ref, key_ref='backup-recipient/missing', version='missing'),
                          replace(self.public_ref, key_ref='backup-identity/v1', purpose=KeyPurpose.BACKUP_PRIVATE)):
            self.assertIsInstance(self.create(recipient=reference), ProtectionError)
        (self.config_path.parent / 'archive-recipient.key').unlink()
        self.assertIsInstance(self.create(), ProtectionError)
        self.assertFalse(list(self.archive_root.iterdir()))
        self.assertEqual(AuditLedgerEntry.objects.count(), 2)

    def test_snapshot_iterator_matches_original_default_verifier_with_all_error_fields(self):
        AuditLedgerEntry.objects.filter(pk=self.first.pk).update(
            payload={'tampered': True}, previous_hash='1' * 64, current_hash='2' * 64)
        original = AuditLedgerService.verify_chain()
        bounded = AuditLedgerService.verify_chain(entries=AuditLedgerEntry.objects.order_by('id').iterator(chunk_size=1))
        self.assertEqual(original, bounded)
        self.assertFalse(original.is_valid)
        self.assertEqual(original.checked_count, 2)
        self.assertEqual({error.field for error in original.errors},
                         {'payload_hash', 'previous_hash', 'current_hash'})

    def test_unbound_old_time_and_raw_event_are_copied_without_new_authenticity_claim(self):
        AuditLedgerEntry.objects.filter(pk=self.first.pk).update(created_at=self.first.created_at.replace(year=2020))
        row = SecurityAuditRecord.objects.get(event_id='legacy/archive-source')
        changed = {**row.event, 'legacy_unverified_note': self.secret}
        SecurityAuditRecord.objects.filter(pk=row.pk).update(event=changed)
        self.assertTrue(AuditLedgerService.verify_chain().is_valid)
        stored, _ = self.create()
        lines = self.decrypt(stored)
        self.assertEqual(lines[1]['row']['created_at'][:4], '2020')
        self.assertEqual(lines[-1]['row']['event'], changed)
        self.assertFalse(lines[0]['legacy_timestamps_authenticated'])
        self.assertFalse(lines[0]['security_records_authenticated'])
