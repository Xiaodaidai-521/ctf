"""Owned-cluster supplementary PostgreSQL suites; keep synthetic DBs to avoid repeated checkpoints."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.full_audit.batch import execute
from tools.full_audit.run import config_and_identity

config = config_and_identity()
evidence = Path(__file__).resolve().parent
task = ROOT / 'tasks/controlled-export-execution'
extra = {
    'PYTHONPATH': os.pathsep.join((str(ROOT), str(ROOT / 'backend'), str(task))),
    'CONTROLLED_EXPORT_DATABASE_URL': f"postgres://full_audit@127.0.0.1:{config['port']}/full_audit",
    'CONTROLLED_EXPORT_ALLOWED_HOSTS': 'testserver,localhost,127.0.0.1',
}
jobs = [
    ('recheck-rt-mainline-postgres', ['test', 'mainline1.tests.postgres_cases',
        'mainline1.tests.postgres_review_cases', 'mainline1.tests.postgres_operations_cases',
        'mainline1.tests.postgres_planning_cases', 'mainline1.tests.postgres_parsed_artifact_cases',
        '--noinput', '--keepdb', '-v', '2'], 'tools.full_audit.mainline_settings',
        {'FULL_AUDIT_MAINLINE_USER': 'mainline1_test'}, None),
    ('recheck-rt-export-final', ['test', 'controlled_export', '--noinput', '--keepdb', '-v', '1'],
        'tools.full_audit.export_settings', extra, task),
]
records = {}
for label, arguments, settings, env, cwd in jobs:
    _, record = execute(label, arguments, evidence, config, settings=settings, extra_env=env, cwd=cwd)
    records[label] = {key: value for key, value in record.items() if key != 'source_hashes_before'}
    (evidence / 'postgres-summary.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
raise SystemExit(any(record['exit_code'] for record in records.values()))
