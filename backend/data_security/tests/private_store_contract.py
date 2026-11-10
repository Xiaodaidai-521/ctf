"""Shared PrivateStore behavior, independent of its database/filesystem representation."""
from dataclasses import replace
import hashlib
import os
from unittest.mock import patch

from data_security.application.crypto_service import CryptoService
from data_security.contracts import (
    BASELINE_LIMITS, CipherEnvelope, Environment, KeyPurpose, ObjectContext,
    ProtectionError, ReasonCode, SecretMaterial, StoredObject, canonical_bytes, content_hash,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key, text


class PrivateStoreContract:
    def setUp(self):
        super().setUp()
        self.context = examples()[ObjectContext]
        self.key = reference_key()
        self.keys = FakeKeys()
        self.crypto = CryptoService(keys=self.keys, service_identity='private-contract/test',
            random_bytes=os.urandom, environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.payload = text('synthetic-private-contract@example.invalid')
        self.envelope = self.crypto.seal(self.payload, self.context, self.key)
        self.assertIs(type(self.envelope), CipherEnvelope)
        self.store = self.make_store()

    def assert_error(self, result, code):
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, code)
        self.assertFalse(result.retryable)

    def candidate(self):
        stored = self.store.write_candidate(self.envelope, self.context)
        self.assertIs(type(stored), StoredObject)
        return stored

    def test_lifecycle_authenticates_before_verification_and_returns_only_ciphertext(self):
        candidate = self.candidate()
        encoded = canonical_bytes(self.envelope)
        identity = content_hash(dict(project=self.context.project_ref, environment=self.context.environment,
            object_uuid=self.context.object_uuid, version=self.context.object_version, field=self.context.field_ref))
        digest = hashlib.sha256(encoded).hexdigest()
        self.assertEqual(candidate.object_ref, 'private/' + content_hash({'context': identity, 'ciphertext': digest}))
        self.assertEqual((candidate.version, candidate.ciphertext_hash, candidate.size_bytes, candidate.state),
                         (self.context.object_version, digest, len(encoded), 'candidate'))
        self.assertEqual(self.blob(candidate), encoded)
        self.assertNotIn(self.payload.text.encode(), encoded)
        self.assert_error(self.store.read(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assert_error(self.store.publish(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
        with patch.object(self.crypto, 'open', wraps=self.crypto.open) as opened:
            verified = self.store.verify(candidate, self.context)
            opened.assert_called_once_with(self.envelope, self.context, self.envelope.key)
        self.assertEqual(verified, replace(candidate, state='verified'))
        self.assert_error(self.store.read(verified, self.context), ReasonCode.AUTHORIZATION_DENIED)
        with patch.object(self.crypto, 'open', side_effect=AssertionError('publish/read cannot open plaintext')):
            published = self.store.publish(verified, self.context)
            self.assertEqual(published, replace(candidate, state='published'))
            self.assertEqual(self.store.read(published, self.context), self.envelope)
        self.assertEqual(self.crypto.open(self.store.read(published, self.context), self.context, self.key), self.payload)
        self.assertEqual(self.resources(), (1, 1, len(encoded)))

    def test_forged_client_state_cannot_advance_authoritative_candidate(self):
        candidate = self.candidate()
        for state in ('candidate', 'verified', 'published'):
            forged = replace(candidate, state=state)
            with self.subTest(state=state):
                self.assert_error(self.store.publish(forged, self.context), ReasonCode.AUTHORIZATION_DENIED)
                self.assert_error(self.store.read(forged, self.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.candidate(), candidate)
        self.assertEqual(self.resources(), (1, 1, candidate.size_bytes))

    def test_replays_and_new_instance_preserve_state_identity_and_resources(self):
        candidate = self.candidate()
        self.assertEqual(self.candidate(), candidate)
        verified = self.store.verify(candidate, self.context)
        self.assertEqual(self.store.verify(candidate, self.context), verified)
        published = self.store.publish(candidate, self.context)
        self.assertEqual(self.store.publish(verified, self.context), published)
        reopened = self.make_store()
        renewed = replace(self.context, authorization_ref='authorization/renewed')
        self.assertEqual(reopened.write_candidate(self.envelope, renewed), published)
        self.assertEqual(reopened.verify(candidate, renewed), published)
        self.assertEqual(reopened.publish(candidate, renewed), published)
        self.assertEqual(reopened.read(candidate, renewed), self.envelope)
        self.assertEqual(self.resources(), (1, 1, candidate.size_bytes))

    def test_changed_stored_identity_and_unknown_references_never_read_or_publish(self):
        candidate = self.candidate()
        verified = self.store.verify(candidate, self.context)
        cases = ((replace(candidate, version='other'), ReasonCode.HASH_MISMATCH),
                 (replace(candidate, ciphertext_hash='0' * 64), ReasonCode.HASH_MISMATCH),
                 (replace(candidate, size_bytes=candidate.size_bytes + 1), ReasonCode.HASH_MISMATCH),
                 (replace(candidate, object_ref='private/' + '0' * 64), ReasonCode.AUTHORIZATION_DENIED),
                 (replace(candidate, object_ref='private/not-a-digest'), ReasonCode.AUTHORIZATION_DENIED))
        for stored, code in cases:
            for name in ('verify', 'publish', 'read'):
                with self.subTest(reference=stored.object_ref, operation=name):
                    self.assert_error(getattr(self.store, name)(stored, self.context), code)
        self.assertEqual(self.candidate(), verified)
        self.assertEqual(self.resources(), (1, 1, candidate.size_bytes))

    def test_context_binding_rejects_other_object_version_field_project_or_environment(self):
        candidate = self.candidate()
        changes = ({'object_uuid': '00000000-0000-4000-8000-000000000002'},
                   {'object_version': 'other'}, {'field_ref': 'other/field'},
                   {'project_ref': 'other/project'}, {'environment': Environment.EVALUATION})
        for change in changes:
            context = replace(self.context, **change)
            code = ReasonCode.SOURCE_NOT_APPROVED if 'environment' in change else ReasonCode.HASH_MISMATCH
            for name in ('verify', 'publish', 'read'):
                with self.subTest(field=next(iter(change)), operation=name):
                    self.assert_error(getattr(self.store, name)(candidate, context), code)
        self.assert_error(self.store.write_candidate(self.envelope, replace(
            self.context, environment=Environment.EVALUATION)), ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.candidate(), candidate)
        self.assertEqual(self.resources(), (1, 1, candidate.size_bytes))

    def test_rewrapping_same_envelope_under_another_context_cannot_authenticate(self):
        context = replace(self.context, object_version='other')
        candidate = self.store.write_candidate(self.envelope, context)
        self.assertIs(type(candidate), StoredObject)
        self.assert_error(self.store.verify(candidate, context), ReasonCode.CIPHERTEXT_INVALID)
        self.assert_error(self.store.publish(candidate, context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.store.write_candidate(self.envelope, context), candidate)

    def test_wrong_or_missing_key_leaves_candidate_unverified_and_can_retry(self):
        candidate = self.candidate()
        with patch.object(self.keys, 'resolve', return_value=SecretMaterial(b'W' * 32, KeyPurpose.DATA)):
            self.assert_error(self.store.verify(candidate, self.context), ReasonCode.CIPHERTEXT_INVALID)
        self.keys.error = ReasonCode.KEY_UNAVAILABLE
        self.assert_error(self.store.verify(candidate, self.context), ReasonCode.KEY_UNAVAILABLE)
        self.assert_error(self.store.publish(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.candidate(), candidate)
        self.keys.error = None
        self.assertEqual(self.store.verify(candidate, self.context), replace(candidate, state='verified'))
        self.assertEqual(self.resources(), (1, 1, candidate.size_bytes))

    def test_salt_nonce_and_tag_forgery_cannot_be_marked_verified(self):
        expected_bytes = 0
        for field in ('kdf_salt', 'nonce', 'ciphertext_and_tag'):
            original = getattr(self.envelope, field)
            forged = replace(self.envelope, **{field: bytes([original[0] ^ 1]) + original[1:]})
            with self.subTest(field=field):
                candidate = self.store.write_candidate(forged, self.context)
                self.assertIs(type(candidate), StoredObject)
                expected_bytes += candidate.size_bytes
                self.assert_error(self.store.verify(candidate, self.context), ReasonCode.CIPHERTEXT_INVALID)
                self.assert_error(self.store.publish(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
                self.assertEqual(self.store.write_candidate(forged, self.context), candidate)
        self.assertEqual(self.resources(), (3, 3, expected_bytes))

    def test_truncation_and_mutation_reject_verify_and_never_overwrite_ciphertext(self):
        candidate = self.candidate()
        original = self.blob(candidate)
        for encoded, code in ((original[:-1], ReasonCode.CIPHERTEXT_INVALID),
                              (b'X' + original[1:], ReasonCode.HASH_MISMATCH)):
            with self.subTest(code=code), patch.object(self.crypto, 'open') as opened:
                self.replace_blob(candidate, encoded)
                self.assert_error(self.store.verify(candidate, self.context), code)
                self.assert_error(self.store.write_candidate(self.envelope, self.context), code)
                self.assert_error(self.store.publish(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
                self.assertEqual(self.blob(candidate), encoded)
                opened.assert_not_called()
        self.replace_blob(candidate, original)
        self.assertEqual(self.candidate(), candidate)

    def test_published_corruption_or_missing_ciphertext_never_returns_an_envelope(self):
        candidate = self.candidate()
        self.store.verify(candidate, self.context)
        published = self.store.publish(candidate, self.context)
        original = self.blob(candidate)
        self.replace_blob(candidate, b'X' + original[1:])
        self.assert_error(self.store.read(published, self.context), ReasonCode.HASH_MISMATCH)
        self.remove_blob(candidate)
        self.assert_error(self.store.read(published, self.context), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(self.resources(), (1, 0, 0))

    def test_orphan_ciphertext_is_unreadable_until_explicit_reregistration_and_verification(self):
        candidate = self.candidate()
        original = self.blob(candidate)
        self.remove_record(candidate)
        self.assertEqual(self.resources(), (0, 1, len(original)))
        for name in ('verify', 'publish', 'read'):
            self.assert_error(getattr(self.store, name)(replace(candidate, state='published'), self.context),
                              ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.candidate(), candidate)
        self.assertEqual(self.blob(candidate), original)
        self.assert_error(self.store.publish(candidate, self.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.resources(), (1, 1, len(original)))

    def test_different_ciphertexts_do_not_overwrite_each_other_or_share_publication(self):
        first = self.candidate()
        envelope = self.crypto.seal(text('another-synthetic-private-value'), self.context, self.key)
        second = self.store.write_candidate(envelope, self.context)
        self.assertIs(type(second), StoredObject)
        self.assertNotEqual(first.object_ref, second.object_ref)
        self.store.verify(first, self.context)
        self.store.publish(first, self.context)
        self.assert_error(self.store.read(second, self.context), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.blob(first), canonical_bytes(self.envelope))
        self.assertEqual(self.blob(second), canonical_bytes(envelope))
        self.assertEqual(self.resources(), (2, 2, first.size_bytes + second.size_bytes))
