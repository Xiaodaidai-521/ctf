"""Dependency probes for the source-identity addition, not a repeat of prior suites."""
import unittest

from tools.data_security.dependencies import PHASE7_EXTERNAL, check_source


class RevealSourceDependencyTests(unittest.TestCase):
    def test_source_http_mapper_cannot_resolve_owners_keys_or_implementations(self):
        path = 'backend/data_security/adapters/django/reveal_api.py'
        self.assertFalse(check_source(path, 'from data_security.contracts import FrozenJSON', phase=7))
        for statement in (
            'from data_security.adapters.persistence.reveal import DjangoRevealRepository',
            'from data_security.application.reveal import RevealFlow',
            'from users.models import CTFUser', 'from users.permissions import authorized_users',
            'from legal.services.data_access import authorized_legal_objects',
            'from ctf_backend.security_bootstrap import assemble', 'from django.conf import settings',
            'import os\nos.getenv("ARK_API_KEY")',
        ):
            with self.subTest(statement=statement):
                self.assertTrue(check_source(path, statement, phase=7))

    def test_repository_admits_only_the_added_database_error_import(self):
        module = 'data_security.adapters.persistence.reveal'
        self.assertEqual(PHASE7_EXTERNAL[module], {
            'django.db.DatabaseError', 'django.db.connection', 'django.db.models.Q',
            'legal.models.LegalAnalysisTask', 'legal.models.LegalReport', 'legal.permissions.IsLegalReviewer',
            'legal.services.data_access.authorized_legal_objects', 'users.models.CTFUser',
            'users.permissions.authorized_users',
        })
        path = 'backend/' + module.replace('.', '/') + '.py'
        self.assertFalse(check_source(path, 'from django.db import DatabaseError', phase=7))
        for statement in ('from data_security.adapters.keys import FileKeyResolver',
                          'from django.conf import settings', 'from data_security.core.crypto import open_envelope',
                          'from audit.services import AuditLedgerService',
                          'from ctf_backend.security_bootstrap import assemble', 'import os\nos.environ["ARK_API_KEY"]'):
            with self.subTest(statement=statement):
                self.assertTrue(check_source(path, statement, phase=7))
