from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PROBE = r'''
import json, os, socket, sys, sysconfig, unittest
from pathlib import Path
root = Path(sys.argv[1]).resolve()
stdlib = Path(sysconfig.get_path('stdlib')).resolve()
site = Path(sysconfig.get_path('purelib')).resolve()
sys.path[:0] = [str(root), str(root / 'backend')]
from tools.data_security.phase2_test_entry import SafeResult
forbidden = {'django', 'rest_framework', 'psycopg2', 'sqlite3', 'openai', 'anthropic',
             'requests', 'httpx', 'dotenv', 'ai_providers'}
assert not forbidden.intersection(sys.modules)
assert not any(name.startswith('data_security') for name in sys.modules)
class NoEnvironment(dict):
    def __getitem__(self, key): raise RuntimeError('ENVIRONMENT_UNAVAILABLE')
    def get(self, *args): raise RuntimeError('ENVIRONMENT_UNAVAILABLE')
    def __iter__(self): raise RuntimeError('ENVIRONMENT_UNAVAILABLE')
    def __len__(self): raise RuntimeError('ENVIRONMENT_UNAVAILABLE')
    def __contains__(self, key): raise RuntimeError('ENVIRONMENT_UNAVAILABLE')
os.environ = NoEnvironment()
def guard(event, args):
    if event == 'import' and args[0].split('.')[0] in forbidden:
        raise RuntimeError('IMPORT_UNAVAILABLE')
    if event.startswith(('socket.', 'sqlite3.', 'subprocess.')) or event in (
        'os.system', 'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.chdir', 'os.putenv', 'os.unsetenv'):
        raise RuntimeError('SIDE_EFFECT_UNAVAILABLE')
    if event == 'open':
        filename, mode, flags = args
        if not isinstance(filename, (str, bytes)):
            raise RuntimeError('FILE_UNAVAILABLE')
        path = Path(os.fsdecode(filename)).resolve()
        source = path.is_relative_to(root / 'backend/data_security') or path.is_relative_to(root / 'tools/data_security')
        library = path.is_relative_to(stdlib) or path.is_relative_to(site)
        if not (source or library) or path.suffix not in ('.py', '.pyc', '.so') or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
            raise RuntimeError('FILE_UNAVAILABLE')
sys.addaudithook(guard)
for probe in (lambda: os.getenv('UNAVAILABLE'), lambda: open('media/unavailable'),
              lambda: socket.socket(), lambda: __import__('django'), lambda: __import__('sqlite3')):
    try: probe()
    except RuntimeError: pass
    else: raise AssertionError('GUARD_NOT_ACTIVE')
suite = unittest.defaultTestLoader.loadTestsFromName('data_security.tests.test_phase2_core')
result = unittest.TextTestRunner(verbosity=2, buffer=True, resultclass=SafeResult).run(suite)
assert not forbidden.intersection(sys.modules)
print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
    'environment_read': False, 'network': False, 'database': False, 'media': False, 'writes': False}))
sys.exit(not result.wasSuccessful())
'''


class OfflineCoreTests(unittest.TestCase):
    def test_fresh_import_and_entire_core_suite_without_io_environment_or_django(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.state', prefix='phase2-offline-') as directory:
            result = subprocess.run([sys.executable, '-I', '-B', '-c', PROBE, str(ROOT)], cwd=directory,
                                    env={}, capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"failures": 0', result.stdout)
            self.assertIn('"errors": 0', result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])
