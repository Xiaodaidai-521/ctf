"""Read-only runtime recheck. Never emits environment values or Compose secrets."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values
import yaml

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
phase = sys.argv[1] if len(sys.argv) > 1 else 'before'


def run(argv, env=None):
    try:
        result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
        return {'exit_code': result.returncode, 'stdout': result.stdout.strip(),
                'stderr': result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {'exit_code': None, 'timed_out': True}


values = dotenv_values(ROOT / '.env')
compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text('utf-8'))
services = compose['services']
checks = {
    'scope': 'read-only runtime and Compose structure; no deployment or production database access',
    'observed_at_utc': datetime.now(timezone.utc).isoformat(),
    'python': sys.version,
    'django_version': __import__('django').get_version(),
    'pip_check': run([sys.executable, '-m', 'pip', 'check']),
    'docker_server': run(['docker', 'version', '--format', '{{json .Server}}']),
    'hypervisor_present': run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                               '(Get-CimInstance Win32_ComputerSystem).HypervisorPresent']),
    'external_paths_configured': {
        name: bool(values.get(name) or os.environ.get(name))
        for name in ('TLS_CERT_DIR', 'FRPS_CONFIG_FILE')
    },
    'feature_gates_enabled': {
        name: str(os.environ.get(name, values.get(name) or 'false')).lower() in ('true', '1', 'yes')
        for name in ('PRACTICAL_TRAINING_ENABLED', 'FEEDBACK_PHASE3_ENABLED',
                     'FEEDBACK_PHASE3_RELEASE_ENABLED', 'EVALUATION_LIVE_GATEWAY_ENABLED')
    },
    'analytics_scheduler_depends_on': services['analytics-scheduler']['depends_on'],
    'container_cleanup_depends_on': services['container-cleanup']['depends_on'],
    'compose_actual_environment': run(['docker', 'compose', 'config', '--quiet']),
}
temporary_env = os.environ.copy()
temporary_env.update({'TLS_CERT_DIR': str(OUT / 'fixture-tls'),
                      'FRPS_CONFIG_FILE': str(OUT / 'fixture-frps.ini')})
checks['compose_fixture_paths'] = run(['docker', 'compose', 'config', '--quiet'], temporary_env)
checks['fixture_paths_are_not_deployment_evidence'] = True

old = json.loads((ROOT / 'artifacts/full-audit-20261113/runtime-code-hashes.json').read_text('utf-8'))
checks['source_hash_comparison'] = {
    name: {'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
           'same_as_prior_evidence': hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest}
    for name, digest in old.items()
}
checks['start_sh_crlf_count'] = (ROOT / 'backend/start.sh').read_bytes().count(b'\r\n')
(OUT / f'runtime-{phase}.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in checks.items() if key != 'source_hash_comparison'}, ensure_ascii=False, indent=2))
