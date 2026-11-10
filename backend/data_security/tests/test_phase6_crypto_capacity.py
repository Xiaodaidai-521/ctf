"""The object limit measures raw file bytes, not base64/JSON envelope overhead."""
from dataclasses import replace
import os
import unittest

from data_security.application.crypto_service import CryptoService
from data_security.contracts import (
    BASELINE_LIMITS, BoundedPayload, CipherEnvelope, ContractViolation, Environment, MediaType, ObjectContext,
    PayloadKind, ProtectionError, ReasonCode, canonical_bytes,
)
from data_security.contracts.crypto import BINARY_CIPHER_FORMAT
from data_security.contracts.schema import MAX_BYTES, MAX_CRYPTO_FRAME_BYTES
from data_security.core import crypto
from data_security.tests.fixtures import dto, examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key, root_key, text


class CryptoCapacityTests(unittest.TestCase):
    def test_full_twenty_mib_binary_seals_wire_roundtrips_and_opens(self):
        payload = dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.BINARY,
            text=None, tree=None, binary=b'F' * BASELINE_LIMITS.max_bytes, limits=BASELINE_LIMITS)
        service = CryptoService(keys=FakeKeys(), service_identity='capacity/test', random_bytes=os.urandom,
            environment=Environment.TEST, limits=BASELINE_LIMITS)
        context, key = examples()[ObjectContext], reference_key()
        sealed = service.seal(payload, context, key)
        self.assertIsInstance(sealed, CipherEnvelope)
        decoded = CipherEnvelope.from_json(canonical_bytes(sealed))
        self.assertEqual(service.open(decoded, context, key), payload)
        self.assertEqual(sealed.format_version, BINARY_CIPHER_FORMAT)
        self.assertLessEqual(len(sealed.ciphertext_and_tag), MAX_CRYPTO_FRAME_BYTES + 16)

    def test_binary_media_empty_and_stricter_limits_roundtrip(self):
        context, key = examples()[ObjectContext], reference_key()
        for media in (MediaType.BINARY, MediaType.CSV, MediaType.XLSX):
            for binary in (b'', b'\x00\xffabc'):
                payload = dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=media,
                    text=None, tree=None, binary=binary, limits=BASELINE_LIMITS)
                service = CryptoService(keys=FakeKeys(), service_identity='capacity/test', random_bytes=os.urandom,
                    environment=Environment.TEST, limits=replace(BASELINE_LIMITS, max_bytes=5))
                sealed = service.seal(payload, context, key)
                self.assertIsInstance(sealed, CipherEnvelope)
                self.assertEqual(service.open(sealed, context, key), payload)
                too_large = replace(payload, binary=b'123456')
                self.assertEqual(service.seal(too_large, context, key).code, ReasonCode.LIMIT_EXCEEDED)

    def test_business_limit_and_original_envelope_limit_are_unchanged(self):
        with self.assertRaises(ContractViolation):
            dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.BINARY,
                text=None, tree=None, binary=b'F' * (MAX_BYTES + 1), limits=BASELINE_LIMITS)
        with self.assertRaises(ContractViolation):
            replace(examples()[CipherEnvelope], ciphertext_and_tag=b'F' * (MAX_BYTES + 17))
        with self.assertRaises(ContractViolation):
            replace(examples()[CipherEnvelope], format_version=BINARY_CIPHER_FORMAT,
                    ciphertext_and_tag=b'F' * (MAX_CRYPTO_FRAME_BYTES + 17))

    def test_existing_json_framed_binary_is_still_readable(self):
        context, key = examples()[ObjectContext], reference_key()
        payload = dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.CSV,
            text=None, tree=None, binary=b'a,b\n1,2\n', limits=BASELINE_LIMITS)
        old = crypto.seal(canonical_bytes(payload, include_payload=True), context, key,
            root_key(key.purpose.value), salt=os.urandom(16), nonce=os.urandom(12))
        service = CryptoService(keys=FakeKeys(), service_identity='capacity/test', random_bytes=os.urandom,
            environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.assertEqual(service.open(old, context, key), payload)
        changed_version = replace(old, format_version=BINARY_CIPHER_FORMAT)
        self.assertEqual(service.open(changed_version, context, key).code, ReasonCode.CIPHERTEXT_INVALID)

    def test_authenticated_malformed_frames_still_fail_before_return(self):
        context, key = examples()[ObjectContext], reference_key()
        service = CryptoService(keys=FakeKeys(), service_identity='capacity/test', random_bytes=os.urandom,
            environment=Environment.TEST, limits=replace(BASELINE_LIMITS, max_bytes=5))
        binary = dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.BINARY,
            text=None, tree=None, binary=b'', limits=BASELINE_LIMITS)
        header = canonical_bytes(binary, include_payload=True)
        wrong_type = canonical_bytes(text('x'), include_payload=True)
        populated = canonical_bytes(replace(binary, binary=b'x'), include_payload=True)
        frames = (b'', b'\0' * 4, (4093).to_bytes(4, 'big') + b'x' * 4093,
            (100).to_bytes(4, 'big') + b'x',
            len(wrong_type).to_bytes(4, 'big') + wrong_type,
            len(populated).to_bytes(4, 'big') + populated,
            len(header).to_bytes(4, 'big') + header + b'123456')
        for frame in frames:
            sealed = crypto.seal(frame, context, key, root_key(key.purpose.value),
                salt=os.urandom(16), nonce=os.urandom(12), format_version=BINARY_CIPHER_FORMAT)
            self.assertIsInstance(service.open(sealed, context, key), ProtectionError)

    def test_binary_tag_and_format_are_authenticated(self):
        context, key = examples()[ObjectContext], reference_key()
        payload = dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.BINARY,
            text=None, tree=None, binary=b'file', limits=BASELINE_LIMITS)
        service = CryptoService(keys=FakeKeys(), service_identity='capacity/test', random_bytes=os.urandom,
            environment=Environment.TEST, limits=BASELINE_LIMITS)
        sealed = service.seal(payload, context, key)
        for changed in (replace(sealed, format_version=crypto.FORMAT_VERSION),
                        replace(sealed, ciphertext_and_tag=sealed.ciphertext_and_tag[:-1] +
                                bytes([sealed.ciphertext_and_tag[-1] ^ 1]))):
            self.assertEqual(service.open(changed, context, key).code, ReasonCode.CIPHERTEXT_INVALID)
