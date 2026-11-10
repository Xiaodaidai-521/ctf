"""Fresh local resources and scrubbed subprocess environments for phase-1 tests."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.state'
EVIDENCE = Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-01')
PG = STATE / 'pg-install/bin'
PGROOT = STATE / 'pg-run'
# Keep mainline1's provider-free pure suite in its own original unittest process.
MAIN_TEST_LABELS = ('agent_runtime', 'agents', 'ai_assistant', 'audit', 'challenges',
                    'export_quota', 'export_risk', 'feedback_center', 'learning_analytics',
                    'learning_map', 'legal', 'legal_kb', 'rag_ingestion', 'resources',
                    'skill_review', 'student_profiles', 'test_auth', 'users')


def clean_env(*, transport=False):
    env = {'PATH': os.environ['PATH'], 'HOME': str(STATE / 'home'),
           'TMPDIR': str(STATE / 'tmp'), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1'}
    for key in ('PGHOSTADDR', 'PGPORT'):
        if key in os.environ:
            env[key] = os.environ[key]
    if transport:
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                    'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
                    'SSL_CERT_FILE', 'NODE_EXTRA_CA_CERTS', 'NODE_USE_ENV_PROXY'):
            if key in os.environ:
                env[key] = os.environ[key]
        if 'SSL_CERT_FILE' in env:
            env['PIP_CERT'] = env['SSL_CERT_FILE']
    return env


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


def identity():
    import psycopg2
    config = json.loads((STATE / 'postgres.json').read_text())
    with psycopg2.connect(host=config['socket'], port=config['port'], user='ds_phase1',
                          dbname='postgres') as db:
        with db.cursor() as cursor:
            cursor.execute('SHOW data_directory')
            if Path(cursor.fetchone()[0]).resolve() != PGROOT / 'data':
                raise RuntimeError('ISOLATED_CLUSTER_IDENTITY_MISMATCH')
    return config


def start_postgres():
    if (STATE / 'postgres.json').exists():
        config = json.loads((STATE / 'postgres.json').read_text())
        prefix = (['unshare', '--user', '--map-user=65534', '--map-group=65534', '--']
                  if os.getuid() == 0 else [])
        if (config.get('data') != str(PGROOT / 'data') or config.get('socket') != str(PGROOT)
                or config.get('namespace_prefix') != prefix or config.get('synthetic_only') is not True
                or type(config.get('port')) is not int or not 1024 <= config['port'] <= 65535
                or (PGROOT / 'data').resolve() != PGROOT / 'data'
                or (PGROOT / 'data/PG_VERSION').read_text().strip() != '16'):
            raise RuntimeError('REFUSE_TO_RESTART_UNOWNED_CLUSTER')
        status = subprocess.run(prefix + [str(PG / 'pg_ctl'), '-D', config['data'], 'status'],
                                cwd=ROOT, env=clean_env(), capture_output=True)
        if status.returncode == 3:
            label = 'postgres-owned-restart-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
            command = prefix + [str(PG / 'pg_ctl'), '-D', config['data'], '-l', str(PGROOT / 'postgres.log'),
                '-w', '-t', '30', '-o', f'-h 127.0.0.1 -p {config["port"]} -k {PGROOT} '
                '-c max_connections=40 -c log_min_messages=fatal -c log_min_error_statement=panic', 'start']
            result = run(label, command, ROOT, clean_env())
            if result:
                return result
        elif status.returncode != 0:
            raise RuntimeError('ISOLATED_CLUSTER_STATUS_UNKNOWN')
        identity()
        return 0
    if PGROOT.exists():
        raise RuntimeError('REFUSE_TO_OVERWRITE_UNOWNED_CLUSTER')
    PGROOT.mkdir(mode=0o700)
    # The workspace filesystem is accessible only by its host owner. A user
    # namespace maps that owner to nobody without patching PostgreSQL checks.
    prefix = (['unshare', '--user', '--map-user=65534', '--map-group=65534', '--']
              if os.getuid() == 0 else [])
    env = clean_env()
    env['PGPASSFILE'] = str(PGROOT / 'no-password-file')
    env['PGSERVICEFILE'] = str(PGROOT / 'no-service-file')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    commands = [
        [str(PG / 'initdb'), '-D', str(PGROOT / 'data'), '-U', 'ds_phase1',
         '--auth-local=trust', '--auth-host=trust', '--encoding=UTF8', '--locale=C'],
        [str(PG / 'pg_ctl'), '-D', str(PGROOT / 'data'), '-l', str(PGROOT / 'postgres.log'),
         '-w', '-t', '30', '-o', f'-h 127.0.0.1 -p {port} -k {PGROOT} '
         '-c max_connections=40 -c log_min_messages=fatal -c log_min_error_statement=panic', 'start'],
    ]
    with (EVIDENCE / 'postgres-bootstrap.log').open('a') as output:
        os.chmod(output.name, 0o600)
        for command in commands:
            result = subprocess.run(prefix + command, cwd=ROOT, env=env,
                                    stdout=output, stderr=subprocess.STDOUT)
            if result.returncode:
                return result.returncode
    config = {'socket': str(PGROOT), 'port': port, 'data': str(PGROOT / 'data'),
              'user': 'ds_phase1', 'namespace_prefix': prefix,
              'version': '16.13', 'pgvector': '0.8.1', 'synthetic_only': True}
    dump(STATE / 'postgres.json', config)
    identity()
    import psycopg2
    db = psycopg2.connect(host=config['socket'], port=port, user='ds_phase1', dbname='postgres')
    db.autocommit = True
    with db.cursor() as cursor:
        cursor.execute('CREATE ROLE mainline1_test LOGIN CREATEDB')
        for name in ('ds_phase1_main', 'ds_phase1_export', 'ds_phase1_mainline'):
            owner = 'mainline1_test' if name == 'ds_phase1_mainline' else 'ds_phase1'
            cursor.execute('CREATE DATABASE ' + name + ' OWNER ' + owner)
    db.close()
    dump(EVIDENCE / 'postgres-resource.json', config)
    return 0


def environment():
    config = identity()
    env = clean_env()
    env.update({'PYTHONPATH': str(ROOT), 'DATA_SECURITY_ISOLATED_TEST': '1',
                'DS_TEST_PG_SOCKET': config['socket'], 'DS_TEST_PG_PORT': str(config['port']),
                'MAINLINE1_TEST_PORT': str(config['port']), 'DB_HOST': config['socket'],
                'DB_PORT': str(config['port']), 'DB_NAME': 'ds_phase1_main', 'DB_USER': 'ds_phase1',
                'SECRET_KEY': secrets.token_urlsafe(48), 'DEBUG': 'true', 'ALLOWED_HOSTS': 'testserver,localhost',
                'CONTROLLED_EXPORT_VAR_DIR': str(STATE / 'export'),
                'CONTROLLED_EXPORT_PRIVATE_ROOT': str(STATE / 'export/private'),
                'PGPASSFILE': str(PGROOT / 'no-password-file'), 'PGSERVICEFILE': str(PGROOT / 'no-service-file')})
    return env


def run(label, command, cwd, env):
    if not cwd.resolve().is_relative_to(ROOT):
        raise RuntimeError('COMMAND_OUTSIDE_ISOLATION')
    if not label or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in label):
        raise ValueError('INVALID_EVIDENCE_LABEL')
    output_path = EVIDENCE / (label + '.log')
    if output_path.exists():
        raise RuntimeError('EVIDENCE_ALREADY_EXISTS_USE_NEW_LABEL')
    started = datetime.now(timezone.utc)
    with output_path.open('w') as output:
        os.chmod(output_path, 0o600)
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    record = {'label': label, 'command': command, 'cwd': str(cwd),
              'exit_code': result.returncode, 'started_at': started.isoformat(),
              'finished_at': datetime.now(timezone.utc).isoformat(),
              'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'output': str(output_path), 'output_sha256': hashlib.sha256(output_path.read_bytes()).hexdigest()}
    dump(EVIDENCE / (label + '.json'), record)
    print(json.dumps(record, ensure_ascii=False))
    return result.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['pg-start', 'pg-stop', 'main-check', 'main-drift', 'main-tests', 'main-domain-tests',
                                         'export-check', 'export-drift', 'export-tests', 'mainline-unit',
                                         'mainline-check', 'mainline-drift', 'mainline-postgres',
                                         'mainline-migrate', 'mainline-rollback',
                                         'frontend-install', 'frontend-build'])
    parser.add_argument('--label')
    args = parser.parse_args()
    if ROOT != Path('/home/hatch/workspace/ctf-data-security') or Path.cwd() != ROOT:
        parser.error('run only from the isolated worktree root')
    if args.action == 'pg-start':
        return start_postgres()
    if args.action == 'pg-stop':
        config = identity()
        return subprocess.call(config['namespace_prefix'] + [str(PG / 'pg_ctl'), '-D', config['data'],
                               '-w', '-m', 'fast', 'stop'], cwd=ROOT, env=clean_env())
    if not args.label:
        parser.error('--label is required for immutable evidence')
    python = str(ROOT / '.venv/bin/python')
    if args.action.startswith('frontend-'):
        pnpm = str(STATE / 'node-tools/node_modules/.bin/pnpm')
        env = clean_env(transport=args.action == 'frontend-install')
        env['XDG_CACHE_HOME'] = str(STATE / 'cache')
        env['XDG_DATA_HOME'] = str(STATE / 'share')
        command = ([pnpm, 'install', '--frozen-lockfile', '--store-dir', str(STATE / 'pnpm-store')]
                   if args.action == 'frontend-install' else [pnpm, 'run', 'build'])
        return run(args.label, command, ROOT / 'frontend', env)
    if args.action == 'mainline-unit':
        return run(args.label, [python, '-B', '-m', 'unittest', 'discover', '-s', 'mainline1/tests', '-v'],
                   ROOT / 'backend', clean_env())
    env = environment()
    if args.action.startswith('mainline-'):
        env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.mainline_test_settings'
        command = [python, '-B', '-m', 'django']
        operation = args.action.removeprefix('mainline-')
        if operation == 'check':
            command += ['check']
        elif operation == 'drift':
            command += ['makemigrations', '--check', '--dry-run']
        elif operation == 'postgres':
            command += ['test', 'mainline1.tests.postgres_cases',
                        'mainline1.tests.postgres_review_cases', 'mainline1.tests.postgres_planning_cases',
                        'mainline1.tests.postgres_operations_cases', '--noinput', '-v', '2']
        else:
            command += ['migrate', 'mainline1']
            if operation == 'rollback':
                command += ['zero']
            command += ['--noinput']
        return run(args.label, command, ROOT / 'backend', env)
    domain, operation = args.action.split('-', 1)
    cwd = ROOT / ('backend' if domain == 'main' else 'tasks/controlled-export-execution')
    env['DJANGO_SETTINGS_MODULE'] = ('tools.data_security.test_settings' if domain == 'main'
                                     else 'tools.data_security.export_test_settings')
    command = [python, '-B', 'manage.py']
    if operation == 'check':
        command += ['check']
    elif operation == 'drift':
        command += ['makemigrations', '--check', '--dry-run']
    else:
        command += ['test', '--noinput', '-v', '2']
        if domain == 'export':
            command += ['controlled_export']
        elif operation == 'domain-tests':
            command += list(MAIN_TEST_LABELS)
    return run(args.label, command, cwd, env)


if __name__ == '__main__':
    raise SystemExit(main())
