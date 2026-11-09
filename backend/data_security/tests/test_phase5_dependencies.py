"""Additive M8 inventory; historical dependency rules remain closed."""
from pathlib import Path
import tempfile
import unittest

from tools.data_security.dependencies import (ALLOWED, PHASE4_MODULES, PHASE5_MODULES,
    PHASE5_EXTERNAL, PHASE5_LEGACY, check_source, scan)


class Phase5Dependencies(unittest.TestCase):
    def test_specific_grants_do_not_expand_module_matrix(self):
        self.assertEqual(ALLOWED['M8'], {'M0', 'M8'})
        for grants in (PHASE5_EXTERNAL, PHASE5_LEGACY):
            for module, imports in grants.items():
                path = ('backend/' + module.replace('.', '/') + '.py')
                for target in imports:
                    with self.subTest(module=module, target=target):
                        self.assertEqual(check_source(path, 'import ' + target, phase=5), [])

    def test_m8_cannot_read_policies_orm_secrets_core_or_deliver(self):
        for module in ('codec', 'source_plans', 'parsed_artifacts', 'column_v1'):
            path = 'backend/data_security/adapters/tabular/' + module + '.py'
            for target in ('django.conf.settings', 'django.db', 'data_security.core.redaction',
                           'data_security.core.policy', 'data_security.adapters.keys',
                           'data_security.adapters.persistence', 'export_risk', 'export_quota',
                           'requests', 'ctf_backend.security_bootstrap'):
                with self.subTest(module=module, target=target):
                    self.assertTrue(check_source(path, 'import ' + target, phase=5))
            self.assertTrue(check_source(path, 'import os\nv = os.getenv("SECRET")', phase=5))

    def test_inventory_is_not_backported_and_future_remains_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for module in PHASE5_MODULES - PHASE4_MODULES:
                file = root / ('backend/' + module.replace('.', '/') + '.py')
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('from data_security.contracts import Limits\n')
            self.assertEqual(scan(root, phase=5)[1], [])
            for phase in (1, 2, 3, 4):
                self.assertIn(f'PHASE{phase}_FUTURE_IMPLEMENTATION', {v.code for v in scan(root, phase=phase)[1]})
        for statement in ('import data_security.application.export_flow',
                          'import data_security.adapters.tabular.future'):
            self.assertTrue(check_source('backend/ctf_backend/security_bootstrap.py', statement, phase=5))
