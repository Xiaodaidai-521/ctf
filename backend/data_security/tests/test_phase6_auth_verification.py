"""Restricted historical MAC verification; no key rotation or live provider use."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock

from data_security.application.crypto_service import CryptoService
from data_security.contracts import (
    BASELINE_LIMITS, Environment, KeyPurpose, KeyStatus, ObjectContext, ProtectionError, ReasonCode,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key


class AuthenticationVerificationTests(TestCase):
    def setUp(self):
        self.context = examples()[ObjectContext]
        self.key = reference_key(KeyPurpose.AUDIT)
        self.service = CryptoService(keys=FakeKeys(), service_identity='test/mac-verification',
            random_bytes=Mock(side_effect=AssertionError('MAC verification must not generate randomness')),
            environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.metadata = b'synthetic-versioned-audit-metadata'
        self.mac = self.service.authenticate(self.metadata, self.context, self.key)
        self.assertIsInstance(self.mac, bytes)

    def test_read_only_key_verifies_but_cannot_issue_authentication(self):
        old = replace(self.key, status=KeyStatus.READ_ONLY)
        self.assertIs(self.service.verify_authentication(self.metadata, self.mac, self.context, self.key), True)
        self.assertIs(self.service.verify_authentication(self.metadata, self.mac, self.context, old), True)
        self.assertEqual(self.service.authenticate(self.metadata, self.context, old).code, ReasonCode.KEY_UNAVAILABLE)
        self.service.random_bytes.assert_not_called()

    def test_wrong_content_scope_project_version_and_mac_are_false_not_success(self):
        cases = (
            (self.metadata + b'changed', self.mac, self.context, self.key),
            (self.metadata, bytes([self.mac[0] ^ 1]) + self.mac[1:], self.context, self.key),
            (self.metadata, self.mac, replace(self.context, field_ref='other/purpose'), self.key),
            (self.metadata, self.mac, replace(self.context, project_ref='other/project'), self.key),
            (self.metadata, self.mac, self.context, replace(self.key, key_ref='audit-auth/v2', version='v2')),
        )
        for args in cases:
            self.assertIs(self.service.verify_authentication(*args), False)

    def test_retired_wrong_purpose_environment_and_resolver_errors_remain_errors(self):
        for key in (replace(self.key, status=KeyStatus.RETIRED), reference_key(KeyPurpose.INDEX)):
            self.assertEqual(self.service.verify_authentication(self.metadata, self.mac, self.context, key).code,
                             ReasonCode.KEY_UNAVAILABLE)
        result = self.service.verify_authentication(self.metadata, self.mac,
            replace(self.context, environment=Environment.PRODUCTION), self.key)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.service.keys = FakeKeys(ReasonCode.KEY_UNAVAILABLE)
        self.assertEqual(self.service.verify_authentication(self.metadata, self.mac, self.context, self.key).code,
                         ReasonCode.KEY_UNAVAILABLE)
        self.service.keys = Mock(resolve=Mock(side_effect=RuntimeError('synthetic resolver failure')))
        result = self.service.verify_authentication(self.metadata, self.mac, self.context, self.key)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(result.code, ReasonCode.KEY_UNAVAILABLE)

    def test_malformed_mac_or_metadata_limit_fail_before_loading_key_material(self):
        self.service.keys.calls.clear()
        for value in (None, '', b'', b'0' * 31, b'0' * 33):
            result = self.service.verify_authentication(self.metadata, value, self.context, self.key)
            self.assertEqual(result.code, ReasonCode.INVALID_VALUE)
        self.service.limits = replace(BASELINE_LIMITS, max_bytes=4)
        result = self.service.verify_authentication(b'12345', self.mac, self.context, self.key)
        self.assertEqual(result.code, ReasonCode.LIMIT_EXCEEDED)
        self.assertEqual(self.service.keys.calls, [])
