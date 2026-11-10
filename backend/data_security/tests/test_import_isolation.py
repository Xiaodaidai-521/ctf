from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
PROBE = r'''
import json
import os
import socket
import sys
import sysconfig

backend = os.path.realpath(sys.argv[1])
contract_root = os.path.join(backend, 'data_security')
stdlib = os.path.realpath(sysconfig.get_path('stdlib'))
forbidden = {'django', 'rest_framework', 'psycopg2', 'sqlite3', 'openai', 'anthropic',
             'requests', 'httpx', 'cryptography', 'dotenv', 'ai_providers'}
assert not forbidden.intersection(sys.modules)

class NoEnvironment(dict):
    def __getitem__(self, key):
        raise RuntimeError('ENVIRONMENT_UNAVAILABLE')
    def get(self, *args):
        raise RuntimeError('ENVIRONMENT_UNAVAILABLE')
    def __iter__(self):
        raise RuntimeError('ENVIRONMENT_UNAVAILABLE')
    def __len__(self):
        raise RuntimeError('ENVIRONMENT_UNAVAILABLE')
    def __contains__(self, key):
        raise RuntimeError('ENVIRONMENT_UNAVAILABLE')

os.environ = NoEnvironment()

def guard(event, args):
    if event == 'import' and args[0].split('.')[0] in forbidden:
        raise RuntimeError('IMPORT_UNAVAILABLE')
    if event.startswith(('socket.', 'sqlite3.', 'subprocess.')) or event in (
        'os.system', 'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.chdir', 'os.putenv', 'os.unsetenv'
    ):
        raise RuntimeError('SIDE_EFFECT_UNAVAILABLE')
    if event == 'open':
        filename, mode, flags = args
        if not isinstance(filename, (str, bytes)):
            raise RuntimeError('FILE_UNAVAILABLE')
        filename = os.path.realpath(os.fsdecode(filename))
        source = filename.startswith(contract_root + os.sep)
        standard = filename.startswith(stdlib + os.sep) and '/site-packages/' not in filename
        if not (source or standard) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
            raise RuntimeError('FILE_UNAVAILABLE')

sys.addaudithook(guard)
for probe in (lambda: os.getenv('UNAVAILABLE'), lambda: open('unavailable-media'),
              lambda: socket.socket(), lambda: __import__('django'), lambda: __import__('sqlite3')):
    try:
        probe()
    except RuntimeError:
        pass
    else:
        raise AssertionError('GUARD_NOT_ACTIVE')
sys.path.insert(0, backend)
import data_security.contracts as contracts
assert len(contracts.CONTRACT_TYPES) == 49
assert contracts.RevealRequestRecord in contracts.CONTRACT_TYPES
assert contracts.RevealRequestRecord.SCHEMA == 'ds.reveal-request-record.v1'
assert contracts.RevealRequestRecord.SERVER_ONLY and contracts.RevealRequestRecord.SENSITIVE
assert contracts.RevealSource in contracts.CONTRACT_TYPES
assert contracts.RevealSource.SCHEMA == 'ds.reveal-source.v1'
assert contracts.RevealSource.SERVER_ONLY and contracts.RevealSource.SENSITIVE
assert contracts.BackupRetentionRecord in contracts.CONTRACT_TYPES
assert contracts.BackupRetentionRecord.SCHEMA == 'ds.backup-retention-record.v1'
assert contracts.BackupRetentionRecord.SERVER_ONLY
assert contracts.CanarySeed in contracts.CONTRACT_TYPES
assert contracts.CanarySeed.SCHEMA == 'ds.canary-seed.v1'
assert contracts.QuotaRecoveryEvent in contracts.CONTRACT_TYPES
assert contracts.QuotaRecoveryEvent.SCHEMA == 'ds.quota-recovery-event.v1'
assert contracts.AuditCheckpoint in contracts.CONTRACT_TYPES
assert contracts.AuditCheckpoint.SCHEMA == 'ds.audit-checkpoint.v1'
assert contracts.SecurityEventV2 in contracts.CONTRACT_TYPES
assert contracts.SecurityEventV2.SCHEMA == 'ds.security-event.v2'
assert contracts.ReportRecord in contracts.CONTRACT_TYPES
assert contracts.ReportRecord.SCHEMA == 'ds.report-record.v1'
assert contracts.ReportRepository in contracts.PORT_TYPES
assert contracts.ReportProof in contracts.CONTRACT_TYPES
assert contracts.ReportProof.SCHEMA == 'ds.report-proof.v1'
assert len(contracts.PORT_TYPES) == 23
assert contracts.RevealRequestRepository in contracts.PORT_TYPES
assert contracts.CanaryCheckPort in contracts.PORT_TYPES
assert contracts.RevealSourcePort in contracts.PORT_TYPES
limits = contracts.BASELINE_LIMITS
assert type(limits).from_wire(limits.to_wire()) == limits
assert not forbidden.intersection(sys.modules)
print(json.dumps({'imported_contracts': len(contracts.CONTRACT_TYPES),
                  'ports': len(contracts.PORT_TYPES), 'environment_available': False,
                  'network_available': False, 'database_available': False,
                  'application_media_available': False, 'writes_available': False}))
'''


class ImportIsolationTests(unittest.TestCase):
    def test_m0_imports_and_validates_without_site_packages_env_network_database_or_media(self):
        with tempfile.TemporaryDirectory(prefix='import-fixture-') as directory:
            result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', PROBE, str(ROOT / 'backend')],
                                    cwd=directory, env={}, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"imported_contracts": 49', result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])
