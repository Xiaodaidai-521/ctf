"""Retained upload intention failure windows; run only in the isolated PostgreSQL job."""
import multiprocessing
import os
from pathlib import Path
import signal
from unittest.mock import patch

from django.db import DatabaseError, connection, connections, transaction
from django.test import TransactionTestCase

from audit.models import SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject
from data_security.contracts import ContractViolation, ProtectionError, ReasonCode

from .models import Resource
from .test_phase6_b2_fixtures import PrivateFileHTTPFixture


class PrivateUploadUnknownTests(PrivateFileHTTPFixture, TransactionTestCase):
    def test_committed_retry_does_not_encrypt_create_or_audit_twice(self):
        first = self.upload()
        self.assertEqual(first.status_code, 201, first.data)
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        with patch.object(self.preparation.crypto, 'seal', side_effect=AssertionError('reencrypted retry')), \
             patch.object(Resource.objects, 'create', side_effect=AssertionError('duplicate resource')), \
             patch.object(self.uploads.audit, 'record', side_effect=AssertionError('duplicate upload audit')):
            retry = self.upload()
            self.assertEqual(retry.status_code, 201, retry.data)
            self.assertEqual(self.operation().data['state'], 'committed')
        self.assertEqual(first.data, retry.data)
        self.assertEqual(Resource.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, before)

    def test_same_operation_with_different_content_or_metadata_is_conflict(self):
        self.assertEqual(self.upload().status_code, 201)
        for change in ('metadata', 'content', 'cover'):
            with self.subTest(change=change):
                if change == 'content':
                    self.content += b'changed'
                data = self.data(cover=change == 'cover')
                if change == 'metadata':
                    data['title'] = '另一份合成资料'
                result = self.upload(data=data)
                self.assertEqual(result.status_code, 409)
                self.assertEqual(result.data['code'], 'IDEMPOTENCY_CONFLICT')
        self.assertEqual((Resource.objects.count(), PrivateObject.objects.count()), (1, 1))

    def test_intention_and_exact_filename_are_committed_before_ciphertext_io(self):
        write = self.preparation.store.write_candidate

        def observed(envelope, context):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(connection.get_autocommit())
            operation = PrivateFileOperation.objects.get()
            self.assertEqual(str(operation.object_uuid), context.object_uuid)
            item = operation.files[context.field_ref]
            self.assertEqual(item['context'], context.to_wire())
            self.assertEqual(item['stored']['state'], 'candidate')
            result = write(envelope, context)
            self.assertEqual(result.object_ref, item['stored']['object_ref'])
            return result

        with patch.object(self.preparation.store, 'write_candidate', side_effect=observed) as called:
            self.assertEqual(self.upload(data=self.data(cover=True)).status_code, 201)
        self.assertEqual(called.call_count, 2)

    def test_fsync_before_row_confirmation_loss_recovers_exact_file_without_reencryption(self):
        with patch.object(PrivateObject.objects, 'get_or_create', side_effect=DatabaseError('synthetic lost row')):
            response = self.upload()
        self.assertEqual(response.data['code'], 'DELIVERY_UNKNOWN')
        operation = PrivateFileOperation.objects.get()
        self.assertEqual(operation.state, 'preparing')
        self.assertFalse(PrivateObject.objects.exists())
        self.assertFalse(Resource.objects.exists())
        before = {path.name: path.read_bytes() for path in self.root.glob('*.sealed')}
        self.assertEqual(len(before), 1)
        fresh = assemble(config_path=self.config_path)['private_uploads']['resources']
        with patch.object(fresh.prepare.__self__.crypto, 'seal', side_effect=AssertionError('reencrypted recovery')):
            recovered = fresh.reconcile_operation(user=self.teacher, operation_id=self.operation_id)
        self.assertNotIsInstance(recovered, ProtectionError)
        self.assertEqual(recovered.state, 'prepared')
        with patch.object(self.preparation.crypto, 'seal', side_effect=AssertionError('reencrypted retry')):
            self.assertEqual(self.upload().status_code, 201)
        self.assertEqual((PrivateObject.objects.count(), Resource.objects.count()), (1, 1))
        self.assertEqual({path.name: path.read_bytes() for path in self.root.glob('*.sealed')}, before)

    def test_real_business_commit_ack_loss_is_positive_not_zero_or_duplicate(self):
        commit, lost = connection.commit, False

        def commit_then_lose():
            nonlocal lost
            should_lose = not lost and PrivateFileOperation.objects.filter(state='committed').exists()
            result = commit()
            if should_lose:
                lost = True
                raise DatabaseError('synthetic confirmation lost after commit')
            return result

        with patch.object(connection, 'commit', side_effect=commit_then_lose):
            result = self.upload()
        self.assertTrue(lost)
        self.assertEqual(result.data['code'], 'DELIVERY_UNKNOWN')
        self.assertEqual(self.operation().data['state'], 'committed')
        self.assertEqual(self.upload().status_code, 201)
        self.assertEqual((Resource.objects.count(), PrivateObject.objects.count(), SecurityAuditRecord.objects.count()), (1, 1, 1))

    def test_partial_cover_failure_requires_explicit_abort_before_exact_cleanup(self):
        write = self.preparation.store.write_candidate

        def fail_cover(envelope, context):
            if context.field_ref == 'resources/cover_image':
                raise OSError('synthetic cover write failure')
            return write(envelope, context)

        with patch.object(self.preparation.store, 'write_candidate', side_effect=fail_cover):
            self.assertEqual(self.upload(data=self.data(cover=True)).data['code'], 'DELIVERY_UNKNOWN')
        self.assertEqual(self.operation().data['code'], 'DELIVERY_UNKNOWN')
        self.assertFalse(Resource.objects.exists())
        self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)
        self.assertEqual(self.operation(cleanup=True).data['state'], 'cleaned')
        self.assertEqual(list(self.root.glob('*.sealed')), [])
        self.assertEqual(PrivateFileOperation.objects.get().result_ref, '')
        self.assertEqual(PrivateObject.objects.get().state, 'retired')

    def test_key_refusal_has_durable_intent_and_can_be_explicitly_aborted(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
            retryable=False, trace_id='b2/key-refusal')
        with patch.object(self.preparation.crypto.keys, 'resolve', return_value=failure):
            self.assertEqual(self.upload().data['code'], 'KEY_UNAVAILABLE')
        self.assertEqual(PrivateFileOperation.objects.get().files, {})
        self.assertEqual(self.operation().data['code'], 'DELIVERY_UNKNOWN')
        self.assertFalse(PrivateObject.objects.exists())
        self.assertEqual(self.operation(cleanup=True).data['state'], 'cleaned')
        self.assertEqual(self.upload().status_code, 403)

    def test_missing_intention_never_authorizes_cleanup_of_unregistered_files(self):
        path = self.root / ('0' * 64 + '.sealed')
        path.write_bytes(b'synthetic retained ciphertext fixture')
        path.chmod(0o600)
        for cleanup in (False, True):
            self.assertEqual(self.operation(cleanup=cleanup).data['code'], 'DELIVERY_UNKNOWN')
        self.assertEqual(path.read_bytes(), b'synthetic retained ciphertext fixture')
        self.assertFalse(PrivateFileOperation.objects.exists())

    def test_live_operation_gate_blocks_observation_and_cleanup_without_timeout_takeover(self):
        self.assertEqual(self.upload().status_code, 201)
        row = PrivateFileOperation.objects.get()
        with self.uploads.operations.claim(operation_ref=row.operation_ref, actor_ref=row.actor_ref,
                scope_ref=row.scope_ref):
            self.assertEqual(self.operation().data['code'], 'DELIVERY_UNKNOWN')
            self.assertEqual(self.operation(cleanup=True).data['code'], 'DELIVERY_UNKNOWN')
            self.assertEqual(self.upload().data['code'], 'DELIVERY_UNKNOWN')
            self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)
        self.assertEqual(self.operation().data['state'], 'committed')

    def test_cleanup_ack_loss_keeps_tombstone_then_resumes_without_audit_replay(self):
        self.assertEqual(self.upload().status_code, 201)
        unlink = Path.unlink

        def unlink_then_lose(path, *args, **kwargs):
            result = unlink(path, *args, **kwargs)
            if path.suffix == '.sealed':
                raise OSError('synthetic unlink confirmation loss')
            return result

        with patch.object(Path, 'unlink', unlink_then_lose):
            result = self.operation(cleanup=True)
        self.assertEqual(result.data['code'], 'DELIVERY_UNKNOWN')
        self.assertEqual(PrivateFileOperation.objects.get().state, 'retired')
        self.assertEqual(list(self.root.glob('*.sealed')), [])
        with patch.object(self.uploads.audit, 'record', side_effect=AssertionError('replayed retirement audit')):
            self.assertEqual(self.operation(cleanup=True).data['state'], 'cleaned')
        self.assertEqual(SecurityAuditRecord.objects.count(), 2)

    def test_clean_requires_terminal_tombstone_and_refuses_published_object(self):
        self.assertEqual(self.upload().status_code, 201)
        row = PrivateFileOperation.objects.get()
        with self.uploads.operations.claim(operation_ref=row.operation_ref, actor_ref=row.actor_ref,
                scope_ref=row.scope_ref) as operation:
            with self.assertRaises(ContractViolation):
                self.uploads.operations.clean(operation)
        PrivateObject.objects.update(state='published')
        response = self.operation(cleanup=True)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(PrivateObject.objects.get().state, 'published')
        self.assertEqual(PrivateFileOperation.objects.get().state, 'retired')
        self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)

    def test_outer_transaction_is_rejected_before_operation_or_ciphertext_creation(self):
        with transaction.atomic():
            result = self.upload()
        self.assertEqual(result.data['code'], 'DELIVERY_UNKNOWN')
        self.assertFalse(PrivateFileOperation.objects.exists())
        self.assertFalse(PrivateObject.objects.exists())
        self.assertFalse(Resource.objects.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def _crash(self, stage):
        def run():
            def stop(*args, **kwargs):
                os.kill(os.getpid(), signal.SIGKILL)

            if stage == 'fsync':
                target, method = PrivateObject.objects, 'get_or_create'
            else:
                target, method = Resource.objects, 'create'
            with patch.object(target, method, side_effect=stop):
                self.upload()

        connections.close_all()
        worker = multiprocessing.get_context('fork').Process(target=run)
        worker.start()
        try:
            worker.join(30)
            self.assertEqual(worker.exitcode, -signal.SIGKILL)
        finally:
            if worker.is_alive():
                worker.kill()
                worker.join()
            worker.close()
        self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)
        self.assertEqual(PrivateFileOperation.objects.count(), 1)
        self.assertFalse(Resource.objects.exists())
        fresh = assemble(config_path=self.config_path)['private_uploads']['resources']
        result = fresh.reconcile_operation(user=self.teacher, operation_id=self.operation_id)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result.state, 'prepared')
        result = fresh.reconcile_operation(user=self.teacher, operation_id=self.operation_id, cleanup=True)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result.state, 'cleaned')
        self.assertEqual(list(self.root.glob('*.sealed')), [])
        self.assertEqual(len(list(self.root.glob('*.lock'))), 1)

    def test_killed_after_fsync_releases_gate_and_recovers_then_cleans_exact_orphan(self):
        self._crash('fsync')

    def test_killed_after_verification_releases_gate_and_recovers_then_cleans_candidate(self):
        self._crash('verified')
