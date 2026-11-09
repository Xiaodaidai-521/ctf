"""Explicit synthetic-cluster acceptance, with keys kept out of E3 and the repo.

Usage: .venv/bin/python -m tools.data_security.phase3_backup_verify --tools ROOT
Downloads/installations are deliberately not part of this runner.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--controlled-parent', type=Path,
        default=Path('/home/hatch/workspace/data-security-seven-phases/isolated-material'))
    parser.add_argument('--evidence', type=Path,
        default=Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-03'))
    args = parser.parse_args()
    controlled_parent = args.controlled_parent.resolve()
    if controlled_parent.is_relative_to(ROOT) or controlled_parent.is_relative_to(args.evidence.resolve()):
        raise RuntimeError('KEY_MATERIAL_MUST_STAY_OUTSIDE_REPOSITORY_AND_EVIDENCE')
    args.controlled_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    controlled = Path(tempfile.mkdtemp(prefix='phase3-backup-', dir=args.controlled_parent))
    env = dict(os.environ, DS_PHASE3_BACKUP_RUN='1', DS_PHASE3_TOOLS=str(args.tools.resolve()),
        DS_PHASE3_CONTROLLED=str(controlled), PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT / 'backend'))),
        PYTHONDONTWRITEBYTECODE='1', DJANGO_SETTINGS_MODULE='ctf_backend.settings',
        SECRET_KEY=secrets.token_urlsafe(64), DEBUG='False', ALLOWED_HOSTS='localhost,127.0.0.1',
        DATA_SECURITY_CONFIG='', DATABASE_URL='', DATABASE_BACKEND='postgres',
        DB_TRANSPORT='local', DB_SSLMODE='disable')
    run = subprocess.run([sys.executable, '-B', '-m', 'unittest',
        'tools.data_security.phase3_backup_cases', '-v'], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # unittest output contains only synthetic test names, fixed errors and tracebacks.
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    log = args.evidence / ('phase3-backup-' + timestamp + '.log')
    with os.fdopen(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
        output.write(run.stdout)
    version = subprocess.check_output([str(args.tools / 'usr/bin/age'), '--version'], text=True).strip()
    evidence = {'scope': 'dedicated local PostgreSQL, synthetic only; database-only recovery',
        'returncode': run.returncode, 'log': log.name,
        'log_sha256': hashlib.sha256(run.stdout).hexdigest(), 'age_version': version,
        'age_package': '1.1.1-1ubuntu0.24.04.3', 'age_license': 'BSD-3-Clause',
        'age_package_sha512': 'd78a9642282acaf9b673e383dfab5f144c9c1c9ea3bd06ef0c9be1e8c10f084ed7f2db2496d097c6d3a8328b25cf865daf878b397c015c685f48680db8bb5825',
        'postgresql_version': '16.13', 'postgresql_license': 'PostgreSQL',
        'psycopg2_version': '2.9.10', 'psycopg2_license': 'LGPL-3.0-or-later with OpenSSL exception',
        'key_material_in_evidence': False, 'production_rotation_verified': False,
        'retention_rpo_rto_claimed': False, 'security_update_owner': 'deployment maintainer; review before deployment',
        'dependency_license_metadata': {'age_debian_packaging': 'GPL-3.0-or-later',
            'age_vendored_components': ['MIT', 'ISC']}}
    observations = controlled / 'observations.json'
    if observations.exists():
        evidence['recovery_observations'] = json.loads(observations.read_text())
    formal_observations = controlled / 'formal-observations.json'
    if formal_observations.exists():
        evidence['formal_backup_composition'] = json.loads(formal_observations.read_text())
    with os.fdopen(os.open(args.evidence / ('phase3-backup-' + timestamp + '.json'),
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
        json.dump(evidence, output, sort_keys=True, indent=2)
    sys.stdout.buffer.write(run.stdout)
    return run.returncode


if __name__ == '__main__':
    raise SystemExit(main())
