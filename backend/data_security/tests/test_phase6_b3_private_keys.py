"""No Django, database, files or backup claims: retained-key reads and actual root changes."""
from dataclasses import replace
import os
from unittest import TestCase
from unittest.mock import patch

from data_security.application.crypto_service import CryptoService
from data_security.application.private_files import PrivateFilePreparation
from data_security.contracts import (
    BASELINE_LIMITS, BoundedPayload, CipherEnvelope, Environment, KeyPurpose, KeyReference,
    KeyStatus, MediaType, ObjectContext, PayloadKind, ProtectionError, ReasonCode, SecretMaterial,
)
from data_security.contracts.schema import canonical_bytes
from data_security.tests.fixtures import examples
from data_security.tests.private_store_memory import MemoryPrivateStore


class PrivateRootRotationTests(TestCase):
    def setUp(self):
        self.old = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='enc-data/v1',
            purpose=KeyPurpose.DATA, version='v1', status=KeyStatus.ACTIVE)
        self.new = replace(self.old, key_ref='enc-data/v2', version='v2')
        self.read_only = replace(self.old, status=KeyStatus.READ_ONLY)
        self.entries = {key.key_ref: (key, os.urandom(32)) for key in (self.old, self.new)}
        self.context = examples()[ObjectContext]
        self.payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
            media_type=MediaType.BINARY, text=None, tree=None,
            binary=b'B3 synthetic private root rotation', limits=BASELINE_LIMITS)
        self.crypto = CryptoService(keys=self, service_identity='private-maintenance/test',
            random_bytes=os.urandom, environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.envelope = self.crypto.seal(self.payload, self.context, self.old)
        self.original_bytes = canonical_bytes(self.envelope)
        self.entries[self.old.key_ref] = (self.read_only, self.entries[self.old.key_ref][1])
        self.reader = CryptoService(keys=self, service_identity='private-maintenance/test',
            random_bytes=os.urandom, environment=Environment.TEST, limits=BASELINE_LIMITS,
            retained_data_keys=(self.read_only,))

    def resolve(self, key_ref, purpose, service_identity):
        # Mirrors FileKeyResolver's exact manifest-reference equality, without filesystem I/O.
        current, root = self.entries[key_ref.key_ref]
        if key_ref != current or purpose is not current.purpose:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                retryable=False, trace_id='private-maintenance/synthetic-key')
        return SecretMaterial(root, purpose)

    def test_retained_read_only_key_opens_without_rewriting_signed_envelope(self):
        result = self.reader.open(self.envelope, self.context, self.envelope.key)
        self.assertEqual(result, self.payload)
        self.assertEqual(canonical_bytes(self.envelope), self.original_bytes)
        self.assertIs(self.envelope.key.status, KeyStatus.ACTIVE)
        self.assertEqual(self.reader.open(self.envelope,
            replace(self.context, authorization_ref='renewed/read-grant'), self.envelope.key), self.payload)

    def test_actual_reseal_changes_root_ciphertext_and_path_not_object_aad(self):
        records, blobs = {}, {}
        store = MemoryPrivateStore(records=records, blobs=blobs, crypto=self.reader, environment=Environment.TEST)
        old_stored = store.verify(store.write_candidate(self.envelope, self.context), self.context)
        old_blob = blobs[old_stored.object_ref]
        payload = self.reader.open(self.envelope, self.context, self.envelope.key)
        preparation = PrivateFilePreparation(crypto=self.reader, data_key=self.new,
            store=store, limits=BASELINE_LIMITS)
        new_stored = preparation.prepare(payload, self.context)
        new_envelope = CipherEnvelope.from_json(blobs[new_stored.object_ref])
        self.assertNotEqual(new_stored.object_ref, old_stored.object_ref)
        self.assertNotEqual(new_envelope.ciphertext_and_tag, self.envelope.ciphertext_and_tag)
        self.assertNotEqual(new_envelope.kdf_salt, self.envelope.kdf_salt)
        self.assertNotEqual(new_envelope.nonce, self.envelope.nonce)
        self.assertEqual(new_envelope.key, self.new)
        self.assertEqual(self.reader.open(new_envelope, self.context, self.new), self.payload)
        self.assertEqual(blobs[old_stored.object_ref], old_blob)
        self.assertEqual(canonical_bytes(self.envelope), self.original_bytes)
        self.assertEqual(len(records), 2)
        self.assertEqual(store.read(new_stored, self.context).code, ReasonCode.AUTHORIZATION_DENIED)

    def test_read_only_key_cannot_seal_even_with_retained_read_mapping(self):
        with patch.object(self.reader, 'random_bytes', wraps=os.urandom) as randomness:
            for key in (self.read_only, self.old):
                self.assertEqual(self.reader.seal(self.payload, self.context, key).code, ReasonCode.KEY_UNAVAILABLE)
            randomness.assert_not_called()

    def test_unconfigured_and_retired_references_fail_without_fallback(self):
        self.assertEqual(self.crypto.open(self.envelope, self.context, self.envelope.key).code,
                         ReasonCode.KEY_UNAVAILABLE)
        retired = replace(self.old, status=KeyStatus.RETIRED)
        self.assertEqual(self.reader.open(self.envelope, self.context, retired).code, ReasonCode.KEY_UNAVAILABLE)
        self.assertEqual(canonical_bytes(self.envelope), self.original_bytes)

    def test_wrong_root_cross_object_and_ciphertext_tampering_never_open(self):
        for context in (replace(self.context, field_ref='resources/cover_image'),
                        replace(self.context, object_uuid='00000000-0000-0000-0000-000000000099')):
            self.assertEqual(self.reader.open(self.envelope, context, self.envelope.key).code,
                             ReasonCode.CIPHERTEXT_INVALID)
        corrupted = replace(self.envelope, ciphertext_and_tag=self.envelope.ciphertext_and_tag[:-1] +
            bytes([self.envelope.ciphertext_and_tag[-1] ^ 1]))
        self.assertEqual(self.reader.open(corrupted, self.context, corrupted.key).code, ReasonCode.CIPHERTEXT_INVALID)
        self.entries[self.old.key_ref] = (self.read_only, os.urandom(32))
        self.assertEqual(self.reader.open(self.envelope, self.context, self.envelope.key).code,
                         ReasonCode.CIPHERTEXT_INVALID)
