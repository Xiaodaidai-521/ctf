"""Local acceptance harness only; requires the namespaces exercised in r2 logs."""
import os
import subprocess
import sys
from pathlib import Path


def run(*args):
    subprocess.run(args, check=True)


root = Path(sys.argv[1]).resolve()
port = sys.argv[2]
run('mount', '--make-rprivate', '/')
run('ip', 'link', 'set', 'lo', 'up')
(root / 'usr').mkdir(exist_ok=True)
run('mount', '--bind', '/usr', str(root / 'usr'))
run('mount', '-o', 'remount,bind,ro', str(root / 'usr'))
for name in ('bin', 'sbin', 'lib', 'lib64'):
    (root / name).symlink_to('usr/' + name)
for name in ('dev', 'proc', 'tmp'):
    (root / name).mkdir(exist_ok=True)
for name in ('null', 'zero', 'random', 'urandom'):
    target = root / 'dev' / name
    target.touch()
    run('mount', '--bind', '/dev/' + name, str(target))
# The host rejects a fresh proc mount. Do not expose its existing proc tree.
(root / 'state' / 'namespaces.json').write_text(__import__('json').dumps({
    name: os.readlink('/proc/self/ns/' + name) for name in ('net', 'pid', 'mnt', 'user')
}))
run('mount', '-t', 'tmpfs', '-o', 'size=32m,nosuid,nodev', 'tmpfs', str(root / 'tmp'))
os.chroot(root)
os.chdir('/app')
os.execv('/usr/bin/setpriv', [
    'setpriv', '--bounding-set=-all', '--inh-caps=-all', '--ambient-caps=-all',
    '--no-new-privs', '/usr/bin/python3', '-I', '/r2/worker.py', port,
])
