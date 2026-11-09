from pathlib import Path
import tempfile
import unittest

from tools.data_security.dependencies import ALLOWED, check_source, scan


ROOT = Path(__file__).resolve().parents[3]
MODULES = {
    'M0': 'data_security.contracts.payloads', 'M1': 'data_security.core.redaction',
    'M2': 'data_security.core.policy', 'M3': 'data_security.core.crypto',
    'M4': 'data_security.application.protection', 'M5': 'data_security.adapters.keys',
    'M6': 'data_security.adapters.persistence.audit', 'M7': 'data_security.adapters.llm.official',
    'M8': 'data_security.adapters.tabular.codec', 'M9': 'data_security.adapters.django.views',
    'B': 'ctf_backend.security_bootstrap',
}


def path(module):
    return 'backend/' + module.replace('.', '/') + '.py'


class DependencyTests(unittest.TestCase):
    def test_every_pair_in_the_module_matrix(self):
        for source, module in MODULES.items():
            for target, imported in MODULES.items():
                for statement in (f'import {imported}', f'from {imported} import Boundary'):
                    with self.subTest(source=source, target=target, statement=statement):
                        violations = check_source(path(module), statement)
                        self.assertEqual(bool(violations), target not in ALLOWED[source])

    def test_frameworks_environment_io_and_implicit_randomness_rejected_in_pure_layers(self):
        for owner in ('M0', 'M1', 'M2', 'M3', 'M4'):
            for statement in ('import django', 'import openai', 'import psycopg2',
                              'import os', 'import pathlib', 'import socket', 'import mainline1',
                              'import secrets', 'open("unavailable")', 'print("payload")',
                              'from datetime import datetime as Clock\nClock.now()',
                              'from builtins import open as reader\nreader("unavailable")'):
                with self.subTest(owner=owner, statement=statement):
                    self.assertTrue(check_source(path(MODULES[owner]), statement))

    def test_mature_crypto_is_allowed_only_in_crypto_or_bootstrap(self):
        for owner, module in MODULES.items():
            found = check_source(path(module), 'from cryptography.hazmat.primitives import hashes')
            self.assertEqual(not found, owner in ('M3', 'B'))

    def test_no_reverse_bootstrap_import_from_business_or_root_initializer(self):
        for filename in ('backend/users/views.py', 'backend/data_security/__init__.py'):
            self.assertTrue(check_source(filename, 'from ctf_backend.security_bootstrap import dependencies'))
        self.assertTrue(check_source('backend/data_security/__init__.py', 'import django'))
        self.assertFalse(check_source('backend/data_security/__init__.py', '"""No eager wiring."""'))

    def test_relative_imports_have_the_same_boundaries(self):
        self.assertFalse(check_source(path(MODULES['M1']), 'from ..contracts import Finding'))
        self.assertTrue(check_source(path(MODULES['M0']), 'from ..adapters.keys import Resolver'))
        self.assertTrue(check_source(path(MODULES['M1']), 'from ... import request'))

    def test_dynamic_imports_and_evaluation_rejected_in_every_security_module(self):
        for owner, module in MODULES.items():
            for statement in ('eval("expression")', 'exec("expression")', '__import__("module")',
                              'loader = __import__\nloader("module")',
                              'import importlib as loader\nloader.import_module("module")'):
                with self.subTest(owner=owner, statement=statement):
                    self.assertTrue(check_source(path(module), statement))

    def test_adapters_use_ports_not_each_others_implementations(self):
        cases = {
            'M5': ('import django', 'import urllib.request', 'import openai'),
            'M6': ('import requests', 'import urllib.request', 'import openai'),
            'M7': ('import django', 'from users.serializers import UserSerializer', 'import dotenv'),
            'M8': ('import django', 'from export_quota.service import QuotaService', 'import openai'),
            'M9': ('from ctfsafe.encryption import decrypt_field', 'import dotenv'),
        }
        for owner, statements in cases.items():
            for statement in statements:
                with self.subTest(owner=owner, statement=statement):
                    self.assertTrue(check_source(path(MODULES[owner]), statement))
            self.assertFalse(check_source(path(MODULES[owner]), 'from data_security.contracts import ProtectionPort'))

    def test_secret_config_access_is_not_granted_to_persistence(self):
        for statement in ('import os as env\nenv.getenv("key")',
                          'from os import environ as env\nenv["key"]',
                          'import os\nos.environ.get("key")'):
            self.assertTrue(check_source(path(MODULES['M6']), statement))
        self.assertFalse(check_source(path(MODULES['M5']), 'import os\nos.environ.get("reference")'))

    def test_unclassified_modules_and_live_phase1_connections_are_rejected(self):
        self.assertTrue(check_source('backend/data_security/misc.py', 'value = 1'))
        self.assertTrue(check_source('backend/users/views.py', 'from data_security.contracts import Finding'))
        with tempfile.TemporaryDirectory(dir=ROOT / '.state', prefix='dependency-fixture-') as directory:
            folder = Path(directory) / 'backend/data_security/core'
            folder.mkdir(parents=True)
            (folder / 'crypto.py').write_text('from data_security.contracts import CipherEnvelope\n')
            _, found = scan(directory)
            self.assertIn('PHASE1_FUTURE_IMPLEMENTATION', {item.code for item in found})

    def test_python_source_encoding_is_not_mistaken_for_a_dependency_failure(self):
        self.assertFalse(check_source('backend/users/views.py', b'\xef\xbb\xbfimport datetime\n'))
        self.assertTrue(check_source(path(MODULES['M0']), b'\xef\xbb\xbfimport django\n'))
        self.assertEqual(check_source(path(MODULES['M0']), 'def broken(')[0].code, 'INVALID_PYTHON')

    def test_actual_production_sources_have_no_new_wiring_or_illegal_dependencies(self):
        checked, found = scan(ROOT)
        self.assertGreater(checked, 100)
        self.assertEqual(found, [])
