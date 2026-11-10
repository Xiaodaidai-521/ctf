"""Private upload preparation without Django or a business permission substitute."""
from dataclasses import replace
import os
from unittest import TestCase
from unittest.mock import patch

from data_security.application.crypto_service import CryptoService
from data_security.application.private_files import PrivateFilePreparation
from data_security.contracts import (
    BASELINE_LIMITS, BoundedPayload, CipherEnvelope, Environment, KeyStatus,
    MediaType, ObjectContext, PayloadKind, ProtectionError, ReasonCode, StoredObject,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key, text
from data_security.tests.private_store_memory import MemoryPrivateStore


class PrivateFilePreparationTests(TestCase):
    def setUp(self):
        self.context = examples()[ObjectContext]
        self.records, self.blobs = {}, {}
        self.crypto = CryptoService(keys=FakeKeys(), service_identity='private-upload/test',
            random_bytes=os.urandom, environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.store = MemoryPrivateStore(records=self.records, blobs=self.blobs,
            crypto=self.crypto, environment=Environment.TEST)
        self.prepare = PrivateFilePreparation(crypto=self.crypto, data_key=reference_key(),
            store=self.store, limits=BASELINE_LIMITS)
        self.payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
            media_type=MediaType.BINARY, text=None, tree=None, binary=b'synthetic upload', limits=BASELINE_LIMITS)

    def test_real_encryption_and_verification_do_not_publish_or_allow_reads(self):
        with patch.object(self.store, 'publish', wraps=self.store.publish) as publish:
            stored = self.prepare.prepare(self.payload, self.context)
            publish.assert_not_called()
        self.assertIs(type(stored), StoredObject)
        self.assertEqual(stored.state, 'verified')
        encoded = self.blobs[stored.object_ref]
        self.assertNotIn(self.payload.binary, encoded)
        envelope = CipherEnvelope.from_json(encoded)
        self.assertEqual(self.crypto.open(envelope, self.context, envelope.key), self.payload)
        self.assertEqual(self.store.read(stored, self.context).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual((len(self.records), len(self.blobs)), (1, 1))

    def test_file_and_cover_contexts_cannot_be_exchanged(self):
        original = self.prepare.prepare(self.payload, self.context)
        cover_context = replace(self.context, field_ref='resources/cover_image')
        cover = self.prepare.prepare(self.payload, cover_context)
        self.assertNotEqual(original.object_ref, cover.object_ref)
        envelope = CipherEnvelope.from_json(self.blobs[original.object_ref])
        result = self.crypto.open(envelope, cover_context, envelope.key)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, ReasonCode.CIPHERTEXT_INVALID)
        self.assertEqual(len(self.records), 2)

    def test_wrong_kind_or_limits_fail_before_encryption(self):
        cases = [(text('safe'), ReasonCode.INVALID_TYPE),
            (replace(self.payload, limits=replace(BASELINE_LIMITS, max_bytes=1024)), ReasonCode.LIMIT_EXCEEDED)]
        with patch.object(self.crypto, 'seal', wraps=self.crypto.seal) as seal:
            for payload, code in cases:
                result = self.prepare.prepare(payload, self.context)
                self.assertEqual(result.code, code)
                self.assertFalse(result.retryable)
                self.assertEqual(result.trace_id, 'private-file/prepare')
            seal.assert_not_called()
        self.assertEqual((len(self.records), len(self.blobs)), (0, 0))

    def test_port_errors_are_returned_unchanged_without_later_steps(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
            retryable=False, trace_id='private-upload/synthetic-failure')
        for target, method in ((self.crypto, 'seal'), (self.store, 'write_candidate'), (self.store, 'verify')):
            with self.subTest(method=method), patch.object(target, method, return_value=failure), \
                    patch.object(self.store, 'publish', wraps=self.store.publish) as publish:
                self.assertIs(self.prepare.prepare(self.payload, self.context), failure)
                publish.assert_not_called()
        self.assertEqual([stored.state for _, stored in self.records.values()], ['candidate'])

    def test_tampering_between_write_and_verify_leaves_unreadable_candidate(self):
        write = self.store.write_candidate

        def corrupt(envelope, context):
            stored = write(envelope, context)
            self.blobs[stored.object_ref] = self.blobs[stored.object_ref][:-1]
            return stored

        with patch.object(self.store, 'write_candidate', side_effect=corrupt):
            result = self.prepare.prepare(self.payload, self.context)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, ReasonCode.CIPHERTEXT_INVALID)
        self.assertEqual([stored.state for _, stored in self.records.values()], ['candidate'])

    def test_read_only_key_cannot_prepare_new_upload(self):
        self.prepare.data_key = replace(reference_key(), status=KeyStatus.READ_ONLY)
        result = self.prepare.prepare(self.payload, self.context)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, ReasonCode.KEY_UNAVAILABLE)
        self.assertEqual((len(self.records), len(self.blobs)), (0, 0))
