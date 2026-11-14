"""Regression for separating installed dependencies from project source."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.data_security.dependencies import check_source, scan


class SourceInventoryTests(unittest.TestCase):
    def test_rebuild_grant_only_allows_the_bound_protection_entry(self):
        source = 'backend/legal_kb/management/commands/rebuild_legal_kb.py'
        self.assertFalse(check_source(source,
            'from data_security.adapters.django.rag import protect_rag', phase=7))
        for statement in ('from data_security.adapters.django.rag import bind_rag_protection',
                          'from data_security.adapters.keys import FileKeyResolver',
                          'from ctf_backend.security_bootstrap import assemble'):
            self.assertTrue(check_source(source, statement, phase=7))

    def test_real_venv_is_excluded_but_other_hidden_source_is_checked(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / 'backend' / '.venv-local'
            environment.mkdir(parents=True)
            (environment / 'pyvenv.cfg').write_text('include-system-site-packages = false\n')
            (environment / 'dependency.py').write_text('eval("external dependency")\n')
            source = root / 'backend' / '.application' / 'unsafe.py'
            source.parent.mkdir()
            source.write_text('eval("project code")\n')
            checked, findings = scan(root, phase=7)
            self.assertEqual(checked, 1)
            self.assertEqual([(item.file, item.code) for item in findings],
                             [('backend/.application/unsafe.py', 'DYNAMIC_CODE_OR_IMPORT')])
