"""Offline synthetic regression, source preservation and actual evidence capture."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs/mainline1'
command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'mainline1/tests', '-v']
result = subprocess.run(command, cwd=ROOT / 'backend', capture_output=True, encoding='utf-8',
    env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=120)
files = ['backend/mainline1/' + name for name in ['review.py', 'review_repository.py', 'models.py',
    'migrations/0002_reviewledger.py', 'tests/test_review.py', 'tests/postgres_review_cases.py',
    'tests/run_review_postgres.py', 'tests/run_isolated_postgres.py']]
for name in files:
    ast.parse((ROOT / name).read_text(encoding='utf-8'), filename=name)
baseline = json.loads((DOCS / 'step-06-input-state.json').read_text(encoding='utf-8'))
changed = [p for p, digest in baseline.items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != digest]
allowed = {'backend/mainline1/models.py', 'backend/mainline1/tests/run_isolated_postgres.py',
           'backend/mainline1/README.md', 'docs/mainline1/HANDOFF.md'}
unexpected = sorted(set(changed) - allowed)
evidence = dict(recorded_at=datetime.now(timezone.utc).isoformat(), command='python -B -m unittest discover -s mainline1/tests -v',
    cwd='backend', exit_code=result.returncode, status='Passed' if result.returncode == 0 else 'Failed',
    stdout=result.stdout, stderr=result.stderr, ast_status='Passed',
    source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
    changed_existing_files=changed, unexpected_existing_changes=unexpected,
    preservation_status='Passed' if not unexpected else 'Failed',
    real_rules='Executed on fixed synthetic inputs', real_semantic='Blocked; zero live calls',
    memory_tests='Local threads only; production owner and event delivery use test doubles',
    postgres_evidence='step-06-postgres-verification.json; separate real isolated cluster tests',
    public_contract='Proposed, unchanged', external_event_delivery='Not connected; never claimed as real delivery')
(DOCS / 'step-06-verification.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: evidence[k] for k in ('status', 'ast_status', 'preservation_status')}))
print(result.stderr[-180:])
raise SystemExit(result.returncode or bool(unexpected))
