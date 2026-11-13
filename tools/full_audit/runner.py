"""Capture exact test identities and outcomes without changing assertions."""
import json
import os
import unittest
from pathlib import Path

from django.test.runner import DiscoverRunner


class AuditResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = []

    def addSuccess(self, test):
        self.passed.append(test.id())
        super().addSuccess(test)


def write_result(result):
    output = os.environ.get('FULL_AUDIT_RESULT')
    if output:
        Path(output).write_text(json.dumps({
            'tests': result.testsRun, 'passed': result.passed,
            'failures': [{'id': test.id(), 'traceback': trace} for test, trace in result.failures],
            'errors': [{'id': test.id(), 'traceback': trace} for test, trace in result.errors],
            'skipped': [{'id': test.id(), 'reason': reason} for test, reason in result.skipped],
            'expected_failures': len(result.expectedFailures),
            'unexpected_successes': len(result.unexpectedSuccesses),
            'synthetic_database_only': True,
        }, ensure_ascii=False, indent=2), encoding='utf-8')


class AuditRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        if os.environ.get('FULL_AUDIT_LEGACY') == '1':
            from ctf_backend.security_bootstrap import bind_legacy_for_tests
            from data_security.contracts import Environment
            bind_legacy_for_tests(environment=Environment.TEST)

    def get_resultclass(self):
        return AuditResult

    def run_suite(self, suite, **kwargs):
        result = super().run_suite(suite, **kwargs)
        write_result(result)
        return result
