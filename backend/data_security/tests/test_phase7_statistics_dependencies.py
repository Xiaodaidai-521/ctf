"""Statistics-only dependency probes; previous stage suites are not imported."""
from pathlib import Path
import tempfile
import unittest

from tools.data_security.dependencies import PHASE7_EXTERNAL, check_source, scan


class StatisticsDependencyTests(unittest.TestCase):
    def test_http_mapper_has_no_repository_crypto_secret_or_bootstrap_access(self):
        module = 'data_security.adapters.django.statistics_api'
        path = 'backend/' + module.replace('.', '/') + '.py'
        for target in PHASE7_EXTERNAL[module]:
            self.assertFalse(check_source(path, 'import ' + target, phase=7))
        self.assertFalse(check_source(path, 'from data_security.contracts import FrozenJSON', phase=7))
        for statement in (
            'from data_security.adapters.persistence.statistics import read_statistics',
            'from data_security.adapters.persistence.models import ExportReport',
            'from data_security.application.reports import ReportAuthenticator',
            'from ctf_backend.security_bootstrap import assemble',
            'from django.conf import settings', 'from users.models import CTFUser',
            'from openai import OpenAI', 'import os\nos.getenv("ARK_API_KEY")',
            'from data_security.adapters.django.statistics_api.future import Reader',
        ):
            with self.subTest(statement=statement):
                self.assertTrue(check_source(path, statement, phase=7))

    def test_repository_has_only_read_source_and_exact_database_error_imports(self):
        path = 'backend/data_security/adapters/persistence/statistics.py'
        self.assertEqual(PHASE7_EXTERNAL['data_security.adapters.persistence.statistics'], {'django.db.DatabaseError'})
        self.assertFalse(check_source(path, 'from django.db import DatabaseError', phase=7))
        self.assertFalse(check_source(path, 'from data_security.adapters.persistence.models import ExportReport', phase=7))
        for statement in (
            'from django.db import connection', 'from django.conf import settings',
            'from audit.models import AuthenticatedAuditEntry',
            'from audit.services import AuditLedgerService\nAuditLedgerService.append_entry(None, None, None)',
            'from data_security.application.reports import ReportAuthenticator',
            'from data_security.adapters.keys import FileKeyResolver',
            'from ctf_backend.security_bootstrap import assemble',
            'from export_risk.models import RiskDecision',
            'import os\nos.environ["ARK_API_KEY"]',
            'from data_security.adapters.persistence.statistics.future import Reader',
        ):
            with self.subTest(statement=statement):
                self.assertTrue(check_source(path, statement, phase=7))
        self.assertTrue(check_source('backend/data_security/adapters/persistence/unlisted_statistics.py',
                                     'from django.db import DatabaseError', phase=7))

    def test_statistics_inventory_does_not_reopen_the_first_six_phases(self):
        modules = ('data_security.adapters.django.statistics_api', 'data_security.adapters.persistence.statistics')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for module in modules:
                path = root / 'backend' / (module.replace('.', '/') + '.py')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('"""Synthetic statistics boundary probe."""\n')
            self.assertEqual(scan(root, phase=7), (2, []))
            for phase in (1, 2, 3, 4, 5, 6):
                with self.subTest(phase=phase):
                    checked, findings = scan(root, phase=phase)
                    self.assertEqual(checked, 2)
                    self.assertEqual(len(findings), 2)
                    self.assertEqual({item.file for item in findings},
                                     {'backend/' + module.replace('.', '/') + '.py' for module in modules})
                    self.assertTrue(all(item.code == f'PHASE{phase}_FUTURE_IMPLEMENTATION' for item in findings))
