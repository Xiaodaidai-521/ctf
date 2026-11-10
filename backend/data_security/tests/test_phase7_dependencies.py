"""Phase-seven RAG grants remain source-specific; earlier phase probes stay strict."""
import ast
from pathlib import Path
import unittest

from tools.data_security.dependencies import PHASE7_EXTERNAL, check_source, scan

ROOT = Path(__file__).resolve().parents[3]


class Phase7DependencyTests(unittest.TestCase):
    def test_rag_grants_do_not_reopen_earlier_phases_or_other_business_modules(self):
        statement = 'from data_security.adapters.django.rag import protect_rag'
        for module in ('rag_ingestion/services.py', 'legal_kb/services/retrieval_service.py'):
            path = 'backend/' + module
            self.assertFalse(check_source(path, statement, phase=7))
            for phase in (1, 2, 3, 4, 5, 6):
                self.assertTrue(check_source(path, statement, phase=phase))
        self.assertTrue(check_source('backend/users/views.py', statement, phase=7))

    def test_rag_boundary_cannot_assemble_or_read_secrets(self):
        path = 'backend/data_security/adapters/django/rag.py'
        for statement in ('from data_security.application.protection import ProtectionService',
                          'from data_security.adapters.persistence.fields import FieldStorage',
                          'from ctf_backend.security_bootstrap import assemble_rag',
                          'from django.conf import settings', 'import os\nos.getenv("ARK_API_KEY")'):
            self.assertTrue(check_source(path, statement, phase=7))

    def test_rag_bootstrap_imports_are_exact(self):
        path = 'backend/ctf_backend/security_bootstrap.py'
        for target in PHASE7_EXTERNAL['ctf_backend.security_bootstrap']:
            self.assertFalse(check_source(path, 'import ' + target, phase=7))
        self.assertTrue(check_source(path, 'from rag_ingestion.adapters.parser_docx import OtherParser', phase=7))
        self.assertTrue(check_source('backend/rag_ingestion/services.py',
                                   'from ctf_backend.security_bootstrap import assemble_rag', phase=7))

    def test_pipeline_has_only_explicit_ports_and_no_framework_adapter_or_registry_import(self):
        tree = ast.parse((ROOT/'backend/rag_ingestion/pipeline.py').read_text())
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(set(imports), {'dataclasses', 'typing', 'uuid', 'cleaning'})
        constructor = next(node for node in ast.walk(tree)
                           if isinstance(node, ast.FunctionDef) and node.name == '__init__')
        self.assertTrue(all(default is None for default in constructor.args.kw_defaults))

    def test_http_bridge_edges_are_phase7_and_source_specific(self):
        cases = (
            ('backend/ai_assistant/views.py', 'data_security.adapters.django.content'),
            ('backend/ai_assistant/views.py', 'data_security.adapters.django.rag'),
            ('backend/ai_assistant/response_adapter.py', 'data_security.adapters.django.rag'),
            ('backend/ai_assistant/tutor_request_orchestrator.py', 'data_security.adapters.django.content'),
        )
        for path, target in cases:
            statement = f'from {target} import Boundary'
            with self.subTest(path=path, target=target):
                self.assertFalse(check_source(path, statement, phase=7))
                for phase in (1, 2, 3, 4, 5, 6):
                    self.assertTrue(check_source(path, statement, phase=phase))
                self.assertTrue(check_source('backend/ai_assistant/unlisted_view.py', statement, phase=7))

    def test_http_bridges_do_not_gain_policy_secret_sdk_or_future_imports(self):
        for path in ('backend/ai_assistant/views.py', 'backend/ai_assistant/response_adapter.py',
                     'backend/ai_assistant/tutor_request_orchestrator.py'):
            for statement in (
                'from data_security.application.protection import ProtectionService',
                'from data_security.adapters.keys import FileKeyResolver',
                'from data_security.adapters.persistence.audit import DjangoAuditSink',
                'from data_security.adapters.llm.official import OfficialAI',
                'from ctf_backend.security_bootstrap import assemble',
                'from data_security.adapters.django.rag.future import Bridge',
                'import os\nos.getenv("ARK_API_KEY")',
                'from openai import OpenAI\nOpenAI(api_key="synthetic-unused")',
            ):
                with self.subTest(path=path, statement=statement):
                    self.assertTrue(check_source(path, statement, phase=7))

    def test_current_tree_uses_declared_phase_without_exclusions(self):
        checked, findings = scan(ROOT)
        self.assertGreater(checked, 500)
        self.assertEqual(findings, [])
