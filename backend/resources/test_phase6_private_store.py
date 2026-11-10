"""Synthetic private-file lifecycle on the isolated PostgreSQL database."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.db import DatabaseError, connection
from django.test import TestCase, TransactionTestCase

from data_security.adapters.persistence.models import PrivateObject
from data_security.adapters.persistence.private_store import DjangoPrivateStore
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.adapters.tabular.codec import TableCodec
from data_security.application.crypto_service import CryptoService
from data_security.application.reports import ReportAuthenticator
from data_security.application.table_reports import ReportCandidate, TableReportExecutor
from data_security.contracts import (
    BASELINE_LIMITS, BoundedPayload, CipherEnvelope, ContractViolation, Environment, ExecutionBinding, KeyPurpose,
    MediaType, ObjectContext, PayloadKind, ProtectionError, ReasonCode, SecretMaterial, StoredObject, canonical_bytes,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key, text
from data_security.tests.test_phase5_codec import binary
from data_security.tests.test_phase5_pipeline import pipeline_fixture
from data_security.tests.test_source_plans import AT


class PrivateStoreFixture:
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix='private-store-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.context = examples()[ObjectContext]
        self.key = reference_key()
        self.keys = FakeKeys()
        self.crypto = CryptoService(keys=self.keys, service_identity='private-store/test',
            random_bytes=os.urandom, environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.store = DjangoPrivateStore(root=self.root, crypto=self.crypto, environment=Environment.TEST)
        self.payload = text('synthetic-private-sentinel-6f03@example.test')
        self.envelope = self.crypto.seal(self.payload, self.context, self.key)
        self.assertIsInstance(self.envelope, CipherEnvelope)

    def path(self, stored):
        return self.root / (stored.object_ref.removeprefix('private/') + '.sealed')

    def candidate(self, envelope=None, context=None):
        stored = self.store.write_candidate(envelope or self.envelope, context or self.context)
        self.assertIsInstance(stored, StoredObject)
        return stored

    def verified(self):
        stored = self.store.verify(self.candidate(), self.context)
        self.assertIsInstance(stored, StoredObject)
        self.assertEqual(stored.state, 'verified')
        return stored

    def denied(self, result, code=None):
        self.assertIsInstance(result, ProtectionError)
        if code is not None:
            self.assertEqual(result.code, code)


class PrivateStoreTests(PrivateStoreFixture, TestCase):
    def test_immutable_lifecycle_replay_and_renewed_grant(self):
        candidate = self.candidate()
        self.assertEqual(candidate.state, 'candidate')
        encoded = self.path(candidate).read_bytes()
        self.assertEqual(encoded, canonical_bytes(self.envelope))
        self.assertEqual(candidate.ciphertext_hash, hashlib.sha256(encoded).hexdigest())
        self.assertEqual(candidate.size_bytes, len(encoded))
        self.assertEqual(self.path(candidate).stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.payload.text.encode(), encoded)
        self.assertEqual(self.candidate(), candidate)
        self.denied(self.store.read(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
        verified = self.store.verify(candidate, self.context)
        self.assertEqual(verified.state, 'verified')
        with patch.object(self.crypto, 'open', wraps=self.crypto.open) as opened:
            published = self.store.publish(verified, self.context)
            self.assertEqual(published.state, 'published')
            self.assertEqual(self.store.publish(candidate, self.context), published)
            opened.assert_not_called()
        restored = DjangoPrivateStore(root=self.root, crypto=self.crypto, environment=Environment.TEST)
        renewed = replace(self.context, authorization_ref='authorization/renewed')
        self.assertEqual(restored.write_candidate(self.envelope, renewed), published)
        self.assertEqual(restored.read(candidate, renewed), self.envelope)
        self.assertEqual(self.crypto.open(restored.read(published, renewed), renewed, self.key), self.payload)
        self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_client_state_does_not_publish_unverified_candidate(self):
        candidate = self.candidate()
        for state in ('candidate', 'verified', 'published'):
            forged = replace(candidate, state=state)
            self.denied(self.store.publish(forged, self.context), ReasonCode.AUTHORIZATION_DENIED)
            self.denied(self.store.read(forged, self.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(PrivateObject.objects.get().state, 'candidate')

    def test_complete_stored_identity_is_checked(self):
        verified = self.verified()
        changed = (replace(verified, object_ref='private/' + '0' * 64),
            replace(verified, version='other-version'), replace(verified, ciphertext_hash='0' * 64),
            replace(verified, size_bytes=verified.size_bytes + 1),
            replace(verified, object_ref='private/not-a-digest'))
        with self.assertRaises(ContractViolation):
            replace(verified, object_ref='private/../../outside')
        for stored in changed:
            for operation in (self.store.verify, self.store.publish, self.store.read):
                self.denied(operation(stored, self.context))
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_cross_object_version_field_project_and_environment_are_denied(self):
        candidate = self.candidate()
        for changes in ({'object_uuid': '00000000-0000-4000-8000-000000000002'},
                        {'object_version': 'v2'}, {'field_ref': 'other/field'},
                        {'project_ref': 'other/project'}, {'environment': Environment.EVALUATION}):
            changed = replace(self.context, **changes)
            for operation in (self.store.verify, self.store.publish, self.store.read):
                self.denied(operation(candidate, changed))
        cross = replace(self.context, object_version='v2')
        cross_candidate = self.candidate(context=cross)
        self.denied(self.store.verify(cross_candidate, cross), ReasonCode.CIPHERTEXT_INVALID)
        self.assertFalse(PrivateObject.objects.exclude(state='candidate').exists())

    def test_wrong_key_and_unavailable_key_never_verify(self):
        candidate = self.candidate()
        with patch.object(self.keys, 'resolve', return_value=SecretMaterial(b'W' * 32, KeyPurpose.DATA)):
            self.denied(self.store.verify(candidate, self.context), ReasonCode.CIPHERTEXT_INVALID)
        self.keys.error = ReasonCode.KEY_UNAVAILABLE
        self.denied(self.store.verify(candidate, self.context), ReasonCode.KEY_UNAVAILABLE)
        self.assertEqual(PrivateObject.objects.get().state, 'candidate')

    def test_forged_tag_salt_and_nonce_cannot_pass_authentication(self):
        for field in ('kdf_salt', 'nonce', 'ciphertext_and_tag'):
            original = getattr(self.envelope, field)
            changed = replace(self.envelope, **{field: bytes([original[0] ^ 1]) + original[1:]})
            candidate = self.candidate(envelope=changed)
            self.denied(self.store.verify(candidate, self.context), ReasonCode.CIPHERTEXT_INVALID)
            self.denied(self.store.publish(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(PrivateObject.objects.exclude(state='candidate').exists())

    def test_truncation_and_file_tamper_before_verify_are_denied(self):
        candidate = self.candidate()
        path = self.path(candidate)
        original = path.read_bytes()
        for changed in (original[:-1], b'X' + original[1:]):
            path.write_bytes(changed)
            self.denied(self.store.verify(candidate, self.context))
            self.denied(self.store.publish(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(PrivateObject.objects.get().state, 'candidate')

    def test_published_file_tamper_and_missing_file_do_not_return_ciphertext(self):
        published = self.store.publish(self.verified(), self.context)
        path = self.path(published)
        original = path.read_bytes()
        path.write_bytes(b'X' + original[1:])
        self.denied(self.store.read(published, self.context), ReasonCode.HASH_MISMATCH)
        path.unlink()
        self.denied(self.store.read(published, self.context), ReasonCode.DELIVERY_UNKNOWN)

    def test_private_root_and_symlink_file_boundary(self):
        for root, environment in ((self.root, Environment.PRODUCTION), (Path('.'), Environment.TEST)):
            with self.assertRaises(ContractViolation):
                DjangoPrivateStore(root=root, crypto=self.crypto, environment=environment)
        self.root.chmod(0o755)
        with self.assertRaises(ContractViolation):
            DjangoPrivateStore(root=self.root, crypto=self.crypto, environment=Environment.TEST)
        self.root.chmod(0o700)
        candidate = self.candidate()
        path = self.path(candidate)
        other = path.with_suffix('.other')
        path.rename(other)
        path.symlink_to(other)
        self.denied(self.store.verify(candidate, self.context), ReasonCode.DELIVERY_UNKNOWN)
        self.denied(self.store.write_candidate(self.envelope, self.context), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(other.read_bytes(), canonical_bytes(self.envelope))

    def test_public_mode_or_hardlinked_file_is_rejected(self):
        candidate = self.candidate()
        path = self.path(candidate)
        path.chmod(0o644)
        self.denied(self.store.verify(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
        path.chmod(0o600)
        path.with_suffix('.link').hardlink_to(path)
        self.denied(self.store.verify(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)

    def test_database_failure_leaves_only_unregistered_ciphertext_and_retry_recovers(self):
        with patch.object(PrivateObject.objects, 'get_or_create', side_effect=DatabaseError('injected')):
            self.denied(self.store.write_candidate(self.envelope, self.context), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(PrivateObject.objects.count(), 0)
        files = list(self.root.iterdir())
        self.assertEqual(len(files), 1)
        self.assertNotIn(self.payload.text.encode(), files[0].read_bytes())
        candidate = self.candidate()
        self.assertEqual(self.path(candidate), files[0])
        PrivateObject.objects.all().delete()
        self.denied(self.store.read(replace(candidate, state='published'), self.context),
                    ReasonCode.AUTHORIZATION_DENIED)

    def test_fsync_failure_does_not_register_and_partial_orphan_is_not_overwritten(self):
        with patch('data_security.adapters.persistence.private_store.os.fsync', side_effect=OSError('injected')):
            self.denied(self.store.write_candidate(self.envelope, self.context), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(PrivateObject.objects.count(), 0)
        path, = self.root.iterdir()
        path.write_bytes(path.read_bytes()[:-1])
        original = path.read_bytes()
        self.denied(self.store.write_candidate(self.envelope, self.context), ReasonCode.CIPHERTEXT_INVALID)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(PrivateObject.objects.count(), 0)

    def test_short_uow_rollback_never_publishes_and_preserves_ciphertext(self):
        verified = self.verified()
        with DjangoUnitOfWork():
            self.assertEqual(self.store.publish(verified, self.context).state, 'published')
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        with self.assertRaisesMessage(RuntimeError, 'audit failed'):
            with DjangoUnitOfWork() as uow:
                self.store.publish(verified, self.context)
                uow.commit()
                raise RuntimeError('audit failed')
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.denied(self.store.read(verified, self.context), ReasonCode.AUTHORIZATION_DENIED)
        with DjangoUnitOfWork() as uow:
            published = self.store.publish(verified, self.context)
            uow.commit()
        self.assertEqual(self.store.read(published, self.context), self.envelope)


class PrivateStoreCapacityTests(PrivateStoreFixture, TestCase):
    def test_twenty_mib_encrypted_candidate_verify_publish_and_authenticated_read(self):
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
            media_type=MediaType.BINARY, text=None, tree=None,
            binary=b'F' * BASELINE_LIMITS.max_bytes, limits=BASELINE_LIMITS)
        envelope = self.crypto.seal(payload, self.context, self.key)
        self.assertIsInstance(envelope, CipherEnvelope)
        candidate = self.candidate(envelope=envelope)
        self.assertEqual(self.store.verify(candidate, self.context).state, 'verified')
        published = self.store.publish(candidate, self.context)
        self.assertEqual(published.state, 'published')
        returned = self.store.read(published, self.context)
        self.assertEqual(self.crypto.open(returned, self.context, self.key), payload)
        self.assertNotIn(b'F' * 64, self.path(published).read_bytes())
        with self.assertRaises(ContractViolation):
            replace(payload, binary=payload.binary + b'F')
        self.assertEqual(PrivateObject.objects.count(), 1)


class PrivateStoreTransactionTests(PrivateStoreFixture, TransactionTestCase):
    def test_file_io_and_crypto_authentication_are_outside_database_transaction(self):
        fsync = os.fsync
        def check_fsync(fd):
            self.assertFalse(connection.in_atomic_block)
            return fsync(fd)
        with patch('data_security.adapters.persistence.private_store.os.fsync', side_effect=check_fsync):
            candidate = self.candidate()
        crypto_open = self.crypto.open
        def check_open(*args):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(PrivateObject.objects.get().state, 'candidate')
            return crypto_open(*args)
        with patch.object(self.crypto, 'open', side_effect=check_open) as opened:
            self.assertEqual(self.store.verify(candidate, self.context).state, 'verified')
            opened.assert_called_once()

    def test_candidate_row_rollback_leaves_unreadable_orphan_not_fake_atomic_file(self):
        with DjangoUnitOfWork():
            candidate = self.candidate()
        self.assertFalse(PrivateObject.objects.exists())
        self.assertTrue(self.path(candidate).is_file())
        self.denied(self.store.read(replace(candidate, state='published'), self.context),
                    ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.candidate(), candidate)


class PrivateReportTests(PrivateStoreFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        _, self.plan, self.expected, content = pipeline_fixture('legacy', 'xlsx')
        self.payload = binary(content, MediaType.XLSX)
        self.execution = replace(examples()[ExecutionBinding], asset_version=self.plan.asset_version,
            policy_binding=self.plan.policy_binding, scope=self.plan.scope, environment='test',
            domain_ref=self.plan.source.source_domain, expires_at=self.plan.expires_at)
        self.context = replace(self.context, object_version=self.plan.asset_version,
                               authorization_ref=self.execution.authorization_id)
        self.auth = ReportAuthenticator(crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
            executor_ref='executor/test', environment=Environment.TEST, clock=lambda: AT + timedelta(seconds=1))
        self.executor = TableReportExecutor(codec_factory=TableCodec, crypto=self.crypto, data_key=self.key,
            store=self.store, authenticator=self.auth, limits=BASELINE_LIMITS,
            clock=lambda: AT + timedelta(seconds=1))

    def prepare(self):
        return self.executor.prepare(self.payload, self.plan, self.execution, self.context)

    def test_real_private_report_uses_actual_cipher_file_and_no_long_transaction(self):
        fsync, opened = os.fsync, self.crypto.open
        def check_fsync(*args):
            self.assertFalse(connection.in_atomic_block)
            return fsync(*args)
        def check_open(*args):
            self.assertFalse(connection.in_atomic_block)
            return opened(*args)
        with patch('data_security.adapters.persistence.private_store.os.fsync', side_effect=check_fsync), \
             patch.object(self.crypto, 'open', side_effect=check_open):
            result = self.prepare()
        self.assertIsInstance(result, ReportCandidate)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        encoded = self.path(result.stored).read_bytes()
        self.assertEqual(result.report.ciphertext_hash, hashlib.sha256(encoded).hexdigest())
        envelope = CipherEnvelope.from_json(encoded)
        output = self.crypto.open(envelope, self.context, self.key)
        self.assertEqual(output.binary, self.expected)
        self.assertNotIn(b'a@example.invalid', encoded)
        self.assertNotIn(self.expected, encoded)
        self.assertIs(self.auth.verify(result.report, result.proof, self.execution, self.plan, self.context,
            input_hash=hashlib.sha256(self.payload.binary).hexdigest(),
            output_hash=hashlib.sha256(output.binary).hexdigest(),
            ciphertext_hash=hashlib.sha256(encoded).hexdigest()), True)
        self.denied(self.store.read(replace(result.stored, state='published'), self.context),
                    ReasonCode.AUTHORIZATION_DENIED)

    def test_failed_report_authentication_leaves_only_unpublished_ciphertext(self):
        with patch.object(self.crypto, 'authenticate', return_value=ProtectionError(
                schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                retryable=False, trace_id='synthetic/key')):
            self.denied(self.prepare(), ReasonCode.KEY_UNAVAILABLE)
        record = PrivateObject.objects.get()
        self.assertEqual(record.state, 'verified')
        stored = StoredObject(schema_version=StoredObject.SCHEMA, object_ref=record.object_ref,
            version=record.version, ciphertext_hash=record.ciphertext_hash, size_bytes=record.size_bytes,
            state='published')
        self.denied(self.store.read(stored, self.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_cipher_file_mutation_between_write_and_verify_cannot_issue_report(self):
        write = self.store.write_candidate
        def corrupt(*args):
            candidate = write(*args)
            path = self.path(candidate)
            original = path.read_bytes()
            path.write_bytes(original[:-1])
            return candidate
        with patch.object(self.store, 'write_candidate', side_effect=corrupt), \
             patch.object(self.auth, 'issue', wraps=self.auth.issue) as issue:
            self.denied(self.prepare())
            issue.assert_not_called()
        self.assertEqual(PrivateObject.objects.get().state, 'candidate')
