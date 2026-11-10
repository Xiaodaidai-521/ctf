"""Explicit B, current Django permission, real age and restart reconciliation on isolated PG."""
import hashlib
import json
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import transaction
from django.test import TransactionTestCase

from ctf_backend.security_bootstrap import assemble_legacy_archives
from data_security.contracts import ContractViolation, EventKind, ProtectionError, ReasonCode
from users.models import CTFUser
from .models import AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
from .test_phase6_legacy_archive import LegacyArchiveFixture


class LegacyArchiveOwnerTests(LegacyArchiveFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.assemble_owner()
        self.flow = self.owner.capture.__self__
        self.permission = Permission.objects.get(content_type__app_label='audit', codename='archive_auditledgerentry')

    def assemble_owner(self):
        return assemble_legacy_archives(config_path=self.config_path, directory=self.archive_root,
                                       age=self.age, recipient=self.public_ref)

    def approve(self, **changes):
        return self.owner.run(**{**dict(user=self.teacher, operation='capture', expected_count=2,
                                       expected_tail=self.tail.current_hash), **changes})

    def test_explicit_permission_approves_exact_prefix_and_persists_bridge_receipt(self):
        self.assertFalse(self.teacher.has_perm('audit.archive_auditledgerentry'))
        self.teacher.user_permissions.add(self.permission)
        before = list(AuditLedgerEntry.objects.values())
        stored, receipt = self.approve()
        self.assertEqual(receipt.chain_version, 'ds.audit.v2')
        metadata = json.loads(next(self.archive_root.glob('*.legacy.json')).read_text())
        self.assertEqual(metadata['bridge_state'], 'confirmed')
        self.assertEqual(metadata['bridge_receipt'], receipt.to_wire())
        approval = self.flow.read_event(metadata['approval_ref'])
        self.assertEqual(approval.actor_ref, 'user/' + str(self.teacher.pk))
        self.assertEqual(approval.kind, EventKind.AUTHORIZATION)
        self.assertEqual(approval.counts, (('records', 2),))
        self.assertEqual(approval.evidence_hashes, (('report', self.tail.current_hash),))
        self.assertEqual(list(AuditLedgerEntry.objects.values()), before)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(self.decrypt(stored)[1]['row']['payload'], {'synthetic': self.secret})
        fresh = self.assemble_owner()
        self.assertEqual(fresh.run(user=self.teacher, operation='reconcile', archive_ref=stored.object_ref),
                         (stored, receipt))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(len(list(self.archive_root.glob('*.legacy.age'))), 1)

    def test_current_permission_and_active_state_override_cached_role_or_permission(self):
        self.assertEqual(self.approve().code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertFalse(list(self.archive_root.iterdir()))
        self.teacher.user_permissions.add(self.permission)
        cached = CTFUser.objects.get(pk=self.teacher.pk)
        self.assertTrue(cached.has_perm('audit.archive_auditledgerentry'))
        stored, _ = self.approve(user=cached)
        self.teacher.user_permissions.remove(self.permission)
        self.assertEqual(self.approve(user=cached).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.owner.run(user=cached, operation='reconcile', archive_ref=stored.object_ref).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.teacher.user_permissions.add(self.permission)
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
        self.assertEqual(self.approve(user=cached).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(len(list(self.archive_root.glob('*.legacy.age'))), 1)

    def test_outer_transaction_bad_request_prefix_and_unconfigured_chain_cannot_capture(self):
        self.teacher.user_permissions.add(self.permission)
        with transaction.atomic():
            self.assertEqual(self.approve().code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        for ref in (None, '../outside', ''):
            self.assertIsInstance(self.owner.run(user=self.teacher, operation='reconcile', archive_ref=ref), ProtectionError)
        self.assertEqual(self.approve(expected_count=1).code, ReasonCode.REPORT_MISMATCH)
        self.assertEqual(self.approve(expected_tail='0' * 64).code, ReasonCode.REPORT_MISMATCH)
        self.assertFalse(list(self.archive_root.iterdir()))
        self.config.pop('audit_chain')
        self.config_path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            self.assemble_owner()
        self.config['environment'] = 'production'
        self.config_path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            self.assemble_owner()
        self.assertEqual(AuditLedgerEntry.objects.count(), 2)

    def test_approval_audit_failure_or_old_chain_receipt_stops_before_age(self):
        self.teacher.user_permissions.add(self.permission)
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                  retryable=False, trace_id='synthetic/audit-failure')
        with patch.object(self.flow.archives, 'create') as create:
            with patch.object(self.flow.audit, 'record', return_value=failure):
                self.assertEqual(self.approve().code, ReasonCode.AUDIT_UNAVAILABLE)
            legacy = self.gateway.sink.verify('v1')
            with patch.object(self.flow.audit, 'record', return_value=legacy):
                self.assertEqual(self.approve().code, ReasonCode.AUDIT_UNAVAILABLE)
            create.assert_not_called()
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertFalse(list(self.archive_root.iterdir()))

    def test_bridge_unknown_before_or_after_commit_reconciles_on_restart_without_recapture(self):
        self.teacher.user_permissions.add(self.permission)
        record = self.flow.audit.record
        for committed in (False, True):
            with self.subTest(committed=committed):
                prior = AuthenticatedAuditEntry.objects.count()
                def fail_bridge(event, durability):
                    if event.kind is EventKind.BACKUP:
                        if committed:
                            record(event, durability)
                        return ProtectionError(schema_version=ProtectionError.SCHEMA,
                            code=ReasonCode.DELIVERY_UNKNOWN, retryable=False, trace_id='synthetic/lost-receipt')
                    return record(event, durability)
                with patch.object(self.flow.audit, 'record', side_effect=fail_bridge):
                    result = self.approve()
                self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
                self.assertTrue(result.trace_id.startswith('audit/archive/'))
                prefix = result.trace_id.split('/')[-1]
                metadata_path = self.archive_root / (prefix + '.legacy.json')
                self.assertEqual(json.loads(metadata_path.read_text())['bridge_state'], 'pending')
                encrypted = (self.archive_root / (prefix + '.legacy.age')).read_bytes()
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), prior + 1 + int(committed))
                fresh = self.assemble_owner()
                with patch.object(fresh.capture.__self__.archives, 'create', side_effect=AssertionError('recapture')):
                    stored, receipt = fresh.run(user=self.teacher, operation='reconcile', archive_ref=result.trace_id)
                self.assertEqual(stored.object_ref, result.trace_id)
                self.assertEqual(stored.ciphertext_hash, hashlib.sha256(encrypted).hexdigest())
                self.assertEqual(json.loads(metadata_path.read_text())['bridge_receipt'], receipt.to_wire())
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), prior + 2)
                self.assertEqual((self.archive_root / (prefix + '.legacy.age')).read_bytes(), encrypted)
        self.assertEqual(AuditLedgerEntry.objects.count(), 2)

    def test_receipt_persistence_failure_is_unknown_and_reconciliation_keeps_same_ciphertext(self):
        self.teacher.user_permissions.add(self.permission)
        confirm = self.flow.archives.confirm
        def fail_confirmation(*args):
            with patch('data_security.adapters.persistence.legacy_archive.os.fsync', side_effect=OSError):
                return confirm(*args)
        with patch.object(self.flow.archives, 'confirm', side_effect=fail_confirmation):
            result = self.approve()
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(len(list(self.archive_root.glob('*.legacy.age'))), 1)
        prefix = result.trace_id.split('/')[-1]
        metadata_path = self.archive_root / (prefix + '.legacy.json')
        self.assertEqual(json.loads(metadata_path.read_text())['bridge_state'], 'pending')
        stored, receipt = self.assemble_owner().run(user=self.teacher, operation='reconcile', archive_ref=result.trace_id)
        self.assertEqual(json.loads(metadata_path.read_text())['bridge_receipt'], receipt.to_wire())
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(len(list(self.archive_root.glob('*.legacy.age'))), 1)
        self.assertEqual(stored.object_ref, result.trace_id)
        for path in self.archive_root.iterdir():
            self.assertNotIn(self.secret.encode(), path.read_bytes())

    def test_bad_retained_file_metadata_or_authenticated_approval_never_rebridges(self):
        self.teacher.user_permissions.add(self.permission)
        record = self.flow.audit.record
        def fail_bridge(event, durability):
            return (ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
                    retryable=False, trace_id='synthetic/pending') if event.kind is EventKind.BACKUP
                    else record(event, durability))
        with patch.object(self.flow.audit, 'record', side_effect=fail_bridge):
            result = self.approve()
        prefix = result.trace_id.split('/')[-1]
        path = self.archive_root / (prefix + '.legacy.age')
        original = path.read_bytes()
        metadata_path = self.archive_root / (prefix + '.legacy.json')
        metadata = json.loads(metadata_path.read_text())
        path.write_bytes(original[:-1])
        self.assertEqual(self.owner.run(user=self.teacher, operation='reconcile', archive_ref=result.trace_id).code,
                         ReasonCode.CIPHERTEXT_INVALID)
        path.write_bytes(original)
        metadata_path.write_text(json.dumps({**metadata, 'tail_hash': '0' * 64}))
        self.assertEqual(self.owner.run(user=self.teacher, operation='reconcile', archive_ref=result.trace_id).code,
                         ReasonCode.REPORT_MISMATCH)
        changed_event = {**metadata['bridge_event'], 'counts': [['records', 1], ['processed', 1]]}
        metadata_path.write_text(json.dumps({**metadata, 'chain_length': 1, 'bridge_event': changed_event}))
        self.assertEqual(self.owner.run(user=self.teacher, operation='reconcile', archive_ref=result.trace_id).code,
                         ReasonCode.REPORT_MISMATCH)
        metadata_path.write_text(json.dumps(metadata))
        approval = SecurityAuditRecord.objects.get(event_id=metadata['approval_ref'])
        SecurityAuditRecord.objects.filter(pk=approval.pk).update(event={**approval.event, 'counts': [['records', 1]]})
        self.assertIsInstance(self.owner.run(user=self.teacher, operation='reconcile', archive_ref=result.trace_id), ProtectionError)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(json.loads(metadata_path.read_text())['bridge_state'], 'pending')
        self.assertEqual(len(list(self.archive_root.glob('*.legacy.age'))), 1)
