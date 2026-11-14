"""Bootstrap an isolated cluster or execute a check with a scrubbed environment.

Usage: python tools/full_audit/run.py --bootstrap
       python tools/full_audit/run.py --label baseline test --noinput --verbosity 1
Only this task's local cluster is accepted. Existing services are never changed.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.state' / 'full-audit-20261113'
EVIDENCE = ROOT / 'artifacts' / 'full-audit-20261113'
PG_BIN = Path('C:/Program Files/PostgreSQL/16/bin')


def clean_env():
    names = ('PATH', 'SystemRoot', 'SYSTEMROOT', 'COMSPEC', 'TEMP', 'TMP',
             'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMDATA')
    env = {key: os.environ[key] for key in names if key in os.environ}
    env.update({
        'PYTHONPATH': str(ROOT) + os.pathsep + str(ROOT / 'backend'),
        'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1',
        'SECRET_KEY': secrets.token_urlsafe(48), 'DEBUG': 'true',
        'ALLOWED_HOSTS': 'testserver,localhost,127.0.0.1',
        'FULL_AUDIT_ISOLATED': '1', 'DATABASE_BACKEND': 'sqlite',
        'SQLITE_DATABASE_PATH': str(STATE / 'unused.sqlite3'),
        'DJANGO_SETTINGS_MODULE': 'tools.full_audit.settings',
        'DB_TRANSPORT': 'local', 'DB_SSLMODE': 'disable',
        'CONTROLLED_EXPORT_VAR_DIR': str(STATE / 'export'),
        'CONTROLLED_EXPORT_PRIVATE_ROOT': str(STATE / 'export' / 'private'),
        'PGPASSFILE': str(STATE / 'no-password-file'),
        'PGSERVICEFILE': str(STATE / 'no-service-file'),
    })
    native = STATE / 'native-magic' / 'dll'
    if (native / 'magic.mgc').exists():
        env['PATH'] = str(native) + os.pathsep + env.get('PATH', '')
        env['MAGIC'] = str(native / 'magic.mgc')
    return env


def call(command, **kwargs):
    return subprocess.run(command, env=clean_env(), cwd=ROOT,
                          creationflags=subprocess.CREATE_NO_WINDOW, **kwargs)


def config_and_identity():
    import psycopg2
    config = json.loads((STATE / 'postgres.json').read_text())
    if config.get('data') != str(STATE / 'pgdata') or config.get('synthetic_only') is not True:
        raise RuntimeError('FULL_AUDIT_CLUSTER_NOT_OWNED')
    with psycopg2.connect(host='127.0.0.1', port=config['port'], user='full_audit', dbname='postgres') as db:
        with db.cursor() as cursor:
            # PostgreSQL's Windows GUC path may contain system-codepage bytes
            # despite a UTF-8 database. Fetch ASCII hex and verify the real path.
            cursor.execute("SELECT encode(pg_catalog.textsend(current_setting('data_directory')), 'hex')")
            raw = bytes.fromhex(cursor.fetchone()[0])
            try:
                directory = raw.decode('utf-8')
            except UnicodeDecodeError:
                directory = raw.decode('gbk')
            if Path(directory).resolve() != (STATE / 'pgdata').resolve():
                raise RuntimeError('FULL_AUDIT_CLUSTER_IDENTITY_MISMATCH')
    return config


def bootstrap():
    import psycopg2
    STATE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if (STATE / 'postgres.json').exists():
        config = json.loads((STATE / 'postgres.json').read_text())
        if config.get('data') != str(STATE / 'pgdata') or config.get('synthetic_only') is not True:
            raise RuntimeError('FULL_AUDIT_CLUSTER_NOT_OWNED')
        status = call([str(PG_BIN / 'pg_ctl.exe'), '-D', config['data'], 'status'],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if status.returncode == 3:
            call([str(PG_BIN / 'pg_ctl.exe'), '-D', config['data'],
                  '-l', str(STATE / 'postgres.log'), '-w', '-t', '30',
                  '-o', f'-h 127.0.0.1 -p {config["port"]} -c max_connections=40', 'start'],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        elif status.returncode:
            raise RuntimeError('FULL_AUDIT_CLUSTER_STATUS_UNKNOWN')
        text = config_and_identity()
        print(json.dumps(text))
        return
    if (STATE / 'pgdata').exists():
        raise RuntimeError('REFUSE_TO_OVERWRITE_CLUSTER')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    with (EVIDENCE / 'postgres-bootstrap.log').open('w', encoding='utf-8') as output:
        result = call([str(PG_BIN / 'initdb.exe'), '-D', str(STATE / 'pgdata'),
                       '-U', 'full_audit', '--auth=trust', '--encoding=UTF8', '--locale=C'],
                      stdout=output, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError('FULL_AUDIT_INITDB_FAILED')
        result = call([str(PG_BIN / 'pg_ctl.exe'), '-D', str(STATE / 'pgdata'),
                       '-l', str(STATE / 'postgres.log'), '-w', '-t', '30',
                       '-o', f'-h 127.0.0.1 -p {port} -c max_connections=40', 'start'],
                      stdout=output, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError('FULL_AUDIT_PG_START_FAILED')
    db = psycopg2.connect(host='127.0.0.1', port=port, user='full_audit', dbname='postgres')
    db.autocommit = True
    with db.cursor() as cursor:
        cursor.execute('CREATE DATABASE full_audit')
    db.close()
    config = {'data': str(STATE / 'pgdata'), 'port': port, 'user': 'full_audit',
              'synthetic_only': True, 'host': '127.0.0.1'}
    (STATE / 'postgres.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    print(json.dumps(config_and_identity()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('--label')
    parser.add_argument('--test-db', default='test_full_audit')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--unit', action='store_true')
    parser.add_argument('--legacy', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.bootstrap:
        bootstrap()
        return
    config = config_and_identity()
    if args.stop:
        result = call([str(PG_BIN / 'pg_ctl.exe'), '-D', config['data'], '-m', 'fast', 'stop'])
        sys.exit(result.returncode)
    if not args.label or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in args.label):
        raise ValueError('FULL_AUDIT_SAFE_LABEL_REQUIRED')
    env = clean_env()
    env['FULL_AUDIT_RESULT'] = str(EVIDENCE / (args.label + '.json'))
    env['FULL_AUDIT_TEST_DB'] = args.test_db
    env['FULL_AUDIT_LEGACY'] = '1' if args.legacy else '0'
    env['MAINLINE1_TEST_PORT'] = str(config['port'])
    entry = [str(ROOT / 'tools' / 'full_audit' / 'unit_entry.py')] if args.unit else [str(ROOT / 'backend' / 'manage.py')]
    command = [sys.executable, '-B', *entry, *args.command]
    started = time.monotonic()
    with (EVIDENCE / (args.label + '.log')).open('w', encoding='utf-8') as output:
        result = subprocess.run(command, env=env, cwd=ROOT / 'backend',
                                stdout=output, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    record = {'command': command, 'exit_code': result.returncode,
              'elapsed_seconds': round(time.monotonic() - started, 2),
              'synthetic_only': True, 'test_database': args.test_db}
    (EVIDENCE / (args.label + '-command.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record))
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
