"""Reproducible E2 commands. Uses the previously accepted isolated PostgreSQL."""
import argparse
from pathlib import Path
import sys

from tools.data_security import isolation

EVIDENCE = Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-02')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('core', 'all', 'mainline-unit', 'mainline-postgres',
        'main-check', 'main-drift', 'mainline-check', 'mainline-drift', 'main-domain-tests',
        'export-check', 'export-drift', 'export-tests', 'frontend-build', 'dependencies', 'metrics', 'audit', 'rollback'))
    parser.add_argument('--label', required=True)
    parser.add_argument('--bound', action='store_true', help='explicit test binding for main-domain-tests only')
    args = parser.parse_args()
    if args.bound and args.action != 'main-domain-tests':
        parser.error('--bound requires main-domain-tests')
    root = isolation.ROOT
    if Path.cwd() != root or root != Path('/home/hatch/workspace/ctf-data-security'):
        parser.error('isolated worktree required')
    isolation.EVIDENCE = EVIDENCE
    python = str(root / '.venv/bin/python')
    env = isolation.clean_env()
    env['PYTHONPATH'] = str(root) + ':' + str(root / 'backend')
    entry = [python, '-B', '-m', 'tools.data_security.phase2_test_entry']
    cwd = root
    if args.action in ('all', 'core'):
        command = entry + [args.action]
    elif args.action in ('metrics', 'audit'):
        command = [python, '-B', '-m', 'tools.data_security.phase2_' + args.action]
    elif args.action == 'rollback':
        env = isolation.environment()
        env['PYTHONPATH'] = str(root) + ':' + str(root / 'backend')
        env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.test_settings'
        command = [python, '-B', '-m', 'tools.data_security.phase2_rollback']
    elif args.action == 'dependencies':
        command = [python, '-B', '-m', 'tools.data_security.dependencies']
    elif args.action == 'mainline-unit':
        command, cwd = entry + ['mainline'], root / 'backend'
    elif args.action == 'frontend-build':
        command = [str(root / '.state/node-tools/node_modules/.bin/pnpm'), 'run', 'build']
        cwd = root / 'frontend'
        env['XDG_CACHE_HOME'], env['XDG_DATA_HOME'] = str(root / '.state/cache'), str(root / '.state/share')
    else:
        isolation.start_postgres()
        env = isolation.environment()
        env['PYTHONPATH'] = str(root) + ':' + str(root / 'backend') + ':' + str(root / '.state')
        domain, operation = args.action.split('-', 1)
        env['DJANGO_SETTINGS_MODULE'] = {'main': 'tools.data_security.test_settings',
            'mainline': 'tools.data_security.mainline_test_settings',
            'export': 'tools.data_security.export_test_settings'}[domain]
        cwd = root / ('tasks/controlled-export-execution' if domain == 'export' else 'backend')
        command = (entry + ['django'] if domain == 'mainline' or args.bound else [python, '-B', 'manage.py'])
        if operation == 'check':
            command += ['check']
        elif operation == 'drift':
            command += ['makemigrations', '--check', '--dry-run']
        else:
            command += ['test', '--noinput', '-v', '2']
            if domain == 'main':
                command += list(isolation.MAIN_TEST_LABELS) + ['--testrunner=baseline_fix_test_cleanup.CleanupRunner']
            elif domain == 'mainline':
                command += ['mainline1.tests.postgres_cases', 'mainline1.tests.postgres_review_cases',
                    'mainline1.tests.postgres_planning_cases', 'mainline1.tests.postgres_operations_cases']
            else:
                command += ['controlled_export']
    return isolation.run(args.label, command, cwd, env)


if __name__ == '__main__':
    raise SystemExit(main())
