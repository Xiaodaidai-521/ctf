"""Offline synthetic field-crypto checks; no Django setup or database required."""
from dataclasses import replace
import json
import os
import secrets
import unittest
from unittest.mock import patch

from ctfsafe import encryption
from data_security.application.crypto_service import CryptoService
from data_security.contracts import BASELINE_LIMITS, KeyPurpose, KeyStatus, ObjectContext, ReasonCode
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key


class FieldCryptoBoundaryTests(unittest.TestCase):
    def setUp(self):
        binding = patch.object(encryption, '_binding', None)
        binding.start()
        self.addCleanup(binding.stop)
        self.context = examples()[ObjectContext]
        self.key = reference_key()
        self.keys = FakeKeys()
        self.crypto = CryptoService(keys=self.keys, service_identity='service/field-test',
            random_bytes=secrets.token_bytes, environment=self.context.environment, limits=BASELINE_LIMITS)

    def bind(self):
        encryption.bind_field_crypto(self.crypto, key_ref=self.key, limits=BASELINE_LIMITS)

    def test_unbound_never_derives_from_environment_even_for_empty_fields(self):
        with patch.dict(os.environ, {'SECRET_KEY': 'synthetic-signing-only',
                                      'FERNET_KEY': 'synthetic-unused-key'}):
            for operation in (encryption.encrypt_field, encryption.decrypt_field):
                for value in ('', 'synthetic-field'):
                    with self.subTest(operation=operation.__name__, empty=not value):
                        with self.assertRaisesRegex(encryption.EncryptionError, 'FIELD_CRYPTO_NOT_BOUND'):
                            operation(value)
        self.assertFalse(self.keys.calls)

    def test_binding_requires_data_reference_and_explicit_limits(self):
        with self.assertRaisesRegex(encryption.EncryptionError, 'FIELD_DATA_KEY_REQUIRED'):
            encryption.bind_field_crypto(self.crypto, key_ref=reference_key(KeyPurpose.FRAMEWORK),
                                         limits=BASELINE_LIMITS)
        with self.assertRaisesRegex(encryption.EncryptionError, 'FIELD_LIMITS_REQUIRED'):
            encryption.bind_field_crypto(self.crypto, key_ref=self.key)

    def test_context_is_required_including_empty_values(self):
        self.bind()
        for operation in (encryption.encrypt_field, encryption.decrypt_field):
            with self.assertRaisesRegex(encryption.EncryptionError, 'FIELD_OBJECT_CONTEXT_REQUIRED'):
                operation('')
        self.assertFalse(self.keys.calls)

    def test_new_format_round_trip_preserves_unicode_and_empty_value(self):
        self.bind()
        for value in ('synthetic-field-甲', ''):
            ciphertext = encryption.encrypt_field(value, object_context=self.context)
            self.assertTrue(ciphertext.startswith('ds-field.v1:'))
            if value:
                self.assertNotIn(value, ciphertext)
            self.assertEqual(encryption.decrypt_field(ciphertext, object_context=self.context), value)
        self.assertTrue(all(call[0] == self.key and call[1] is KeyPurpose.DATA for call in self.keys.calls))

    def test_randomized_ciphertexts_do_not_reuse_salt_or_nonce(self):
        self.bind()
        values = [encryption.encrypt_field('synthetic-same', object_context=self.context) for _ in range(2)]
        envelopes = [json.loads(value.split(':', 1)[1]) for value in values]
        self.assertNotEqual(envelopes[0]['kdf_salt'], envelopes[1]['kdf_salt'])
        self.assertNotEqual(envelopes[0]['nonce'], envelopes[1]['nonce'])
        self.assertNotEqual(values[0], values[1])

    def test_wrong_object_and_tampering_fail_without_plaintext_fallback(self):
        self.bind()
        ciphertext = encryption.encrypt_field('synthetic-secret-field', object_context=self.context)
        with self.assertRaises(encryption.EncryptionError):
            encryption.decrypt_field(ciphertext, object_context=replace(self.context, field_ref='field/other'))
        envelope = json.loads(ciphertext.split(':', 1)[1])
        nonce = envelope['nonce']
        envelope['nonce'] = ('A' if nonce[0] != 'A' else 'B') + nonce[1:]
        with self.assertRaises(encryption.EncryptionError):
            encryption.decrypt_field('ds-field.v1:' + json.dumps(envelope), object_context=self.context)

    def test_legacy_format_requires_separate_migration_without_trying_keys(self):
        self.bind()
        for ciphertext in ('gAAAAA-synthetic-legacy-fernet', '', 'plain-old-field', 'ds-field.v2:{}'):
            with self.subTest(format=ciphertext[:8]):
                with self.assertRaisesRegex(encryption.EncryptionError, 'FIELD_FORMAT_MIGRATION_REQUIRED'):
                    encryption.decrypt_field(ciphertext, object_context=self.context)
        self.assertFalse(self.keys.calls)

    def test_missing_or_retired_key_is_not_replaced_by_framework_key(self):
        self.bind()
        self.keys.error = ReasonCode.KEY_UNAVAILABLE
        with self.assertRaises(encryption.EncryptionError):
            encryption.encrypt_field('synthetic-field', object_context=self.context)
        self.keys.error = None
        self.key = replace(self.key, status=KeyStatus.RETIRED)
        self.bind()
        with self.assertRaises(encryption.EncryptionError):
            encryption.encrypt_field('synthetic-field', object_context=self.context)

    def test_invalid_payload_and_invalid_envelope_return_fixed_errors(self):
        self.bind()
        with self.assertRaises(encryption.EncryptionError):
            encryption.encrypt_field('x' * (BASELINE_LIMITS.max_text_chars + 1), object_context=self.context)
        with self.assertRaisesRegex(encryption.EncryptionError, '^FIELD_CIPHERTEXT_INVALID$'):
            encryption.decrypt_field('ds-field.v1:synthetic-invalid-json', object_context=self.context)

    def test_unbinding_closes_previously_enabled_facade(self):
        self.bind()
        encryption.bind_field_crypto(None)
        with self.assertRaisesRegex(encryption.EncryptionError, 'FIELD_CRYPTO_NOT_BOUND'):
            encryption.encrypt_field('', object_context=self.context)
