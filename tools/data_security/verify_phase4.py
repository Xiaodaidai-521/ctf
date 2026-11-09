"""Phase-four commands with immutable E4 evidence and the existing PG identity guard."""
import argparse
from pathlib import Path

from tools.data_security import isolation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = isolation.ROOT
    if Path.cwd() != root or not args.command:
        parser.error('run from isolated worktree with a manage.py command')
    isolation.EVIDENCE = Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-04')
    isolation.start_postgres()
    env = isolation.environment()
    env['PYTHONPATH'] = str(root) + ':' + str(root / 'backend') + ':' + str(root / '.state')
    env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.test_settings'
    return isolation.run(args.label, [str(root / '.venv/bin/python'), '-B', 'manage.py', *args.command],
                         root / 'backend', env)


if __name__ == '__main__':
    raise SystemExit(main())
