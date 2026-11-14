"""Native ACL regressions for the Windows evaluation key boundary."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data_security.adapters.private_permissions import is_private_path


@unittest.skipUnless(os.name == 'nt', 'Windows native ACL tests')
class WindowsPrivateKeyTests(unittest.TestCase):
    def setUp(self):
        import win32security
        self.security = win32security
        self.tmp = tempfile.TemporaryDirectory(prefix='private-acl-test-')
        self.directory = Path(self.tmp.name).resolve()
        self.path = self.directory / 'secret.key'
        self.path.write_bytes(b'synthetic-key-only')
        from scripts.evaluate_remote_knowledge import private
        private(self.directory, directory=True)
        private(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_private_directory_and_key_are_accepted(self):
        self.assertTrue(is_private_path(self.directory, directory=True))
        self.assertTrue(is_private_path(self.path))

    def test_foreign_reader_is_rejected(self):
        security = self.security
        descriptor = security.GetNamedSecurityInfo(str(self.path), security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION)
        acl = descriptor.GetSecurityDescriptorDacl()
        everyone = security.CreateWellKnownSid(security.WinWorldSid, None)
        acl.AddAccessAllowedAce(security.ACL_REVISION, 1, everyone)
        security.SetNamedSecurityInfo(str(self.path), security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, acl, None)
        self.assertFalse(is_private_path(self.path))

    def test_unprotected_dacl_is_rejected(self):
        security = self.security
        security.SetNamedSecurityInfo(str(self.path), security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION | security.UNPROTECTED_DACL_SECURITY_INFORMATION,
            None, None, security.ACL(), None)
        self.assertFalse(is_private_path(self.path))

    def test_null_dacl_is_rejected(self):
        security = self.security
        security.SetNamedSecurityInfo(str(self.path), security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, None, None)
        self.assertFalse(is_private_path(self.path))

    def test_native_acl_read_failure_denies_access(self):
        import pywintypes
        with patch.object(self.security, 'GetNamedSecurityInfo',
                          side_effect=pywintypes.error(5, 'GetNamedSecurityInfo', 'Access denied')):
            self.assertFalse(is_private_path(self.path))
