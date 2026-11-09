"""E3 evidence runner, retaining the unbound/bound legacy command distinction."""
import argparse
from pathlib import Path
import sys

from tools.data_security import isolation, verify_phase2

EVIDENCE = Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-03')


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('unit', 'integration', 'metrics', 'audit', 'rollback'):
        parser = argparse.ArgumentParser()
        parser.add_argument('action', choices=('unit', 'integration', 'metrics', 'audit', 'rollback'))
        parser.add_argument('--label', required=True)
        args = parser.parse_args()
        root = isolation.ROOT
        if Path.cwd() != root:
            parser.error('isolated worktree required')
        isolation.EVIDENCE = EVIDENCE
        env = isolation.environment()
        env['PYTHONPATH'] = str(root) + ':' + str(root / 'backend') + ':' + str(root / '.state')
        if args.action in ('metrics', 'audit', 'rollback'):
            command = [str(root / '.venv/bin/python'), '-B', '-m', 'tools.data_security.phase3_' + args.action]
            env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.test_settings'
            cwd = root
        elif args.action == 'unit':
            env['DS_CAPTURE_FILE'] = str(EVIDENCE / (args.label + '-captures.json'))
            command = [str(root / '.venv/bin/python'), '-B', '-m', 'tools.data_security.phase3_unit_entry',
                'data_security.tests.test_phase3_official', 'data_security.tests.test_phase3_audit_gateway',
                'data_security.tests.test_phase3_auth_crypto', 'data_security.tests.test_phase3_dependencies']
            cwd = root
        else:
            isolation.start_postgres()
            capture_directory = EVIDENCE / (args.label + '-captures')
            capture_directory.mkdir(mode=0o700)
            env['DS_CAPTURE_DIRECTORY'] = str(capture_directory)
            env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.test_settings'
            command = [str(root / '.venv/bin/python'), '-B', 'manage.py', 'test',
                'audit.test_phase3_audit_persistence', 'audit.test_phase3_bootstrap',
                'users.test_phase3_auth', 'ai_assistant.test_phase3_content',
                '--noinput', '-v', '2', '--testrunner=baseline_fix_test_cleanup.CleanupRunner']
            cwd = root / 'backend'
        return isolation.run(args.label, command, cwd, env)
    verify_phase2.EVIDENCE = EVIDENCE
    return verify_phase2.main()


if __name__ == '__main__':
    raise SystemExit(main())
