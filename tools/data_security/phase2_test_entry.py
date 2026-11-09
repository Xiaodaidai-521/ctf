"""Explicit isolated-test composition. Never loaded by application startup."""
import argparse
import json
import runpy
import sys
import traceback
import unittest


class SafeResult(unittest.TextTestResult):
    def getDescription(self, test):
        return test.id()

    def _exc_info_to_string(self, err, test):
        return json.dumps({'exception_type': err[0].__name__, 'frames': [
            {'file': f.filename, 'line': f.lineno, 'function': f.name}
            for f in traceback.extract_tb(err[2])], 'message': 'omitted: synthetic evidence'})

    def stopTest(self, test):
        self._mirrorOutput = False
        super().stopTest(test)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('core', 'all', 'mainline', 'django'))
    args, remaining = parser.parse_known_args()
    if args.mode in ('mainline', 'django'):
        from ctf_backend.security_bootstrap import bind_legacy_for_tests
        from data_security.contracts import Environment
        bind_legacy_for_tests(environment=Environment.TEST)
    if args.mode == 'django':
        sys.argv = ['django', *remaining]
        runpy.run_module('django', run_name='__main__')
        return 0
    if args.mode == 'core':
        suite = unittest.defaultTestLoader.loadTestsFromName('data_security.tests.test_phase2_core')
    else:
        suite = unittest.defaultTestLoader.discover('mainline1/tests' if args.mode == 'mainline'
            else 'backend/data_security/tests', top_level_dir=None if args.mode == 'mainline' else 'backend')
    result = unittest.TextTestRunner(verbosity=2, buffer=True, resultclass=SafeResult).run(suite)
    return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
