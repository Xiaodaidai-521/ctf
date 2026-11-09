"""Phase-four source grants remain narrower than the frozen module matrix."""
from pathlib import Path
import tempfile
import unittest

from tools.data_security.dependencies import (
    ALLOWED, PHASE3_MODULES, PHASE4_MODULES, PHASE4_EXTERNAL, PHASE4_LEGACY,
    check_source, scan,
)


class Phase4DependencyTests(unittest.TestCase):
    def test_each_declared_external_and_legacy_grant_is_source_specific(self):
        for grants in (PHASE4_EXTERNAL, PHASE4_LEGACY):
            for module, targets in grants.items():
                source = 'backend/' + module.replace('.', '/') + '.py'
                for target in targets:
                    with self.subTest(source=source, target=target):
                        self.assertFalse(check_source(source, 'import ' + target, phase=4))
        for source in ('backend/unlisted/views.py', 'backend/users/serializers.py'):
            for target in ('data_security.core.crypto', 'data_security.adapters.keys',
                           'data_security.application.crypto_service', 'ctf_backend.security_bootstrap'):
                self.assertTrue(check_source(source, 'import ' + target, phase=4))

    def test_storage_and_http_do_not_gain_cross_layer_capabilities(self):
        self.assertEqual(ALLOWED['M6'], {'M0', 'M6'})
        self.assertEqual(ALLOWED['M9'], {'M0', 'M9'})
        for name in ('fields', 'field_migration', 'field_rotation', 'orm_policies'):
            source = 'backend/data_security/adapters/persistence/' + name + '.py'
            for target in ('data_security.core.crypto', 'data_security.adapters.keys',
                           'requests', 'django.http', 'users.models'):
                self.assertTrue(check_source(source, 'import ' + target, phase=4))
            self.assertTrue(check_source(source, 'import os\nvalue = os.environ["DATA_KEY"]', phase=4))
        source = 'backend/data_security/adapters/django/policy_api.py'
        for target in ('data_security.adapters.persistence.orm_policies', 'data_security.adapters.keys',
                       'data_security.application.policy_catalog', 'cryptography'):
            self.assertTrue(check_source(source, 'import ' + target, phase=4))

    def test_phase_four_files_are_not_backported_or_open_to_future_modules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for module in PHASE4_MODULES - PHASE3_MODULES:
                path = root / ('backend/' + module.replace('.', '/') + '.py')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('from data_security.contracts import ProtectionError\n')
            self.assertEqual(scan(root, phase=4)[1], [])
            for phase in (1, 2, 3):
                self.assertIn(f'PHASE{phase}_FUTURE_IMPLEMENTATION', {item.code for item in scan(root, phase=phase)[1]})
        for source in ('from data_security.adapters.persistence import future',
                       'from data_security.adapters.persistence.fields.future import DecryptAll',
                       'import data_security.application.export_flow'):
            self.assertTrue(check_source('backend/ctf_backend/security_bootstrap.py', source, phase=4))
