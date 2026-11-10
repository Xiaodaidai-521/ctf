"""Current permission and authenticated bridge precede explicit private-key content checks."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import connection, transaction
from django.test import TransactionTestCase

from ctf_backend.security_bootstrap import assemble_legacy_archives
from data_security.contracts import ContractViolation, EventKind, KeyPurpose, KeyStatus, ProtectionError, ReasonCode
from users.models import CTFUser
from .models import AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
from .test_phase6_legacy_archive import LegacyArchiveFixture


class LegacyArchiveVerificationOwnerTests(LegacyArchiveFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.private_ref = replace(self.public_ref, key_ref='backup-identity/v1', purpose=KeyPurpose.BACKUP_PRIVATE,
                                   status=KeyStatus.READ_ONLY)
        self.private_path = self.config_path.parent / 'archive-private.key'
        self.private_path.write_bytes(next(line for line in self.identity.read_bytes().splitlines()
                                          if line.startswith(b'AGE-SECRET-KEY-')) + b'\n')
        self.private_path.chmod(0o600)
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_text())
        manifest['entries'].append({'reference': self.private_ref.to_wire(), 'file': self.private_path.name,
                                    'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))
        self.permission = Permission.objects.get(content_type__app_label='audit', codename='archive_auditledgerentry')
        self.teacher.user_permissions.add(self.permission)
        self.owner = self.assemble_owner(identity=self.private_ref)
        self.flow = self.owner.verify_content.__self__

    def assemble_owner(self, **changes):
        return assemble_legacy_archives(config_path=self.config_path, directory=self.archive_root,
                                       age=self.age, recipient=self.public_ref, **changes)

    def capture(self):
        return self.owner.run(user=self.teacher, operation='capture', expected_count=2,
                              expected_tail=self.tail.current_hash)

    def retained(self):
        return ([list(model.objects.order_by('pk').values()) for model in
                 (AuditLedgerEntry, SecurityAuditRecord, AuthenticatedAuditEntry)],
                {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.archive_root.iterdir()})

    def test_restart_reads_authenticated_bridge_then_checks_content_without_writing(self):
        stored, _ = self.capture()
        before = self.retained()
        fresh = self.assemble_owner(identity=self.private_ref)
        flow = fresh.verify_content.__self__
        verify = flow.archives.verify_content
        def no_sql(*args):
            raise AssertionError('content verification must remain offline')
        def offline(*args):
            with connection.execute_wrapper(no_sql):
                return verify(*args)
        with patch.object(flow, 'read_event', wraps=flow.read_event) as read, \
                patch.object(flow.archives, 'verify_content', side_effect=offline) as content, \
                patch.object(flow.audit, 'record', side_effect=AssertionError('no new event')), \
                patch.object(flow.archives, 'create', side_effect=AssertionError('no recapture')), \
                patch.object(flow.archives, 'confirm', side_effect=AssertionError('no receipt rewrite')):
            for _ in range(2):
                self.assertEqual(fresh.run(user=self.teacher, operation='verify', archive_ref=stored.object_ref), stored)
            self.assertEqual(read.call_count, 2)
            self.assertEqual(content.call_count, 2)
            self.assertEqual(read.call_args.args, ('archive/' + stored.object_ref.split('/')[-1],))
        self.assertEqual(self.retained(), before)

    def test_current_permission_active_state_and_outer_transaction_precede_file_access(self):
        stored, _ = self.capture()
        cached = CTFUser.objects.get(pk=self.teacher.pk)
        self.assertTrue(cached.has_perm('audit.archive_auditledgerentry'))
        with patch.object(self.flow.archives, 'load') as load, \
                patch.object(self.flow.archives, 'verify_content') as verify:
            self.teacher.user_permissions.remove(self.permission)
            self.assertEqual(self.owner.run(user=cached, operation='verify', archive_ref=stored.object_ref).code,
                             ReasonCode.AUTHORIZATION_DENIED)
            self.teacher.user_permissions.add(self.permission)
            CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
            self.assertEqual(self.owner.run(user=cached, operation='verify', archive_ref=stored.object_ref).code,
                             ReasonCode.AUTHORIZATION_DENIED)
            CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=True)
            with transaction.atomic():
                self.assertEqual(self.owner.run(user=cached, operation='verify', archive_ref=stored.object_ref).code,
                                 ReasonCode.DELIVERY_UNKNOWN)
            load.assert_not_called()
            verify.assert_not_called()
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_missing_authenticated_bridge_cannot_be_replaced_by_confirmed_sidecar(self):
        record = self.flow.audit.record
        def no_bridge(event, durability):
            if event.kind is EventKind.BACKUP:
                return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
                                       retryable=False, trace_id='synthetic/bridge-unknown')
            return record(event, durability)
        with patch.object(self.flow.audit, 'record', side_effect=no_bridge):
            result = self.capture()
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        metadata_path = self.archive_root / (result.trace_id.split('/')[-1] + '.legacy.json')
        metadata = json.loads(metadata_path.read_text())
        metadata_path.write_text(json.dumps({**metadata, 'bridge_state': 'confirmed',
                                            'bridge_receipt': {'synthetic': 'not-an-authenticated-receipt'}}))
        before = self.retained()
        with patch.object(self.flow.archives, 'verify_content') as verify:
            self.assertIsInstance(self.owner.run(user=self.teacher, operation='verify', archive_ref=result.trace_id),
                                  ProtectionError)
            verify.assert_not_called()
        self.assertEqual(self.retained(), before)
        stored, _ = self.owner.run(user=self.teacher, operation='reconcile', archive_ref=result.trace_id)
        self.assertEqual(self.owner.run(user=self.teacher, operation='verify', archive_ref=stored.object_ref), stored)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_changed_local_evidence_and_corrupt_authenticated_bridge_never_reach_decryption(self):
        stored, _ = self.capture()
        metadata_path = self.archive_root / (stored.object_ref.split('/')[-1] + '.legacy.json')
        original = metadata_path.read_bytes()
        metadata = json.loads(original)
        changed_event = {**metadata['bridge_event'], 'counts': [['records', 1], ['processed', 1]]}
        metadata_path.write_text(json.dumps({**metadata, 'chain_length': 1, 'bridge_event': changed_event}))
        with patch.object(self.flow.archives, 'verify_content') as verify:
            self.assertEqual(self.owner.run(user=self.teacher, operation='verify', archive_ref=stored.object_ref).code,
                             ReasonCode.REPORT_MISMATCH)
            verify.assert_not_called()
        metadata_path.write_bytes(original)
        row = SecurityAuditRecord.objects.get(event_id=metadata['bridge_event']['event_id'])
        SecurityAuditRecord.objects.filter(pk=row.pk).update(event={**row.event, 'counts': [['records', 1]]})
        with patch.object(self.flow.archives, 'verify_content') as verify:
            self.assertIsInstance(self.owner.run(user=self.teacher, operation='verify', archive_ref=stored.object_ref),
                                  ProtectionError)
            verify.assert_not_called()
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_private_identity_is_explicit_and_failures_preserve_archive_and_source(self):
        stored, _ = self.capture()
        before = self.retained()
        default = self.assemble_owner()
        with patch.object(default.capture.__self__.archives, 'load') as load:
            self.assertEqual(default.run(user=self.teacher, operation='verify', archive_ref=stored.object_ref).code,
                             ReasonCode.KEY_UNAVAILABLE)
            load.assert_not_called()
        for identity in (self.public_ref, replace(self.private_ref, status=KeyStatus.RETIRED)):
            with self.assertRaises(ContractViolation):
                self.assemble_owner(identity=identity)
        self.assertTrue(self.private_path.read_bytes().startswith(b'AGE-SECRET-KEY-'))
        self.private_path.unlink()
        self.assertEqual(self.owner.run(user=self.teacher, operation='verify', archive_ref=stored.object_ref).code,
                         ReasonCode.KEY_UNAVAILABLE)
        self.assertEqual(self.retained(), before)
        path = self.archive_root / (stored.object_ref.split('/')[-1] + '.legacy.age')
        original = path.read_bytes()
        path.write_bytes(original[:-1])
        self.assertEqual(self.owner.run(user=self.teacher, operation='verify', archive_ref=stored.object_ref).code,
                         ReasonCode.CIPHERTEXT_INVALID)
        path.write_bytes(original)
        self.assertEqual(self.retained(), before)
