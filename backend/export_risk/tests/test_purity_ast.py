"""Purity guard for the judgment core (regex spec E1; review R7 guardrail).

Statically scans every module under export_risk/judgment/ and fails if it imports
non-pure modules or uses side-effecting attributes (ORM `.objects`, clock `.now`,
file/eval builtins). This is an engineering guardrail, not a proof of purity;
assertNumQueries(0) is added in M1 once the package is Django-loadable.
"""

import ast
import os
import unittest

import export_risk.judgment as judgment_pkg

ALLOWED_IMPORT_ROOTS = {
    "dataclasses", "typing", "enum", "collections", "functools",
    "itertools", "math", "decimal", "__future__",
    # datetime is pure value math (parse/compare ISO timestamps for authorization
    # validity, review F2); clock reads are still banned via BANNED_ATTRS below.
    "datetime",
}
# Clock reads stay banned so adding `datetime` cannot smuggle in a clock: the
# judgment core must compare the injected evaluation_time, never read "now".
BANNED_ATTRS = {"objects", "now", "utcnow", "today"}
BANNED_CALL_NAMES = {"open", "eval", "exec", "compile", "__import__"}


def _judgment_py_files():
    pkg_dir = os.path.dirname(judgment_pkg.__file__)
    for name in sorted(os.listdir(pkg_dir)):
        if name.endswith(".py"):
            yield os.path.join(pkg_dir, name)


class PurityASTTests(unittest.TestCase):
    def test_judgment_modules_are_pure(self):
        offenders = []
        for path in _judgment_py_files():
            with open(path, "r", encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
            base = os.path.basename(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level and node.level > 0:
                        continue  # relative import within the package is fine
                    root = (node.module or "").split(".")[0]
                    if root not in ALLOWED_IMPORT_ROOTS:
                        offenders.append(f"{base}: import from '{node.module}'")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        if root not in ALLOWED_IMPORT_ROOTS:
                            offenders.append(f"{base}: import '{alias.name}'")
                elif isinstance(node, ast.Attribute):
                    if node.attr in BANNED_ATTRS:
                        offenders.append(f"{base}: attribute '.{node.attr}'")
                elif isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id in BANNED_CALL_NAMES:
                        offenders.append(f"{base}: call '{func.id}()'")
        self.assertEqual(offenders, [], f"impure constructs in judgment core: {offenders}")

    def test_scanner_finds_at_least_the_core(self):
        files = {os.path.basename(p) for p in _judgment_py_files()}
        self.assertIn("core.py", files)
        self.assertIn("hard_constraints.py", files)


if __name__ == "__main__":
    unittest.main()
