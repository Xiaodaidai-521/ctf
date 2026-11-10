"""Minute-scale B2 checks. This runner never starts or connects to a database."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    'data_security.tests.test_contracts',
    'data_security.tests.test_import_isolation',
    'data_security.tests.test_phase6_private_files',
    'data_security.tests.test_phase6_uploads',
    'data_security.tests.test_phase6_private_ingress',
    'data_security.tests.test_phase6_b2_ingress',
    'data_security.tests.test_phase6_b2_boundaries',
    'tools.data_security.test_phase6_plaintext_scan',
)
EXECUTOR_MODULES = (
    'controlled_export.tests.test_transformations',
    'controlled_export.tests.test_phase6_b2_boundaries',
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--executor', action='store_true')
    parser.add_argument('--collect-only', action='store_true', help='Load test IDs without executing tests')
    parser.add_argument('modules', nargs='*')
    args = parser.parse_args()
    # A fresh process uses only a synthetic unbound settings profile, then a dummy backend.
    for name in ('DATA_SECURITY_CONFIG', 'DATABASE_URL', 'CONTROLLED_EXPORT_PRIVATE_CONFIG',
                 'CONTROLLED_EXPORT_DATABASE_URL', 'CONTROLLED_EXPORT_PRIVATE_MODE'):
        os.environ.pop(name, None)
    os.environ['SECRET_KEY'] = 'b2-synthetic-system-check-' + 'x' * 64
    os.environ['CONTROLLED_EXPORT_ENVIRONMENT'] = 'evaluation'
    os.environ['DJANGO_SETTINGS_MODULE'] = ('controlled_export_service.settings' if args.executor else 'ctf_backend.settings')
    sys.path.insert(0, str(ROOT / 'backend'))
    sys.path.insert(0, str(ROOT))
    if args.executor:
        sys.path.insert(0, str(ROOT / 'tasks/controlled-export-execution'))
    import django
    from django.conf import settings
    from django.core.management import call_command
    from tools.data_security.dependencies import scan

    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.dummy'}}
    output, stages = StringIO(), {}
    with patch('django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection',
               side_effect=AssertionError('B2 small checks must not connect to a database')) as connect, \
         redirect_stdout(output), redirect_stderr(output):
        django.setup()
        for name, options in (('check', {}), ('makemigrations', {'check': True, 'dry_run': True, 'interactive': False})):
            print('\n=== ' + name + ' ===')
            try:
                call_command(name, **options)
            except (Exception, SystemExit) as error:
                stages[name] = False
                print(type(error).__name__ + ': ' + str(error))
            else:
                stages[name] = True
        print('\n=== test collection only ===' if args.collect_only else '\n=== selected database-free tests ===')
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromNames(args.modules or (EXECUTOR_MODULES if args.executor else MODULES))
        collected = suite.countTestCases()
        if args.collect_only:
            result = unittest.TestResult()
            pending = [suite]
            while pending:
                item = pending.pop()
                if isinstance(item, unittest.TestSuite):
                    pending.extend(item)
                else:
                    print(item.id())
            for error in loader.errors:
                print(error)
            stages['collection'] = not loader.errors
        else:
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
            stages['pure'] = result.wasSuccessful()
        checked, findings = scan(ROOT, phase=6)
        print(json.dumps({'checked_python_files': checked, 'violations': [
            {'file': item.file, 'line': item.line, 'code': item.code} for item in findings]}))
        stages['dependencies'] = not findings
        stages['database_calls'] = connect.call_count == 0
    summary = {'profile': 'executor' if args.executor else 'backend', 'stages': stages, 'tests': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
        'collected_tests': collected, 'collection_only': args.collect_only,
        'database_connections_attempted': connect.call_count, 'postgres_started': False}
    with args.log.open('x', encoding='utf-8') as evidence:
        os.fchmod(evidence.fileno(), 0o600)
        evidence.write(output.getvalue())
        evidence.write('\n' + json.dumps(summary, ensure_ascii=False) + '\n')
    print(json.dumps(summary, ensure_ascii=False))
    return int(not all(stages.values()))


if __name__ == '__main__':
    raise SystemExit(main())
