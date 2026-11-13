"""Run targeted regressions with synthetic data and the scrubbed audit environment."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.full_audit.run import clean_env, config_and_identity

config_and_identity()
env = clean_env()
env['FULL_AUDIT_LEGACY'] = '1'
output = Path(__file__).parent
label = sys.argv[1]
if not label or len(label) > 24 or any(char not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for char in label):
    raise ValueError('Safe audit label required')
env['FULL_AUDIT_TEST_DB'] = 'test_full_audit_rerun_features_' + label.replace('-', '_')
env['FULL_AUDIT_RESULT'] = str(output / f'{label}.json')
command = [sys.executable, '-B', str(ROOT / 'backend/manage.py'), 'test',
           *sys.argv[2:], '--noinput', '--verbosity', '1']
with (output / f'{label}.log').open('w', encoding='utf-8') as stream:
    result = subprocess.run(command, cwd=ROOT / 'backend', env=env,
        creationflags=subprocess.CREATE_NO_WINDOW, stdout=stream, stderr=subprocess.STDOUT)
(output / f'{label}-command.json').write_text(json.dumps({
    'command': command, 'exit_code': result.returncode,
    'synthetic_database_only': True,
    'test_database': env['FULL_AUDIT_TEST_DB'],
}, indent=2), encoding='utf-8')
print(json.dumps({'exit_code': result.returncode, 'label': label}))
sys.exit(result.returncode)
