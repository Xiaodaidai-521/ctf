"""Local synthetic verification only. No model/DB/credential loading."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs/mainline1'
sys.path.insert(0, str(ROOT / 'backend'))
from mainline1.parsing import AssetRef, ParserConfig, parse_table
from mainline1.semantic import SemanticConfig, cell_key
from mainline1.semantic_smoke import abc_preflight
from mainline1.tests.test_rules import RuleTests, V


def write(name, data):
    (DOCS / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


fixture = json.loads((DOCS / 'step-05-smoke-fixture.json').read_text(encoding='utf-8'))
fx = RuleTests()
fx.setUp()
raw = fixture['csv_utf8'].encode('utf-8')
parsed = fx.parse_bytes(raw)
context_parse = parse_table(raw, AssetRef(V, 'test-domain', parsed.input_content_hash, 'csv', len(raw),
                                        'private:synthetic-smoke'), config=ParserConfig(include_header=True))
rule = fx.scan(parsed, context=fx.context(parsed, scenario=fixture['scenario']))
preflight = abc_preflight(parsed, rule, SemanticConfig(),
                         target_keys=[cell_key(parsed.cells[i]) for i in fixture['target_indices']],
                         context_parsed=context_parse)
write('step-05-smoke.json', dict(fixture_version=fixture['version'], asset_hash=parsed.input_content_hash,
      preflight=preflight, actual_live_calls=0, real_backend='Blocked', independent_effectiveness='Untested',
      proposals=dict(total_B_C_calls=6, retries=0, max_output_tokens_per_call=1000,
                     max_input_bytes_per_call=16000, timeout_seconds_per_call=20,
                     currency=None, total_cost_limit=None, approved=False)))
command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'mainline1/tests', '-v']
result = subprocess.run(command, cwd=ROOT / 'backend', capture_output=True, encoding='utf-8',
                        env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=120)
files = ['backend/mainline1/' + name for name in
         ['semantic.py', 'fusion.py', 'semantic_smoke.py', 'tests/test_semantic.py']]
for name in files:
    ast.parse((ROOT / name).read_text(encoding='utf-8'), filename=name)
initial = json.loads((DOCS / 'step-05-input-state.json').read_text(encoding='utf-8'))
changed = [name for name, digest in initial.items()
           if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
allowed = {'backend/mainline1/README.md', 'docs/mainline1/HANDOFF.md', 'docs/mainline1/acceptance.md'}
unexpected = sorted(set(changed) - allowed)
git = subprocess.run(['git', 'status', '--short'], cwd=ROOT, capture_output=True, encoding='utf-8', check=True)
evidence = dict(recorded_at=datetime.now(timezone.utc).isoformat(),
    command='python -B -m unittest discover -s mainline1/tests -v', cwd='backend',
    status='Passed' if result.returncode == 0 else 'Failed', exit_code=result.returncode,
    stdout=result.stdout, stderr=result.stderr, ast_files=files, ast_status='Passed',
    tested_source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
    changed_existing_files=changed, unexpected_existing_changes=unexpected,
    preservation_status='Passed' if not unexpected else 'Failed', git_status=git.stdout,
    real_model='Blocked; zero network calls; transport constructor uses a test double',
    budget_branch='local synthetic receipt/double only; no genuine approval or priced calls',
    database='Not rerun; unchanged code; historical step-03 evidence remains separately scoped',
    effectiveness='Untested; preflight does not measure A/B/C effectiveness')
write('step-05-verification.json', evidence)
print(json.dumps({k: evidence[k] for k in ['status', 'ast_status', 'preservation_status']}, ensure_ascii=False))
print(result.stderr[-300:])
sys.exit(result.returncode or bool(unexpected))
