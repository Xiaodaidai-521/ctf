"""Native permissions on synthetic configuration and recovery proof files."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ctf_backend import security_bootstrap
from data_security.contracts import ContractViolation


@unittest.skipUnless(os.name == 'nt', 'requires real Windows ACLs')
class NativeBootstrapFilePermissionsTests(unittest.TestCase):
    def setUp(self):
        from data_security.runtime.crypto import restrict_path
        from data_security.tests.phase3_fixtures import configuration
        self.restrict = restrict_path
        self.fixture = configuration(providers=())
        source, self.config, *_ = self.fixture.__enter__()
        self.addCleanup(self.fixture.__exit__, None, None, None)
        self.source = source.resolve()
        directory = self.source.parent
        for path in directory.iterdir():
            self.restrict(path)
        self.restrict(directory, directory=True)
        for field in ('key_manifest', 'policy_file'):
            self.config[field] = str(Path(self.config[field]).resolve())
        self.source.write_text(json.dumps(self.config), encoding='utf-8')

    def foreign_reader(self, path):
        import win32security as security
        descriptor = security.GetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION)
        acl = descriptor.GetSecurityDescriptorDacl()
        acl.AddAccessAllowedAce(security.ACL_REVISION, 1,
                               security.CreateWellKnownSid(security.WinWorldSid, None))
        security.SetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, acl, None)

    def proof(self):
        proof = self.source.parent / 'recovery-proof.json'
        proof.write_text(json.dumps({
            'returncode': 0, 'key_material_in_evidence': False,
            'recovery_observations': {'receipt_durability': 'durable', 'checks': {'restore': True}},
        }), encoding='utf-8')
        self.restrict(proof)
        self.config.update(schema_version='ds.bootstrap.v2',
            policy_repository={'kind': 'file', 'writable': False},
            field_storage={'legacy_reads': False, 'index_keys': [self.config['data_key']],
                'read_keys': [], 'recovery_record': {'path': str(proof),
                'sha256': hashlib.sha256(proof.read_bytes()).hexdigest()}})
        self.source.write_text(json.dumps(self.config), encoding='utf-8')
        return proof

    def test_private_configuration_accepted_despite_windows_posix_mode(self):
        self.assertEqual(self.source.stat().st_mode & 0o022, 0o022)
        loaded, _ = security_bootstrap._configuration(self.source)
        self.assertEqual(loaded, self.config)

    def test_foreign_configuration_reader_is_rejected(self):
        self.foreign_reader(self.source)
        with self.assertRaises(ContractViolation):
            security_bootstrap._configuration(self.source)

    def test_private_recovery_proof_is_accepted(self):
        self.proof()
        loaded, _ = security_bootstrap._configuration(self.source)
        self.assertEqual(loaded, self.config)

    def test_foreign_recovery_proof_reader_is_rejected(self):
        proof = self.proof()
        self.foreign_reader(proof)
        with self.assertRaises(ContractViolation):
            security_bootstrap._configuration(self.source)


class PosixBootstrapFilePermissionsTests(unittest.TestCase):
    def test_group_and_other_write_are_rejected_but_read_is_allowed(self):
        path = Mock()
        for mode, accepted in ((0o600, True), (0o644, True), (0o620, False), (0o602, False)):
            with self.subTest(mode=oct(mode)), patch.object(security_bootstrap.os, 'name', 'posix'):
                path.stat.return_value = SimpleNamespace(st_mode=mode)
                self.assertEqual(security_bootstrap._bootstrap_file_permissions(path), accepted)
