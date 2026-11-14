"""Own a distinct synthetic PostgreSQL test database and record each run."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.full_audit.run import clean_env, config_and_identity

OUT = Path(__file__).resolve().parent
label = sys.argv[1]
targets = sys.argv[2:] or ['learning_analytics.test_audit_scheduler', 'skill_review.tests.test_audit_handoff']
config = config_and_identity()
env = clean_env()
env.update(FULL_AUDIT_LEGACY='1', FULL_AUDIT_TEST_DB='test_audit_runtime_fixes_retry',
           FULL_AUDIT_RESULT=str(OUT / (label + '.json')),
           MAINLINE1_TEST_PORT=str(config['port']), FULL_AUDIT_NETWORK_PORT=str(config['port']))
command = [sys.executable, '-B', str(ROOT / 'tools/full_audit/batch.py'), '--entry', 'django',
           'test', *targets, '--noinput', '--keepdb', '--verbosity', '2']
started = time.monotonic()
with (OUT / (label + '.log')).open('w', encoding='utf-8') as output:
    result = subprocess.run(command, env=env, cwd=ROOT / 'backend', stdout=output,
                            stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
record = {'test_database': env['FULL_AUDIT_TEST_DB'], 'synthetic_only': True,
          'command': command, 'exit_code': result.returncode,
          'elapsed_seconds': round(time.monotonic() - started, 2)}
(OUT / (label + '-command.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record))
result_path = OUT / (label + '.json')
if result_path.exists():
    data = json.loads(result_path.read_text('utf-8'))
    print(json.dumps({key: data[key] for key in ('tests', 'failures', 'errors', 'skipped')}, ensure_ascii=False))
raise SystemExit(result.returncode)
