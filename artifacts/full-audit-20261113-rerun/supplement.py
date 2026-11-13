"""Supplementary pure, real PostgreSQL and management checks; synthetic only."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.full_audit.batch import execute
from tools.full_audit.run import config_and_identity

config = config_and_identity()
evidence = Path(__file__).parent / 'supplement'
evidence.mkdir(exist_ok=True)
# The subprocess test intentionally uses its original mainline1_test role.
# Provision it only after proving this cluster is the owned synthetic cluster.
import psycopg2
with psycopg2.connect(host='127.0.0.1', port=config['port'], user='full_audit', dbname='postgres') as db:
    with db.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='mainline1_test'")
        if cursor.fetchone() is None:
            cursor.execute('CREATE ROLE mainline1_test LOGIN CREATEDB')

jobs = [
    ('mainline-pure', ['discover', '-s', 'mainline1/tests', '-p', 'test*.py'], None, True, None, None),
    ('mainline-postgres', ['test', 'mainline1.tests.postgres_cases', 'mainline1.tests.postgres_review_cases',
        'mainline1.tests.postgres_operations_cases', 'mainline1.tests.postgres_planning_cases',
        'mainline1.tests.postgres_parsed_artifact_cases', '--noinput', '-v', '2'],
        'tools.full_audit.mainline_settings', False, {'FULL_AUDIT_MAINLINE_USER': 'mainline1_test'}, None),
    ('tool-pure', ['tools.data_security.test_phase4_evidence',
        'tools.data_security.test_phase6_plaintext_scan'], None, True, None, None),
    ('check', ['check'], None, False, None, None),
    ('migration-check', ['makemigrations', '--check', '--dry-run'], None, False, None, None),
    ('migration-plan', ['showmigrations', '--plan'], None, False, None, None),
]
task_root = ROOT / 'tasks' / 'controlled-export-execution'
export_env = {
    'PYTHONPATH': os.pathsep.join((str(ROOT), str(ROOT / 'backend'), str(task_root))),
    'CONTROLLED_EXPORT_DATABASE_URL': f"postgres://full_audit@127.0.0.1:{config['port']}/full_audit",
    'CONTROLLED_EXPORT_ALLOWED_HOSTS': 'testserver,localhost,127.0.0.1',
}
jobs.append(('controlled-export', ['test', 'controlled_export', '--noinput', '-v', '1'],
             'tools.full_audit.export_settings', False, export_env, task_root))
records = {}
with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(execute, label, arguments, evidence, config, settings, unit, extra, cwd)
               for label, arguments, settings, unit, extra, cwd in jobs]
    for future in futures:
        label, record = future.result()
        records[label] = record
(evidence / 'summary.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
raise SystemExit(any(record['exit_code'] for record in records.values()))
