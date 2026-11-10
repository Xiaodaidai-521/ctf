"""New reveal-only probes; do not reload already-passed RAG dependency methods."""
from pathlib import Path
import tempfile
import unittest

from tools.data_security.dependencies import PHASE7_EXTERNAL, check_source, scan


class RevealDependencyTests(unittest.TestCase):
    def test_reveal_core_cannot_use_framework_owner_secret_sdk_or_bootstrap(self):
        path = 'backend/data_security/application/reveal.py'
        for statement in (
            'from django.db import transaction',
            'from users.models import CTFUser',
            'from data_security.adapters.persistence.reveal import DjangoRevealRepository',
            'from data_security.adapters.keys import FileKeyResolver',
            'from data_security.adapters.llm.official import OfficialAI',
            'from ctf_backend.security_bootstrap import assemble_reveal',
            'import os\nos.getenv("ARK_API_KEY")',
            'from openai import OpenAI',
            'from data_security.application.reveal.future import Flow',
        ):
            with self.subTest(statement=statement):
                self.assertTrue(check_source(path, statement, phase=7))

    def test_reveal_repository_and_migration_imports_are_source_specific(self):
        repository = 'data_security.adapters.persistence.reveal'
        migration = 'data_security.adapters.persistence.migrations.0013_reveal_request'
        for module in (repository, migration):
            path = 'backend/' + module.replace('.', '/') + '.py'
            for target in PHASE7_EXTERNAL[module]:
                with self.subTest(module=module, target=target):
                    self.assertFalse(check_source(path, 'import ' + target, phase=7))
        path = 'backend/' + repository.replace('.', '/') + '.py'
        for statement in (
            'from users.models import CourseDataGrant',
            'from legal.models import LegalFactSnapshot',
            'from django.conf import settings',
            'import os\nos.environ["ARK_API_KEY"]',
            'from openai import OpenAI',
            'from audit.models import AuthenticatedAuditEntry',
            'from audit.services import AuditLedgerService\nAuditLedgerService.append_entry(None, None, None)',
            'from ctf_backend.security_bootstrap import assemble_reveal',
            'from data_security.adapters.persistence.reveal.future import Repository',
        ):
            with self.subTest(statement=statement):
                self.assertTrue(check_source(path, statement, phase=7))
        other = 'backend/data_security/adapters/persistence/unlisted_reveal.py'
        self.assertTrue(check_source(other, 'from django.conf import settings', phase=7))
        self.assertTrue(check_source(other, 'from users.models import CTFUser', phase=7))

    def test_reveal_inventory_does_not_reopen_the_first_six_phases(self):
        modules = (
            'data_security.application.reveal',
            'data_security.adapters.persistence.reveal',
            'data_security.adapters.persistence.migrations.0013_reveal_request',
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for module in modules:
                path = root / 'backend' / (module.replace('.', '/') + '.py')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('"""Synthetic boundary probe."""\n')
            checked, findings = scan(root, phase=7)
            self.assertEqual(checked, 3)
            self.assertEqual(findings, [])
            for phase in (1, 2, 3, 4, 5, 6):
                with self.subTest(phase=phase):
                    checked, findings = scan(root, phase=phase)
                    expected = 2 if phase in (1, 2) else 3
                    self.assertEqual(checked, expected)
                    self.assertEqual(len(findings), expected)
                    self.assertTrue(all(item.code == f'PHASE{phase}_FUTURE_IMPLEMENTATION'
                                        for item in findings))


class RevealManagementDependencyTests(unittest.TestCase):
    def test_new_http_mapper_has_only_schema_and_exact_framework_dependencies(self):
        module = 'data_security.adapters.django.reveal_api'
        path = 'backend/' + module.replace('.', '/') + '.py'
        for target in PHASE7_EXTERNAL[module]:
            with self.subTest(target=target):
                self.assertFalse(check_source(path, 'import ' + target, phase=7))
        self.assertFalse(check_source(path, 'from data_security.contracts import RevealRequestRecord', phase=7))
        for statement in (
            'from data_security.application.reveal import RevealFlow',
            'from data_security.adapters.persistence.reveal import DjangoRevealRepository',
            'from ctf_backend.security_bootstrap import assemble_reveal',
            'from users.models import CTFUser',
            'from django.conf import settings',
            'import os\nos.getenv("ARK_API_KEY")',
            'from openai import OpenAI',
            'from data_security.adapters.django.reveal_api.future import View',
        ):
            with self.subTest(statement=statement):
                self.assertTrue(check_source(path, statement, phase=7))
        bootstrap = 'backend/ctf_backend/security_bootstrap.py'
        self.assertFalse(check_source(bootstrap,
            'from data_security.adapters.django.reveal_api import bind_reveal_api', phase=7))
        self.assertTrue(check_source(bootstrap,
            'from data_security.adapters.django.reveal_api.future import bind', phase=7))

    def test_metadata_migration_and_owner_query_extension_are_caller_specific(self):
        module = 'data_security.adapters.persistence.migrations.0014_reveal_request_metadata'
        path = 'backend/' + module.replace('.', '/') + '.py'
        self.assertEqual(PHASE7_EXTERNAL[module], {'django.db.models', 'django.db.migrations'})
        for target in PHASE7_EXTERNAL[module]:
            self.assertFalse(check_source(path, 'import ' + target, phase=7))
        for statement in ('from django.conf import settings', 'from users.models import CTFUser',
                          'from audit.models import AuthenticatedAuditEntry',
                          'from ctf_backend.security_bootstrap import assemble_reveal'):
            with self.subTest(statement=statement):
                self.assertTrue(check_source(path, statement, phase=7))
        repository = 'backend/data_security/adapters/persistence/reveal.py'
        self.assertFalse(check_source(repository, 'from django.db.models import Q', phase=7))
        self.assertTrue(check_source('backend/data_security/adapters/persistence/unlisted_request.py',
                                     'from django.db.models import Q', phase=7))
        self.assertTrue(check_source(repository,
            'from audit.services import AuditLedgerService\nAuditLedgerService.append_entry(None, None, None)', phase=7))

    def test_management_inventory_is_not_enabled_in_previous_phases(self):
        modules = ('data_security.adapters.django.reveal_api',
                   'data_security.adapters.persistence.migrations.0014_reveal_request_metadata')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for module in modules:
                path = root / 'backend' / (module.replace('.', '/') + '.py')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('"""Synthetic management boundary probe."""\n')
            checked, findings = scan(root, phase=7)
            self.assertEqual(checked, 2)
            self.assertEqual(findings, [])
            for phase in (1, 2, 3, 4, 5, 6):
                with self.subTest(phase=phase):
                    checked, findings = scan(root, phase=phase)
                    expected = 1 if phase in (1, 2) else 2
                    self.assertEqual(checked, expected)
                    self.assertEqual(len(findings), expected)
                    self.assertTrue(all(item.code == f'PHASE{phase}_FUTURE_IMPLEMENTATION'
                                        for item in findings))
