"""Build/install one ordinary wheel into a fresh isolated, Django-free venv."""
import argparse
import hashlib
from pathlib import Path

from tools.data_security import isolation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    root = isolation.ROOT
    if Path.cwd() != root or not args.label.replace('-', '').isalnum():
        parser.error('isolated worktree and a new alphanumeric label required')
    isolation.EVIDENCE = Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-05')
    directory = root / '.state' / ('package-' + args.label)
    directory.mkdir(mode=0o700)
    env = isolation.clean_env(transport=True)
    python = str(root / '.venv/bin/python')
    venv_python = str(directory / 'venv/bin/python')
    for suffix, command in (
        ('build', [python, '-I', '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', str(directory / 'dist'), str(root)]),
        ('venv', [python, '-I', '-m', 'venv', str(directory / 'venv')]),
        ('install', [venv_python, '-I', '-m', 'pip', 'install', str(directory / 'dist/ctf_data_security-0.5.0-py3-none-any.whl')]),
        ('run', [venv_python, '-I', '-B', str(root / 'tools/data_security/phase5_standalone.py')]),
    ):
        code = isolation.run(args.label + '-' + suffix, command, directory, env)
        if code:
            return code
    wheel = directory / 'dist/ctf_data_security-0.5.0-py3-none-any.whl'
    isolation.dump(isolation.EVIDENCE / (args.label + '-wheel.json'), {
        'file': str(wheel), 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
        'format': 'ordinary-wheel', 'django_installed': False, 'source_path_injection': False})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
