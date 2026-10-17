"""Offline step-07 regression, proposed example checks and preservation evidence."""
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
files = ['backend/mainline1/' + name for name in ('planning.py', 'review.py', 'review_repository.py',
    'tests/test_planning.py', 'tests/postgres_planning_cases.py', 'tests/run_planning_postgres.py',
    'tests/run_isolated_postgres.py')]
for name in files:
    ast.parse((ROOT / name).read_text(encoding='utf-8'), filename=name)
baseline = json.loads((DOCS / 'step-07-input-state.json').read_text(encoding='utf-8'))
changed = [p for p, digest in baseline.items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != digest]
allowed = {'backend/mainline1/review.py', 'backend/mainline1/review_repository.py',
           'backend/mainline1/tests/run_isolated_postgres.py', 'backend/mainline1/README.md',
           'docs/mainline1/HANDOFF.md'}
unexpected = sorted(set(changed) - allowed)
sys.path.insert(0, str(ROOT / 'backend'))
from mainline1.tests.test_planning import PlanningTests
from mainline1.planning import PlanPolicy, plan_digest
import jsonschema

fixture = PlanningTests()
fixture.setUp()
plan = fixture.build()
first = fixture.service.page(fixture.actor, plan['plan_id'], page_size=1)
second = fixture.service.page(fixture.actor, plan['plan_id'], page_size=1, cursor=first['next_cursor'])
fixture.source.synthetic_usable = False
fixture.source.policy = PlanPolicy()
draft = fixture.build('draft')
schema = json.loads((DOCS / 'contracts/schema.json').read_text(encoding='utf-8'))
validator = jsonschema.Draft202012Validator({'$ref': '#/$defs/RedactionPlan', '$defs': schema['$defs']},
    format_checker=jsonschema.FormatChecker())
for value in (plan, draft):
    validator.validate(value)
assert plan_digest(dict(first['plan_header'], operations=first['operations'] + second['operations'])) == plan['plan_hash']
# Test-only cursor key is never serialized. Real deployments supply their own key.
example = dict(approval_status='Proposed', synthetic_only=True,
    note='ready uses fictitious test approvals and a test-only usable state; real draft state stays invalid. No execution or authorization.',
    ready=plan, actual_draft=draft,
    pages=[{k: v for k, v in page.items() if k != 'next_cursor'} for page in (first, second)],
    consumer_steps=['Authenticate and authorize', 'Collect immutable pages and verify full plan hash',
        'Query current asset/applicability/requirements/policy; validate again immediately before execution',
        'Execution owner must prevent changes between check and use and obtain separate outbound authorization'])
(DOCS / 'plan-examples-v1.json').write_text(json.dumps(example, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
evidence = dict(recorded_at=datetime.now(timezone.utc).isoformat(), command='python -B -m unittest discover -s mainline1/tests -v',
    cwd='backend', exit_code=result.returncode, status='Passed' if result.returncode == 0 else 'Failed',
    stdout=result.stdout, stderr=result.stderr, ast_status='Passed', example_status='Passed',
    source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
    changed_existing_files=changed, unexpected_existing_changes=unexpected,
    preservation_status='Passed' if not unexpected else 'Failed',
    real_parser_and_rules='Executed on synthetic inputs', authority_acl_and_approval='Test doubles only',
    live_semantic='Untested; zero calls', actual_execution='Untested; not connected',
    postgres_evidence='step-07-postgres-verification.json; separate isolated real PostgreSQL tests',
    public_contract='Proposed; prior schema/examples/catalog unchanged')
(DOCS / 'step-07-verification.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: evidence[k] for k in ('status', 'ast_status', 'example_status', 'preservation_status')}))
print(result.stderr[-180:])
raise SystemExit(result.returncode or bool(unexpected))
