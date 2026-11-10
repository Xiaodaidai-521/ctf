"""Phase-five immutable evidence, with the retained isolated PostgreSQL guard."""
import argparse
from pathlib import Path
import subprocess

from tools.data_security import isolation


def main(*, phase=5):
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--expect-head')
    parser.add_argument('--domain', choices=('main', 'mainline', 'export'), default='main')
    parser.add_argument('suite', choices=('default', 'bound', 'pure', 'mainline', 'mainline-pg',
                                         'export', 'unit', 'django', 'python', 'frontend', 'backfill'))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = isolation.ROOT
    if Path.cwd() != root:
        parser.error('run only from the isolated worktree')
    def check_candidate():
        if args.expect_head:
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
            dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip()
            if head != args.expect_head or dirty:
                raise RuntimeError('EXACT_CLEAN_CANDIDATE_REQUIRED')

    check_candidate()
    isolation.EVIDENCE = Path('/home/hatch/workspace/data-security-seven-phases/evidence') / f'phase-{phase:02d}'
    isolation.start_postgres()
    env = isolation.environment()
    env['PYTHONPATH'] = str(root) + ':' + str(root / 'backend') + ':' + str(root / '.state')
    env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.test_settings'
    python = str(root / '.venv/bin/python')
    cwd = root
    command = [python, '-B']
    if args.suite in ('default', 'bound', 'django'):
        cwd = root / 'backend'
        command += (['-m', 'tools.data_security.phase2_test_entry', 'django'] if args.suite == 'bound'
                    else ['manage.py'])
        command += args.arguments if args.suite == 'django' else [
            'test', '--noinput', '-v', '2', *isolation.MAIN_TEST_LABELS,
            '--testrunner=baseline_fix_test_cleanup.CleanupRunner']
    elif args.suite == 'pure':
        command += ['-m', 'tools.data_security.phase2_test_entry', 'all']
    elif args.suite == 'mainline':
        cwd = root / 'backend'
        command += ['-m', 'tools.data_security.phase2_test_entry', 'mainline']
    elif args.suite == 'mainline-pg':
        cwd = root / 'backend'
        env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.mainline_test_settings'
        command += ['-m', 'tools.data_security.phase2_test_entry', 'django', 'test', 'mainline1.tests.postgres_cases',
            'mainline1.tests.postgres_review_cases', 'mainline1.tests.postgres_planning_cases',
            'mainline1.tests.postgres_operations_cases', 'mainline1.tests.postgres_parsed_artifact_cases',
            '--noinput', '-v', '2']
    elif args.suite == 'export':
        cwd = root / 'tasks/controlled-export-execution'
        env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.export_test_settings'
        command += ['manage.py', 'test', 'controlled_export', '--noinput', '-v', '2']
    elif args.suite == 'backfill':
        records = isolation.EVIDENCE.parents[1]
        env.update(DJANGO_SETTINGS_MODULE='ctf_backend.settings', DATA_SECURITY_CONFIG='', DATABASE_URL='',
            DS_PHASE4_BACKFILL_RUN='1', DS_PHASE4_AGE_TOOLS=str(records / 'isolated-tools/phase3-age-extracted'),
            DS_PHASE4_CONTROLLED_PARENT=str(records / 'isolated-material'),
            DS_PHASE4_BACKFILL_OBSERVATIONS=str(isolation.EVIDENCE / (args.label + '-observations.json')))
        command += ['-m', 'unittest', *args.arguments, '-v']
    elif args.suite == 'unit':
        command += ['-m', 'tools.data_security.phase3_unit_entry', *args.arguments]
    elif args.suite == 'frontend':
        cwd = root / 'frontend'
        command = [str(isolation.STATE / 'node-tools/node_modules/.bin/pnpm'), 'run', 'build']
    else:
        command += args.arguments
    if args.suite == 'django' and args.domain != 'main':
        env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.' + args.domain + '_test_settings'
        if args.domain == 'export':
            cwd = root / 'tasks/controlled-export-execution'
    result = isolation.run(args.label, command, cwd, env)
    check_candidate()
    if args.expect_head:
        isolation.dump(isolation.EVIDENCE / (args.label + '-candidate.json'), {
            'head': args.expect_head, 'clean_before_and_after': True, 'result': result})
    return result


if __name__ == '__main__':
    raise SystemExit(main())
