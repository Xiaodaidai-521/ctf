"""Actual Vue/browser -> final Django URLs -> a separate synthetic PostgreSQL DB.

Random keys and login credentials live only in private external temporary directories.
No test database, production service, provider API, or persistent browser profile is used.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from tools.data_security import isolation

ROOT = isolation.ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--browser', required=True, type=Path)
    parser.add_argument('--playwright', required=True, type=Path)
    args = parser.parse_args()
    if Path.cwd() != ROOT or not args.label.replace('-', '').isalnum():
        parser.error('isolated worktree and a simple evidence label required')
    evidence = Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-04')
    output = evidence / (args.label + '.json')
    if output.exists():
        raise RuntimeError('EVIDENCE_ALREADY_EXISTS')
    os.umask(0o077)
    cluster = isolation.identity()
    database = 'phase4_browser_' + uuid4().hex[:12]
    pg = dict(host=cluster['socket'], port=cluster['port'], user=cluster['user'], dbname='postgres')
    ports = []
    for _ in range(2):
        with socket.socket() as candidate:
            candidate.bind(('127.0.0.1', 0))
            ports.append(candidate.getsockname()[1])
    backend_port, frontend_port = ports
    assert backend_port != frontend_port
    record = {'label': args.label, 'started_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'actual browser; final Django settings and URLs; independent synthetic PostgreSQL database',
        'database': database, 'providers_configured': 0, 'production_connections': False,
        'transport': 'loopback HTTP only; not TLS acceptance', 'checks': {}, 'exit_code': 1,
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()}
    process = None
    created = False
    try:
        with closing(psycopg2.connect(**pg)) as control:
            control.autocommit = True
            with control.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
                created = True
        sys.path.insert(0, str(ROOT / 'backend'))
        from data_security.tests.phase4_fixtures import field_configuration
        with tempfile.TemporaryDirectory(prefix='ds-phase4-browser-', dir='/tmp') as private, field_configuration() as fixture:
            private = Path(private)
            config_path, config, refs, binding = fixture
            env = isolation.environment()
            env.update(DB_NAME=database, DEBUG='false', ALLOWED_HOSTS='127.0.0.1,localhost',
                DATA_SECURITY_CONFIG=str(config_path), DJANGO_SETTINGS_MODULE='ctf_backend.settings',
                DB_TRANSPORT='local', DB_SSLMODE='disable', SECURE_SSL_REDIRECT='false',
                SESSION_COOKIE_SECURE='false', CSRF_COOKIE_SECURE='false',
                ALLOWED_ORIGINS=f'http://127.0.0.1:{frontend_port}',
                PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT / 'backend'))))
            os.environ.update(env)
            import django
            django.setup()
            from django.core.management import call_command
            from django.db import connection, connections
            from users.models import CTFUser
            with (private / 'migration.log').open('w') as stream:
                call_command('migrate', interactive=False, verbosity=1, stdout=stream, stderr=stream)
            credentials = {}
            for role in ('admin', 'teacher', 'student'):
                password = secrets.token_urlsafe(32)
                user = CTFUser.objects.create_user(username='browser-' + role, password=password,
                    role=role, is_staff=role == 'admin', nickname='Synthetic ' + role,
                    email='Browser' + role + '@example.invalid')
                credentials[role] = {'username': user.username, 'password': password}
            (private / 'credentials.json').write_text(json.dumps(credentials))
            connections.close_all()
            command = [sys.executable, '-B', '-c',
                'from tools.data_security.network_guard import install; install(); '
                'from gunicorn.app.wsgiapp import run; run()',
                '--bind', f'127.0.0.1:{backend_port}', '--workers', '1', '--access-logfile', '/dev/null',
                '--error-logfile', str(private / 'server.log'), 'ctf_backend.wsgi:application']
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            command = ['node', str(ROOT / 'tools/data_security/phase4_browser_driver.mjs'),
                str(private), str(backend_port), str(frontend_port), str(args.browser), str(args.playwright),
                str(evidence), args.label]
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=180)
            # Only deliberate metadata output is copied; browser stderr stays private on failure.
            (private / 'browser.stderr').write_bytes(result.stderr)
            if result.returncode:
                record['failure'] = 'BROWSER_DRIVER_FAILED'
                record['driver_exit_code'] = result.returncode
                if result.stdout:
                    record['driver_observations'] = json.loads(result.stdout)
                print(result.stdout.decode(errors='replace'))
                raise RuntimeError('BROWSER_DRIVER_FAILED')
            observation = json.loads(result.stdout)
            record.update(observation)
            from audit.models import AuditEvent, SecurityAuditRecord
            marker = 'RejectedBody@example.invalid'
            with connection.cursor() as cursor:
                for model in (AuditEvent, SecurityAuditRecord):
                    cursor.execute(sql.SQL('SELECT row_to_json(item)::text FROM {} AS item').format(
                        sql.Identifier(model._meta.db_table)))
                    rows = '\n'.join(row[0] for row in cursor.fetchall())
                    assert marker not in rows
                    assert all(value not in rows for value in (
                        'Student@Example.invalid', '192.0.2.42', '4111111111111111'))
            record['checks']['preview_originals_absent_from_audit_tables'] = True
            server_log = (private / 'server.log').read_text()
            assert marker not in server_log
            assert all(value['password'] not in server_log for value in credentials.values())
            record['checks']['server_log_has_no_request_body_or_credentials'] = True
            record['exit_code'] = 0
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=15)
        if created:
            from django.db import connections
            connections.close_all()
            with closing(psycopg2.connect(**pg)) as control:
                control.autocommit = True
                with control.cursor() as cursor:
                    assert database.startswith('phase4_browser_')
                    cursor.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
            record['synthetic_database_removed'] = True
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        record['source_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), ROOT / 'tools/data_security/phase4_browser_driver.mjs',
                         ROOT / 'frontend/src/admin/views/DataSecurity.vue')}
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(record, ensure_ascii=False))
    return record['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
