"""Local retirement guards; never import dormant settings or transport clients."""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class DormantCompatibilityTests(unittest.TestCase):
    def test_frp_token_is_an_empty_placeholder(self):
        source = ROOT / 'backend/ctf_backend/frp_settings.py'
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        tokens = [node.value for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'FRP_TOKEN'
                          for target in node.targets)]
        self.assertEqual(len(tokens), 1)
        self.assertTrue(isinstance(tokens[0], ast.Constant) and tokens[0].value == '')

    def test_semantic_module_has_no_sdk_import(self):
        source = ROOT / 'backend/mainline1/semantic.py'
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or '')
        self.assertFalse(any(name.split('.')[0] in {'langchain_openai', 'openai'} for name in imports))

    def test_views_no_longer_expose_the_unused_teaching_builder(self):
        source = ROOT / 'backend/ai_assistant/views.py'
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        self.assertFalse(any(isinstance(node, ast.FunctionDef) and node.name == '_build_teaching_context'
                             for node in ast.walk(tree)))
        self.assertFalse(any(isinstance(node, ast.Name) and node.id == 'TeachingContextBuilder'
                             for node in ast.walk(tree)))
