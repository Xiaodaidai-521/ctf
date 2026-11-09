"""Bounded-output unit entry; no application prebinding and no live provider calls."""
import sys
import unittest
import json
import os
from pathlib import Path

from tools.data_security.network_guard import install
from tools.data_security.phase2_test_entry import SafeResult


def main():
    install()
    suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
    result = unittest.TextTestRunner(verbosity=2, buffer=True, resultclass=SafeResult).run(suite)
    if os.environ.get('DS_CAPTURE_FILE'):
        from data_security.tests.test_phase3_official import CAPTURE_SUMMARIES
        path = Path(os.environ['DS_CAPTURE_FILE'])
        path.write_text(json.dumps({'real_provider_calls': False, 'passed': result.wasSuccessful(),
                                   'captures': CAPTURE_SUMMARIES}, ensure_ascii=False, indent=2) + '\n')
        path.chmod(0o600)
    return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
