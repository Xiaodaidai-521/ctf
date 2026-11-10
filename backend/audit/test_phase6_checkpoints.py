"""External immutable checkpoints; a trusted selected reference defines the covered prefix."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import os
import tempfile
from unittest.mock import patch

from django.db import transaction
from django.test import TransactionTestCase
from django.utils import timezone

from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.application.audit_gateway import AuditGateway
from data_security.contracts import (
    AuditCheckpoint, AuditReceipt, ContractViolation, Durability, KeyStatus, ProtectionError,
    ReasonCode, canonical_bytes, content_hash,
)
from .models import AuthenticatedAuditEntry, SecurityAuditRecord
from .test_phase6_authenticated_chain import AuditChainFixture


class AuditCheckpointTests(AuditChainFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory(prefix='audit-checkpoint-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.root.chmod(0o700)
        self.sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=self.key,
                                   context=self.context, checkpoint_root=self.root)
        self.gateway = AuditGateway(sink=self.sink)

    def reader(self, reference, **changes):
        values = dict(clock=timezone.now, crypto=self.crypto, key=self.key, context=self.context,
                      checkpoint_root=self.root, checkpoint_ref=reference)
        return DjangoAuditSink(**dict(values, **changes))

    def point(self):
        value = self.sink.checkpoint('ds.audit.v2')
        self.assertIsInstance(value, AuditReceipt)
        return value

    def path(self, reference):
        return self.root / (reference.removeprefix('audit/checkpoint/') + '.json')

    def test_checkpoint_is_external_immutable_authenticated_and_explicitly_selected(self):
        self.append()
        self.append(2)
        at = timezone.now()
        self.sink.clock = lambda: at
        point = self.point()
        path = self.path(point.checkpoint_ref)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        checkpoint = AuditCheckpoint.from_json(path.read_bytes())
        self.assertEqual(checkpoint.receipt.sequence, 2)
        self.assertEqual(checkpoint.checkpointed_at, at)
        self.assertEqual(self.point(), point)
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(self.reader(point.checkpoint_ref).verify('ds.audit.v2'), point)
        # Root alone never means that a trusted expected checkpoint was selected.
        self.assertIsNone(self.sink.verify('ds.audit.v2').checkpoint_ref)

    def test_covered_tail_deletion_fails_but_post_checkpoint_suffix_window_remains(self):
        self.append()
        self.append(2)
        point = self.point()
        reader = self.reader(point.checkpoint_ref)
        self.append(3)
        checked = reader.verify('ds.audit.v2')
        self.assertEqual(checked.sequence, 3)
        self.assertEqual(checked.checkpoint_ref, point.checkpoint_ref)
        AuthenticatedAuditEntry.objects.filter(sequence=3).delete()
        self.assertEqual(reader.verify('ds.audit.v2'), point)
        AuthenticatedAuditEntry.objects.filter(sequence=2).delete()
        self.assertIsInstance(reader.verify('ds.audit.v2'), ProtectionError)
        self.assertIsInstance(reader.checkpoint('ds.audit.v2'), ProtectionError)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_missing_truncated_tampered_oversized_or_public_checkpoint_never_falls_back(self):
        self.append()
        point = self.point()
        reader = self.reader(point.checkpoint_ref)
        path = self.path(point.checkpoint_ref)
        original = path.read_bytes()
        for content in (b'', original[:-1], bytes(len(original)), b' ' * 16385):
            path.write_bytes(content)
            self.assertIsInstance(reader.verify('ds.audit.v2'), ProtectionError)
        path.write_bytes(original)
        path.chmod(0o644)
        self.assertIsInstance(reader.verify('ds.audit.v2'), ProtectionError)
        path.chmod(0o600)
        path.unlink()
        self.assertIsInstance(reader.verify('ds.audit.v2'), ProtectionError)
        self.assertIsInstance(reader.checkpoint('ds.audit.v2'), ProtectionError)

    def test_changed_content_with_recomputed_filename_still_fails_mac(self):
        self.append()
        point = self.point()
        original = AuditCheckpoint.from_json(self.path(point.checkpoint_ref).read_bytes())
        tampered = replace(original, checkpointed_at=original.checkpointed_at + timedelta(seconds=1))
        name = 'audit/checkpoint/' + content_hash(tampered)
        target = self.path(name)
        target.write_bytes(canonical_bytes(tampered))
        target.chmod(0o600)
        self.assertIsInstance(self.reader(name).verify('ds.audit.v2'), ProtectionError)
        self.assertEqual(self.reader(point.checkpoint_ref).verify('ds.audit.v2'), point)

    def test_readonly_retained_key_verifies_checkpoint_without_issuing_new_one(self):
        self.append()
        point = self.point()
        reader = self.reader(point.checkpoint_ref, key=replace(self.key, status=KeyStatus.READ_ONLY))
        with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('no signing')):
            self.assertEqual(reader.verify('ds.audit.v2'), point)
            self.assertIsInstance(reader.checkpoint('ds.audit.v2'), ProtectionError)
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.assertEqual(self.crypto.keys.calls[-1][0].status, KeyStatus.READ_ONLY)

    def test_checkpoint_requires_committed_chain_and_does_not_anchor_outer_transaction(self):
        with transaction.atomic():
            self.append()
            result = self.sink.checkpoint('ds.audit.v2')
            self.assertIsInstance(result, ProtectionError)
            self.assertEqual(list(self.root.iterdir()), [])
            transaction.set_rollback(True)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertIsInstance(self.sink.checkpoint('ds.audit.v2'), ProtectionError)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_failed_signing_or_fsync_does_not_claim_anchor_or_modify_chain(self):
        first = self.append()
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                                  retryable=False, trace_id='fixture/key')
        with patch.object(self.crypto, 'authenticate', return_value=failure):
            self.assertIsInstance(self.sink.checkpoint('ds.audit.v2'), ProtectionError)
        self.assertEqual(list(self.root.iterdir()), [])
        with patch('data_security.adapters.persistence.audit.os.fsync', side_effect=OSError('omitted')):
            self.assertIsInstance(self.sink.checkpoint('ds.audit.v2'), ProtectionError)
        self.assertEqual(self.sink.verify('ds.audit.v2'), first)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(len(list(self.root.iterdir())), 1)  # Failed file retained, no success reference.

    def test_root_reference_and_cross_chain_binding_are_not_trusted_from_database(self):
        self.append()
        point = self.point()
        other = self.reader(point.checkpoint_ref, context=replace(self.context, project_ref='project/other'))
        self.assertIsInstance(other.verify('ds.audit.v2'), ProtectionError)
        for reference in ('../outside', 'audit/checkpoint/not-a-hash'):
            with self.assertRaises(ContractViolation):
                self.reader(reference)
        self.root.chmod(0o755)
        with self.assertRaises(ContractViolation):
            self.reader(point.checkpoint_ref)
        self.root.chmod(0o700)
        target = self.path(point.checkpoint_ref)
        original = target.read_bytes()
        target.unlink()
        different = self.root / 'different.json'
        different.write_bytes(original)
        different.chmod(0o600)
        os.symlink(different, target)
        self.assertIsInstance(self.reader(point.checkpoint_ref).verify('ds.audit.v2'), ProtectionError)
