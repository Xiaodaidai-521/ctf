"""Measured explicit upload composition, not public-route or swap protection acceptance."""
import hashlib
import json
import os
from pathlib import Path
import resource as process_resource
from time import perf_counter
import tracemalloc
from unittest.mock import patch

from django.core.exceptions import RequestDataTooBig
from django.db import connection
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry
from data_security.adapters.django.uploads import BoundedUploadHandler
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import BASELINE_LIMITS, ProtectionError, ReasonCode
from .models import Resource
from .test_phase6_private_uploads import PrivateResourceUploadFixture


class PrivateResourceCapacityTests(PrivateResourceUploadFixture, TransactionTestCase):
    def test_twenty_mib_full_upload_records_time_memory_and_ciphertext_only(self):
        markers = (b'capacity-student@example.invalid', b'192.0.2.71', b'4111111111111111')
        line = b' '.join(markers) + b'\n'
        size = BASELINE_LIMITS.max_bytes
        self.assertEqual(size, 20 * 1024 * 1024)
        self.content = (line * (size // len(line) + 1))[:size]
        expected_hash = hashlib.sha256(self.content).hexdigest()
        opened = self.preparation.crypto.open
        def checked_open(envelope, context, key):
            self.assertFalse(connection.in_atomic_block)
            result = opened(envelope, context, key)
            self.assertNotIsInstance(result, ProtectionError)
            self.assertEqual(hashlib.sha256(result.binary).hexdigest(), expected_hash)
            return result
        rss_before = process_resource.getrusage(process_resource.RUSAGE_SELF).ru_maxrss * 1024
        # Includes request construction and multipart/owner/crypto/store/audit, not input generation.
        tracemalloc.start()
        try:
            started = perf_counter()
            with patch.object(self.preparation.crypto, 'open', side_effect=checked_open) as verify:
                response = self.post()
            elapsed = perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        rss_after = process_resource.getrusage(process_resource.RUSAGE_SELF).ru_maxrss * 1024
        self.assertEqual(response.status_code, 201)
        verify.assert_called_once()
        resource = Resource.objects.get()
        self.assertEqual((resource.file.name, resource.cover_image.name, resource.file_size, resource.status),
                         ('', '', size, 'pending'))
        references = self.uploads.authenticated_references(user=self.teacher, resource_id=resource.pk)
        self.assertIsInstance(references, tuple)
        self.assertEqual(len(references), 1)
        field, context, stored = references[0]
        self.assertEqual((field, stored.state), ('file', 'verified'))
        self.assertEqual(self.preparation.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        files = list(self.root.iterdir())
        self.assertEqual(len(files), 1)
        encoded = files[0].read_bytes()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), stored.ciphertext_hash)
        self.assertEqual(len(encoded), stored.size_bytes)
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        for marker in markers:
            self.assertNotIn(marker, encoded)
        self.assertEqual(list(self.media.iterdir()), [])
        observation = {'scope': 'explicit resource multipart upload through new-chain PROTECTION commit',
            'input_bytes': size, 'input_sha256': expected_hash, 'upload_seconds': elapsed,
            'upload_mib_per_second': size / 1024 / 1024 / elapsed, 'python_peak_allocated_bytes': peak,
            'runner_lifetime_peak_rss_before_bytes': rss_before,
            'runner_lifetime_peak_rss_after_bytes': rss_after,
            'rss_scope': 'Linux test-runner lifetime high-water mark, not operation-only or process-tree RSS',
            'input_generation_in_timing': False, 'multipart_construction_in_timing': True,
            'timing_includes_tracemalloc': True, 'post_upload_reference_and_file_scan_in_timing': False,
            'ciphertext_bytes': stored.size_bytes, 'ciphertext_sha256': stored.ciphertext_hash,
            'private_files': 1, 'private_state': stored.state, 'new_chain_events': 1,
            'ordinary_upload_spool_calls': 0, 'ordinary_filefield_save_calls': 0,
            'persistent_marker_hits': 0, 'public_media_files': 0, 'upload_buffers_closed': True,
            'public_route_enabled': False, 'swap_protection_verified': False,
            'crash_cleanup_verified': False, 'full_delivery_verified': False}
        if target := os.environ.get('DS_PHASE6_RESOURCE_CAPACITY_OBSERVATIONS'):
            path = Path(target)
            self.assertEqual(path.parent.resolve(),
                             Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-06'))
            with path.open('x') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(observation, stream, sort_keys=True, indent=2)
                stream.write('\n')

    def test_twenty_mib_plus_one_is_rejected_before_preparation_and_closes_active_buffer(self):
        self.content = b'x' * (BASELINE_LIMITS.max_bytes + 1)
        closed = []
        close = BoundedUploadHandler.close
        def checked_close(handler):
            close(handler)
            closed.append((len(handler.buffers), all(buffer.closed for buffer in handler.buffers), handler.size))
        with patch.object(BoundedUploadHandler, 'close', checked_close), \
                patch.object(self.uploads, 'prepare', side_effect=AssertionError('oversized input prepared')) as prepare:
            with self.assertRaises(RequestDataTooBig):
                self.post()
            prepare.assert_not_called()
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0][:2], (1, True))
        self.assertLessEqual(closed[0][2], BASELINE_LIMITS.max_bytes)
        self.assertEqual(Resource.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.count(), 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(list(self.media.iterdir()), [])
