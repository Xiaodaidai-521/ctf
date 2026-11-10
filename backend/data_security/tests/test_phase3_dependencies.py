"""Phase-3 inventory/assembly permissions do not widen the M0-B matrix."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.data_security.dependencies import (
    ALLOWED, PHASE2_MODULES, PHASE3_EXTERNAL, PHASE3_LEGACY, PHASE3_MODULES,
    check_source, scan,
)


ROOT = Path(__file__).resolve().parents[3]
MODULES = {
    'M0': 'data_security.contracts.events', 'M1': 'data_security.core.redaction',
    'M2': 'data_security.core.policy', 'M3': 'data_security.core.crypto',
    'M4': 'data_security.application.audit_gateway', 'M5': 'data_security.adapters.keys',
    'M6': 'data_security.adapters.persistence.audit', 'M7': 'data_security.adapters.llm.official',
    'M8': 'data_security.adapters.tabular.legacy', 'M9': 'data_security.adapters.django.logging',
    'B': 'ctf_backend.security_bootstrap',
}


def path(module):
    return 'backend/' + module.replace('.', '/') + '.py'


class Phase3DependencyTests(unittest.TestCase):
    def test_all_matrix_edges_remain_exactly_the_frozen_matrix(self):
        self.assertEqual(ALLOWED, {
            'M0': {'M0'}, 'M1': {'M0', 'M1', 'M3'}, 'M2': {'M0', 'M2'}, 'M3': {'M0', 'M3'},
            'M4': {'M0', 'M1', 'M2', 'M3', 'M4'}, 'M5': {'M0', 'M5'}, 'M6': {'M0', 'M6'},
            'M7': {'M0', 'M7'}, 'M8': {'M0', 'M8'}, 'M9': {'M0', 'M9'},
            'B': {'M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'B'},
        })
        for phase in (1, 2, 3):
            for owner, module in MODULES.items():
                for target_owner, target in MODULES.items():
                    for statement in (f'import {target} as boundary', f'from {target} import Boundary'):
                        with self.subTest(phase=phase, owner=owner, target=target_owner):
                            self.assertEqual(bool(check_source(path(module), statement, phase=phase)),
                                             target_owner not in ALLOWED[owner])

    def test_real_adapter_external_capabilities_are_source_specific(self):
        for module, targets in PHASE3_EXTERNAL.items():
            for target in targets:
                self.assertFalse(check_source(path(module), 'import ' + target, phase=3))
        denied = {
            'data_security.adapters.keys': ('requests', 'django', 'psycopg2', 'dotenv'),
            'data_security.adapters.persistence.audit': ('requests', 'psycopg2', 'struct', 'legal.models'),
            'data_security.adapters.persistence.policies': ('django', 'psycopg2', 'audit.models.AuditEvent'),
            'data_security.adapters.persistence.backup': ('requests', 'audit.models.AuditEvent', 'websockets'),
            'data_security.adapters.llm.official': ('django', 'psycopg2', 'websockets', 'websockets.sync.server.serve'),
            'data_security.adapters.django.logging': ('psycopg2', 'audit.models.AuditEvent', 'subprocess'),
            'ctf_backend.security_bootstrap': ('users.models.User', 'audit.services.AuditLedgerService',
                                             'ai_assistant.service.AIService', 'ai_assistant.security.OutputSanitizer'),
        }
        for module, targets in denied.items():
            for target in targets:
                with self.subTest(module=module, target=target):
                    self.assertTrue(check_source(path(module), 'import ' + target, phase=3))
        self.assertFalse(check_source(path(MODULES['M7']),
                         'from websockets.sync.client import connect', phase=3))
        self.assertTrue(check_source(path(MODULES['M7']),
                        'from websockets.sync.client import connect', phase=2))
        self.assertFalse(check_source('backend/data_security/adapters/persistence/backup.py',
                         'import struct\nimport psycopg2', phase=3))

    def test_only_listed_legacy_sources_get_m0_or_narrow_adapter_edges(self):
        for module, targets in PHASE3_LEGACY.items():
            for target in targets:
                self.assertFalse(check_source(path(module), f'from {target} import Boundary', phase=3))
        for source in ('backend/users/views.py', 'backend/unlisted/service.py'):
            for target in ('data_security.contracts', 'data_security.adapters.django.content',
                           'data_security.application.protection', 'data_security.adapters.keys',
                           'data_security.adapters.persistence.audit', 'data_security.adapters.llm.official'):
                self.assertTrue(check_source(source, f'from {target} import Boundary', phase=3))
        for module in PHASE3_LEGACY:
            for target in (MODULES['M4'], MODULES['M5'], MODULES['M6'], MODULES['M7'], MODULES['B']):
                self.assertTrue(check_source(path(module), 'import ' + target, phase=3))
        self.assertTrue(check_source('backend/ai_assistant/service.py',
            'from data_security.adapters.django.content.future import Bridge', phase=3))
        self.assertTrue(check_source('backend/ai_providers/__init__.py',
            'from data_security.adapters.django.content import protect_text', phase=3))

    def test_ai_facade_has_no_sdk_or_raw_business_provider_imports(self):
        for target in ('requests', 'websockets.sync.client.connect', 'ai_providers.deepseek.DeepSeekProvider',
                       'ai_assistant.security.sanitize_output', 'audit.models.AuditEvent'):
            self.assertTrue(check_source('backend/ai_providers/__init__.py', 'import ' + target, phase=3))
        self.assertFalse(check_source('backend/ai_providers/__init__.py',
            'import asyncio\nfrom dataclasses import dataclass\nfrom data_security.contracts import AIRequest', phase=3))

    def test_bootstrap_reverse_import_is_limited_to_two_exact_startup_modules(self):
        for module, symbol in (('settings', 'framework_startup'), ('settings', 'startup_database_url'),
                               ('settings', 'startup_secret'), ('apps', 'start_application')):
            source = f'from .security_bootstrap import {symbol} as start\nstart()'
            self.assertFalse(check_source(f'backend/ctf_backend/{module}.py', source, phase=3))
            for phase in (1, 2):
                self.assertTrue(check_source(f'backend/ctf_backend/{module}.py', source, phase=phase))
            self.assertTrue(check_source(f'backend/ctf_backend/{module}.py',
                'from .security_bootstrap import assemble', phase=3))
        for source in ('backend/users/apps.py', 'backend/ctf_backend/wsgi.py', 'backend/data_security/__init__.py'):
            self.assertTrue(check_source(source,
                'from ctf_backend.security_bootstrap import start_application', phase=3))

    def test_future_targets_are_not_implicitly_approved_by_package_imports(self):
        for statement in ('import data_security.application.export_flow',
                          'from data_security.application import export_flow',
                          'from data_security.adapters.persistence import future',
                          'from data_security.adapters.persistence.audit.future import Sink',
                          'import data_security.adapters.persistence.audit.future'):
            self.assertTrue(check_source(path(MODULES['B']), statement, phase=3))

    def test_sink_public_callback_and_config_bypasses_remain_rejected(self):
        source = ('from audit.services import AuditLedgerService as Ledger\n'
                  'writer = Ledger\nwriter.append_entry(payload={})')
        self.assertIn('AUDIT_SINK_PUBLIC_CALLBACK', {
            item.code for item in check_source(path(MODULES['M6']), source, phase=3)})
        for owner in ('M6', 'M7', 'M9'):
            source = 'import os as environment\nget = environment.getenv\nget("reference")'
            self.assertTrue(check_source(path(MODULES[owner]), source, phase=3))
        for module in ('audit.bridge', 'ai_providers', 'users.views', *MODULES.values()):
            for source in ('loader = __import__\nloader("module")',
                           'import importlib as loader\nloader.import_module("module")'):
                self.assertTrue(check_source(path(module), source, phase=3))

    def test_phase1_and_phase2_business_negatives_stay_closed(self):
        for phase in (1, 2):
            for source, target in (('ai_providers', 'data_security.contracts'),
                                   ('audit.bridge', 'data_security.contracts'),
                                   ('users.views', 'data_security.contracts'),
                                   ('ai_assistant.service', 'data_security.adapters.django.content')):
                self.assertTrue(check_source(path(source), 'import ' + target, phase=phase))

    def test_actual_current_tree_is_scanned_without_excluding_new_modules(self):
        checked, violations = scan(ROOT, phase=7)
        self.assertGreater(checked, 500)
        self.assertEqual(violations, [])


class Phase3InventoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT / '.state', prefix='phase3-dependencies-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write(self, relative, source):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
        return target

    def declaration(self, phase=3):
        return self.write('tools/data_security/phase-boundary.json',
                          json.dumps({'phase': phase, 'version': 'phase-boundary.v1'}))

    def test_approved_inventory_scanned_but_earlier_explicit_phases_stay_strict(self):
        self.declaration()
        for module in PHASE3_MODULES - PHASE2_MODULES:
            self.write(path(module), 'from data_security.contracts import ProtectionError\n')
        count, found = scan(self.root)
        self.assertEqual(count, len(PHASE3_MODULES - PHASE2_MODULES))
        self.assertEqual(found, [])
        for phase in (1, 2):
            _, found = scan(self.root, phase=phase)
            self.assertIn(f'PHASE{phase}_FUTURE_IMPLEMENTATION', {v.code for v in found})

    def test_missing_or_older_declaration_does_not_enable_phase3(self):
        self.write(path(MODULES['M5']), 'from data_security.contracts import KeyReference\n')
        self.assertIn('PHASE1_FUTURE_IMPLEMENTATION', {v.code for v in scan(self.root)[1]})
        self.declaration(2)
        self.assertIn('PHASE2_FUTURE_IMPLEMENTATION', {v.code for v in scan(self.root)[1]})

    def test_unknown_boolean_extra_malformed_or_symlink_declaration_rejected(self):
        for value in ({'phase': 8, 'version': 'phase-boundary.v1'},
                      {'phase': True, 'version': 'phase-boundary.v1'},
                      {'phase': 3, 'version': 'future'},
                      {'phase': 3, 'version': 'phase-boundary.v1', 'allow_everything': True},
                      ['phase', 3]):
            self.write('tools/data_security/phase-boundary.json', json.dumps(value))
            self.assertEqual(scan(self.root)[1][0].code, 'UNKNOWN_PHASE_BOUNDARY')
        declaration = self.write('tools/data_security/phase-boundary.json', '{')
        self.assertEqual(scan(self.root)[1][0].code, 'UNKNOWN_PHASE_BOUNDARY')
        declaration.unlink()
        approved = self.write('elsewhere.json', '{"phase":3,"version":"phase-boundary.v1"}')
        declaration.symlink_to(approved)
        self.assertEqual(scan(self.root)[1][0].code, 'UNKNOWN_PHASE_BOUNDARY')

    def test_future_modules_symlinks_and_migration_wiring_cannot_hide(self):
        self.declaration()
        self.write('backend/data_security/application/export_flow.py', 'value = None\n')
        self.write('backend/audit/migrations/9999_boundary_fixture.py',
                   'from data_security.application.protection import ProtectionService\n')
        target = self.write('fixture.py', 'value = None\n')
        source = self.root / 'backend/data_security/application/symlink.py'
        source.symlink_to(target)
        count, found = scan(self.root)
        self.assertEqual(count, 2)
        self.assertEqual({v.code for v in found}, {
            'PHASE3_FUTURE_IMPLEMENTATION', 'PHASE3_BUSINESS_NOT_CONNECTED', 'SOURCE_SYMLINK'})
