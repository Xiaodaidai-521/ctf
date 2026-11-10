"""Incremental phase-seven tests with immutable evidence and isolated entry points."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

from tools.data_security import isolation

ROOT = Path('/home/hatch/workspace/ctf-data-security')
EVIDENCE = Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-07')


def snapshot():
    names = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in sorted(set(names))
            if ((name.startswith(('backend/', 'tools/data_security/')) and name.endswith('.py'))
                or name == 'tools/data_security/phase-boundary.json') and (ROOT / name).is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('entry', choices=('pg', 'pure'))
    parser.add_argument('label')
    parser.add_argument('tests', nargs='+')
    args = parser.parse_args()
    if Path.cwd() != ROOT or isolation.ROOT != ROOT:
        parser.error('run only from the isolated phase-seven worktree')
    if not args.label or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in args.label):
        parser.error('invalid evidence label')
    for suffix in ('.log', '.json', '-sources.json', '-sources-after.json'):
        if (EVIDENCE / (args.label + suffix)).exists():
            parser.error('evidence exists; use a new label')
    if args.entry == 'pg':
        import psycopg2
        config = isolation.identity()
        with psycopg2.connect(host=config['socket'], port=config['port'], user='ds_phase1', dbname='postgres') as db:
            with db.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname='test_ds_phase1_main' AND backend_type='client backend'")
                if cursor.fetchone()[0]:
                    parser.error('isolated test database is in use')
        env = isolation.environment()
        env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.test_settings'
        command = [str(ROOT / '.venv/bin/python'), '-B', 'manage.py', 'test', *args.tests, '--noinput', '-v', '2']
        cwd = ROOT / 'backend'
    else:
        env = isolation.clean_env()
        env.update(PYTHONPATH=str(ROOT) + ':' + str(ROOT / 'backend'), DATA_SECURITY_ISOLATED_TEST='1')
        program = ('from tools.data_security.network_guard import install; install(); '
                   'import sys, unittest; '
                   'unittest.main(module=None, argv=["unittest", "-v", *sys.argv[1:]])')
        command = [str(ROOT / '.venv/bin/python'), '-B', '-c', program, *args.tests]
        cwd = ROOT
    before = snapshot()
    isolation.dump(EVIDENCE / (args.label + '-sources.json'), {'files': before})
    isolation.EVIDENCE = EVIDENCE
    code = isolation.run(args.label, command, cwd, env)
    after = snapshot()
    changes = [name for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]
    isolation.dump(EVIDENCE / (args.label + '-sources-after.json'), {'source_changes': changes, 'exit_code': code})
    return code


if __name__ == '__main__':
    sys.exit(main())
