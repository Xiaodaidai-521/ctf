"""Create/stop/remove ONLY a fresh synthetic PostgreSQL cluster; never load .env.

Run from backend: python -B mainline1/tests/run_isolated_postgres.py
Requires already-installed PostgreSQL 16 binaries and psycopg2. No downloads.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time


def main(*, test_modules=('mainline1.tests.postgres_cases',),
         evidence_filename='step-03-postgres-verification.json'):
    if evidence_filename not in ('step-03-postgres-verification.json', 'step-06-postgres-verification.json',
                                 'step-07-postgres-verification.json', 'step-08-postgres-verification.json'):
        raise ValueError('UNSUPPORTED_EVIDENCE_DESTINATION')
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    binaries = Path(os.environ.get('MAINLINE1_PG_BIN', r'C:\Program Files\PostgreSQL\16\bin'))
    if not all((binaries / name).is_file() for name in ('initdb.exe', 'pg_ctl.exe')):
        raise SystemExit('BLOCKED: preinstalled PostgreSQL binaries unavailable')
    parent = Path(tempfile.gettempdir()).resolve()
    root = Path(tempfile.mkdtemp(prefix='mainline1-synthetic-pg-', dir=parent)).resolve()
    data = root / 'data'
    log = root / 'postgres.log'
    started, stopped = False, False
    evidence = dict(kind='isolated_postgresql', synthetic_only=True, production_settings_loaded=False,
                    started=False, stopped=False, checks=[])
    env = os.environ.copy()
    # Do not inherit connection options/service/password files from the host.
    env = {k: v for k, v in env.items() if not k.upper().startswith('PG')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PGPASSFILE'] = str(root / 'no-password-file')
    env['PGSERVICEFILE'] = str(root / 'no-service-file')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    def run(args, timeout=60):
        # Windows postgres can inherit pg_ctl's pipe and keep communicate() open.
        # A regular file does not depend on all descendant handles closing.
        output_path = root / 'command-output.txt'
        with output_path.open('w', encoding='utf-8') as output:
            result = subprocess.run(args, cwd=Path(__file__).resolve().parents[2], env=env,
                                    stdout=output, stderr=subprocess.STDOUT, timeout=timeout,
                                    creationflags=flags, stdin=subprocess.DEVNULL)
        result.stdout = output_path.read_text(encoding='utf-8', errors='replace')
        return result
    try:
        version = run([str(binaries / 'pg_ctl.exe'), '--version'])
        evidence['server_version'] = version.stdout.strip()
        result = run([str(binaries / 'initdb.exe'), '-D', str(data), '-U', 'mainline1_test',
                      '--auth-local=trust', '--auth-host=trust', '--encoding=UTF8', '--locale=C'])
        if result.returncode:
            raise RuntimeError('ISOLATED_INITDB_FAILED')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        env['MAINLINE1_TEST_PORT'] = str(port)
        result = run([str(binaries / 'pg_ctl.exe'), '-D', str(data), '-l', str(log), '-w', '-t', '15',
                      '-o', f'-h 127.0.0.1 -p {port} -c max_connections=20', 'start'])
        if result.returncode:
            raise RuntimeError('ISOLATED_START_FAILED')
        started = evidence['started'] = True
        # Ensure the port belongs to OUR new cluster before any migration or test.
        import psycopg2
        with psycopg2.connect(host='127.0.0.1', port=port, user='mainline1_test', dbname='postgres') as db:
            with db.cursor() as cursor:
                cursor.execute('SHOW data_directory')
                if Path(cursor.fetchone()[0]).resolve() != data.resolve():
                    raise RuntimeError('CLUSTER_IDENTITY_MISMATCH')
        common = ['--settings=mainline1.test_settings']
        commands = [
            [sys.executable, '-B', '-m', 'django', 'check', *common],
            [sys.executable, '-B', '-m', 'django', 'makemigrations', '--check', '--dry-run', *common],
            [sys.executable, '-B', '-m', 'django', 'test', *test_modules, '--noinput', '-v', '2', *common],
            [sys.executable, '-B', '-m', 'django', 'migrate', 'mainline1', '--noinput', *common],
            [sys.executable, '-B', '-m', 'django', 'migrate', 'mainline1', 'zero', '--noinput', *common],
        ]
        for command in commands:
            result = run(command, timeout=60)
            evidence['checks'].append(dict(command=command[1:], exit_code=result.returncode,
                                           status='Passed' if result.returncode == 0 else 'Failed', output=result.stdout))
            print(result.stdout, flush=True)
            if result.returncode:
                break
    finally:
        # pg_ctl targets the directory we created, never a configured business server.
        if (data / 'postmaster.pid').exists():
            result = run([str(binaries / 'pg_ctl.exe'), '-D', str(data), '-w', '-t', '15', '-m', 'fast', 'stop'])
            stopped = result.returncode == 0
        else:
            stopped = True
        evidence['stopped'] = stopped
        if root.parent == parent and root.name.startswith('mainline1-synthetic-pg-') and stopped:
            shutil.rmtree(root)
            evidence['temporary_cluster_removed'] = True
        else:
            evidence['temporary_cluster_removed'] = False
        destination = Path(__file__).resolve().parents[3] / 'docs/mainline1' / evidence_filename
        destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if started and stopped and len(evidence['checks']) == 5 and all(
        check['exit_code'] == 0 for check in evidence['checks']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
