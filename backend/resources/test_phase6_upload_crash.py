"""Abrupt exits of owned upload workers; retained ciphertext is not cleanup completion."""
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import signal
from unittest.mock import patch

from django.db import connection, connections
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry
from ctf_backend.security_bootstrap import assemble_resource_uploads
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import (
    BASELINE_LIMITS, CipherEnvelope, ObjectContext, ProtectionError, ReasonCode, StoredObject,
)
from .models import Resource
from .test_phase6_private_uploads import PrivateResourceUploadFixture


class PrivateResourceCrashTests(PrivateResourceUploadFixture, TransactionTestCase):
    def _crash_upload(self, stage):
        markers = (b'crash-student@example.invalid', b'192.0.2.72', b'4111111111111111')
        line = b' '.join(markers) + b'\n'
        size = BASELINE_LIMITS.max_bytes
        self.content = (line * (size // len(line) + 1))[:size]
        context = ObjectContext(schema_version=ObjectContext.SCHEMA,
            project_ref=self.uploads.project_ref, environment=self.uploads.environment,
            object_uuid='00000000-0000-4000-8000-000000000072', object_version='1',
            field_ref='resources/file', authorization_ref=f'resource-upload/user-{self.teacher.pk}')

        def upload():
            def crash(*args, **kwargs):
                os.kill(os.getpid(), signal.SIGKILL)

            create = self.uploads.create
            def crash_after_commit(*args, **kwargs):
                result = create(*args, **kwargs)
                self.assertIsInstance(result, Resource)
                self.assertFalse(connection.in_atomic_block)
                crash()

            if stage == 'ciphertext':
                target, method, effect = PrivateObject.objects, 'get_or_create', crash
            elif stage == 'verified':
                target, method, effect = Resource.objects, 'create', crash
            else:
                target, method, effect = self.uploads, 'create', crash_after_commit
            with patch.object(self.uploads, 'object_id', return_value=context.object_uuid), \
                    patch.object(target, method, side_effect=effect):
                self.post()

        # Never share an open PostgreSQL socket with the forked test-owned worker.
        self.assertFalse(connection.in_atomic_block)
        connections.close_all()
        worker = multiprocessing.get_context('fork').Process(target=upload)
        worker.start()
        try:
            worker.join(60)
            self.assertEqual(worker.exitcode, -signal.SIGKILL)
        finally:
            if worker.is_alive():
                worker.kill()
                worker.join()
            worker.close()

        paths = list(self.root.iterdir())
        self.assertEqual(len(paths), 1)
        path = paths[0]
        encoded = path.read_bytes()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for marker in markers:
            self.assertNotIn(marker, encoded)
        self.assertEqual(list(self.media.iterdir()), [])
        stored = StoredObject(schema_version=StoredObject.SCHEMA,
            object_ref='private/' + path.stem, version='1', size_bytes=len(encoded),
            ciphertext_hash=hashlib.sha256(encoded).hexdigest(), state='published')
        restarted = assemble_resource_uploads(config_path=self.config_path,
            private_root=self.root, project_ref=self.uploads.project_ref)
        preparation = restarted.prepare.__self__
        self.assertEqual(preparation.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)
        envelope = CipherEnvelope.from_json(encoded)
        opened = preparation.crypto.open(envelope, context, envelope.key)
        self.assertNotIsInstance(opened, ProtectionError)
        self.assertEqual(hashlib.sha256(opened.binary).digest(), hashlib.sha256(self.content).digest())
        self.assertEqual(PrivateObject.objects.count(), int(stage != 'ciphertext'))
        self.assertEqual(Resource.objects.count(), int(stage == 'committed'))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), int(stage == 'committed'))
        if stage != 'ciphertext':
            record = PrivateObject.objects.get()
            self.assertEqual((record.object_ref, record.ciphertext_hash, record.size_bytes, record.state),
                             (stored.object_ref, stored.ciphertext_hash, stored.size_bytes, 'verified'))
        if stage == 'committed':
            resource = Resource.objects.get()
            self.assertEqual((resource.file.name, resource.cover_image.name, resource.status), ('', '', 'pending'))
            for _ in range(2):
                references = restarted.reconcile(user=self.teacher, resource_id=resource.pk)
                self.assertIsInstance(references, tuple)
                self.assertEqual(len(references), 1)
                self.assertEqual((references[0][0], references[0][2].ciphertext_hash, references[0][2].state),
                                 ('file', stored.ciphertext_hash, 'verified'))
            self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
            self.assertEqual(Resource.objects.count(), 1)
            self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertEqual(list(self.root.iterdir()), paths)
        self.assertEqual(path.read_bytes(), encoded)
        if target := os.environ.get('DS_PHASE6_RESOURCE_CRASH_OBSERVATIONS'):
            output = Path(target).with_name(Path(target).stem + '-' + stage + '.json')
            self.assertEqual(output.parent.resolve(),
                             Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-06'))
            observation = {'stage': stage, 'worker_exit_signal': 'SIGKILL', 'input_bytes': size,
                'ciphertext_bytes': len(encoded), 'ciphertext_sha256': stored.ciphertext_hash,
                'private_files': 1, 'private_rows': PrivateObject.objects.count(),
                'resource_rows': Resource.objects.count(), 'new_chain_events': AuthenticatedAuditEntry.objects.count(),
                'private_state': 'unregistered' if stage == 'ciphertext' else 'verified',
                'persistent_marker_hits': 0, 'public_media_files': 0, 'read_denied_after_reassembly': True,
                'ciphertext_authenticated_after_reassembly': True, 'residue_preserved_after_checks': True,
                'normal_worker_finally_executed': False, 'product_crash_cleanup_verified': False,
                'swap_protection_verified': False, 'public_route_enabled': False,
                'cleanup_scope': 'Only parent-owned fixture cleanup after assertions; not product cleanup.'}
            with output.open('x') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(observation, stream, sort_keys=True, indent=2)
                stream.write('\n')

    def test_crash_after_ciphertext_fsync_before_registration_retains_unreadable_orphan(self):
        self._crash_upload('ciphertext')

    def test_crash_after_verification_before_resource_commit_retains_unreadable_candidate(self):
        self._crash_upload('verified')

    def test_crash_after_resource_commit_before_response_preserves_observable_protection(self):
        self._crash_upload('committed')
