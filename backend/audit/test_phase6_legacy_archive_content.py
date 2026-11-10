"""Offline age/v1 content checks, not source migration or a new authenticity claim."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase

from data_security.contracts import BASELINE_LIMITS, KeyPurpose, ProtectionError, ReasonCode
from .models import AuditLedgerEntry, SecurityAuditRecord
from .services import AuditLedgerService
from .test_phase6_legacy_archive import LegacyArchiveFixture


class LegacyArchiveContentTests(LegacyArchiveFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.context = replace(self.context, trace_id=self.context.authorization_ref)
        self.private_ref = replace(self.public_ref, key_ref='backup-identity/v1', purpose=KeyPurpose.BACKUP_PRIVATE)
        self.private_path = self.config_path.parent / 'archive-private.key'
        self.private_path.write_bytes(next(line for line in self.identity.read_bytes().splitlines()
                                          if line.startswith(b'AGE-SECRET-KEY-')) + b'\n')
        self.private_path.chmod(0o600)
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_text())
        manifest['entries'].append({'reference': self.private_ref.to_wire(), 'file': self.private_path.name,
                                    'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))

    def verify(self, stored, event, **changes):
        return self.archive.verify_content(stored, event, changes.get('identity', self.private_ref),
                                           changes.get('context', self.context))

    def reencrypt(self, stored, event, content):
        result = subprocess.run([str(self.age), '--encrypt', '--recipients-file',
            str(self.config_path.parent / 'archive-recipient.key')], input=content,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
        path = self.archive_root / (stored.object_ref.split('/')[-1] + '.legacy.age')
        path.write_bytes(result.stdout)
        changed = replace(stored, ciphertext_hash=hashlib.sha256(result.stdout).hexdigest(),
                          size_bytes=len(result.stdout))
        return changed, replace(event, evidence_hashes=(('archive', changed.ciphertext_hash),
                                                        ('report', dict(event.evidence_hashes)['report'])))

    def test_real_age_and_original_v1_verifier_work_without_database_or_sidecar(self):
        AuditLedgerEntry.objects.filter(pk=self.first.pk).update(created_at=self.first.created_at.replace(year=2020))
        row = SecurityAuditRecord.objects.get(event_id='legacy/archive-source')
        SecurityAuditRecord.objects.filter(pk=row.pk).update(event={**row.event, 'unverified_note': self.secret})
        stored, event = self.create()
        sidecar = self.archive_root / (stored.object_ref.split('/')[-1] + '.legacy.json')
        self.assertEqual(json.loads(sidecar.read_text())['archive_ref'], stored.object_ref)
        sidecar.unlink()
        before = list(AuditLedgerEntry.objects.values()), list(SecurityAuditRecord.objects.values())
        files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.archive_root.iterdir()}
        def no_query(*args):
            raise AssertionError('offline verifier must not access a database')
        with connection.execute_wrapper(no_query), \
                patch.object(self.archive, 'load', side_effect=AssertionError('no sidecar authority')), \
                patch.object(AuditLedgerService, 'verify_chain', wraps=AuditLedgerService.verify_chain) as verify:
            self.assertEqual(self.verify(stored, event), stored)
            verify.assert_called_once()
        self.assertEqual((list(AuditLedgerEntry.objects.values()), list(SecurityAuditRecord.objects.values())), before)
        self.assertEqual({path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in self.archive_root.iterdir()}, files)
        for path in self.archive_root.iterdir():
            self.assertNotIn(self.secret.encode(), path.read_bytes())

    def test_missing_wrong_purpose_wrong_key_and_wrong_service_are_rejected(self):
        stored, event = self.create()
        for identity in (replace(self.private_ref, key_ref='backup-identity/missing', version='missing'), self.public_ref):
            self.assertEqual(self.verify(stored, event, identity=identity).code, ReasonCode.KEY_UNAVAILABLE)
        with patch('data_security.adapters.persistence.legacy_archive.subprocess.Popen') as spawn:
            result = self.verify(stored, event, context=replace(self.context, actor_ref='service/other'))
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
            spawn.assert_not_called()
        wrong = self.config_path.parent / 'wrong-offline-identity'
        subprocess.run([str(self.age.with_name('age-keygen')), '-o', str(wrong)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        self.private_path.write_bytes(next(line for line in wrong.read_bytes().splitlines()
                                          if line.startswith(b'AGE-SECRET-KEY-')) + b'\n')
        self.assertEqual(self.verify(stored, event).code, ReasonCode.CIPHERTEXT_INVALID)
        self.private_path.unlink()
        self.assertEqual(self.verify(stored, event).code, ReasonCode.KEY_UNAVAILABLE)

    def test_ciphertext_digest_and_age_authentication_both_precede_success(self):
        stored, event = self.create()
        path = self.archive_root / (stored.object_ref.split('/')[-1] + '.legacy.age')
        truncated = path.read_bytes()[:-1]
        path.write_bytes(truncated)
        with patch('data_security.adapters.persistence.legacy_archive.subprocess.Popen') as spawn:
            self.assertEqual(self.verify(stored, event).code, ReasonCode.CIPHERTEXT_INVALID)
            spawn.assert_not_called()
        # A matching outer digest cannot turn a truncated age stream into success.
        changed = replace(stored, size_bytes=len(truncated), ciphertext_hash=hashlib.sha256(truncated).hexdigest())
        changed_event = replace(event, evidence_hashes=(('archive', changed.ciphertext_hash),
                                                        ('report', dict(event.evidence_hashes)['report'])))
        self.assertEqual(self.verify(changed, changed_event).code, ReasonCode.CIPHERTEXT_INVALID)
        self.assertIsInstance(self.verify(changed, event), ProtectionError)

    def test_valid_age_does_not_hide_bad_header_chain_rows_or_trailing_content(self):
        stored, event = self.create()
        original = self.decrypt(stored)
        cases = ('environment', 'approval_ref', 'timestamps', 'record_count_type',
                 'payload', 'order', 'security_link', 'extra_row')
        for case in cases:
            with self.subTest(case=case):
                rows = json.loads(json.dumps(original))
                if case == 'environment':
                    rows[0]['environment'] = 'production'
                elif case == 'approval_ref':
                    rows[0]['approval_ref'] = 'approval/different'
                elif case == 'timestamps':
                    rows[0]['legacy_timestamps_authenticated'] = True
                elif case == 'record_count_type':
                    rows[0]['security_records'] = True
                elif case == 'payload':
                    rows[1]['row']['payload'] = {'tampered': True}
                elif case == 'order':
                    rows[1], rows[2] = rows[2], rows[1]
                elif case == 'security_link':
                    rows[-1]['row']['ledger_entry_id'] = 999999
                else:
                    rows.append(rows[-1])
                content = b''.join(json.dumps(row).encode() + b'\n' for row in rows)
                changed, changed_event = self.reencrypt(stored, event, content)
                result = self.verify(changed, changed_event)
                self.assertIsInstance(result, ProtectionError)
                self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE if case == 'payload'
                                 else ReasonCode.REPORT_MISMATCH)

    def test_limits_bound_each_row_and_count_without_capping_total_archive_at_one_object(self):
        for _ in range(20):
            tail = AuditLedgerService._append_entry(event_category='synthetic-bounded-archive',
                payload={'synthetic': 'x' * 800}, chain_version='v1')
        stored, event = self.create(expected_count=22, expected_tail=tail.current_hash)
        rows = self.decrypt(stored)
        sizes = [len(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode()) + 1 for row in rows]
        self.assertGreater(sum(sizes), 2048)
        self.assertLess(max(sizes), 2048)
        self.archive.limits = replace(BASELINE_LIMITS, max_bytes=2048)
        self.assertEqual(self.verify(stored, event), stored)
        for limits, reason in ((replace(BASELINE_LIMITS, max_actions=1), ReasonCode.INVALID_VALUE),
                               (replace(BASELINE_LIMITS, max_json_bytes=32), ReasonCode.LIMIT_EXCEEDED),
                               (replace(BASELINE_LIMITS, max_bytes=32), ReasonCode.LIMIT_EXCEEDED)):
            with self.subTest(limits=limits):
                self.archive.limits = limits
                self.assertEqual(self.verify(stored, event).code, reason)

    def test_artifact_reference_permissions_and_expected_bridge_binding_are_not_bypassed(self):
        stored, event = self.create()
        for changed in (replace(event, actor_ref='service/other'), replace(event, object_ref='audit/other'),
                        replace(event, event_id='archive/other')):
            self.assertEqual(self.verify(stored, changed).code, ReasonCode.REPORT_MISMATCH)
        path = self.archive_root / (stored.object_ref.split('/')[-1] + '.legacy.age')
        path.chmod(0o640)
        self.assertEqual(self.verify(stored, event).code, ReasonCode.SOURCE_NOT_APPROVED)
        path.chmod(0o600)
        existing = path.read_bytes()
        path.unlink()
        target = self.archive_root / 'outside-reference.age'
        target.write_bytes(existing)
        target.chmod(0o600)
        path.symlink_to(target)
        self.assertIsInstance(self.verify(stored, event), ProtectionError)
