"""Native config ACL checks; no key material, database or provider calls."""
import os
from pathlib import Path
import tempfile
import unittest

from django.test import override_settings

from controlled_export_service.security_bootstrap import start_application
from data_security.contracts import ContractViolation, ReasonCode


@unittest.skipUnless(os.name == 'nt', 'Windows native ACL tests')
class WindowsPreparationConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='executor-config-acl-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / 'config.json'
        self.path.write_text('[]', encoding='utf-8')
        self.enterContext(override_settings(CONTROLLED_EXPORT_PRIVATE_CONFIG=str(self.path)))

    def test_native_private_config_reaches_schema_validation(self):
        from scripts.evaluate_remote_knowledge import private
        private(self.root, directory=True)
        private(self.path)
        with self.assertRaises(ContractViolation) as raised:
            start_application()
        self.assertEqual(str(raised.exception), ReasonCode.INVALID_TYPE.value)

    def test_chmod_without_private_dacl_is_rejected(self):
        self.path.chmod(0o600)
        with self.assertRaises(ContractViolation) as raised:
            start_application()
        self.assertEqual(str(raised.exception), ReasonCode.AUTHORIZATION_DENIED.value)
