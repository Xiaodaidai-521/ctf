"""Receipt-only checks; no backup, database, key tools or external calls."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.data_security import phase3_backup_verify


class BackupReceiptTests(unittest.TestCase):
    def test_log_hash_binds_exact_output_and_preserves_exit_code(self):
        payload = b'synthetic backup runner output\n'
        for exit_code in (0, 1):
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory(
                    prefix='ds-receipt-test-', dir='/tmp') as temporary:
                root = Path(temporary)
                evidence = root / 'evidence'
                stdout = SimpleNamespace(buffer=io.BytesIO())
                argv = ['phase3_backup_verify', '--tools', str(root / 'tools'),
                        '--controlled-parent', str(root / 'controlled'),
                        '--evidence', str(evidence)]
                with patch('sys.argv', argv), patch('sys.stdout', stdout), \
                        patch.object(phase3_backup_verify.subprocess, 'run', return_value=
                                     subprocess.CompletedProcess([], exit_code, payload)) as run, \
                        patch.object(phase3_backup_verify.subprocess, 'check_output',
                                     return_value='synthetic-test-version\n'):
                    self.assertEqual(phase3_backup_verify.main(), exit_code)
                run.assert_called_once()
                receipts = list(evidence.glob('*.json'))
                self.assertEqual(len(receipts), 1)
                receipt = json.loads(receipts[0].read_text())
                log = evidence / receipt['log']
                self.assertEqual(log.read_bytes(), payload)
                self.assertEqual(receipt['log_sha256'], hashlib.sha256(payload).hexdigest())
                self.assertEqual(receipt['returncode'], exit_code)
                self.assertEqual(stdout.buffer.getvalue(), payload)
                self.assertEqual(log.stat().st_mode & 0o777, 0o600)
                self.assertEqual(receipts[0].stat().st_mode & 0o777, 0o600)
