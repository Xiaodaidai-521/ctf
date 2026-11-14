"""Record pure test outcomes and explicitly opt into the existing test binding."""
import os
import unittest

from tools.full_audit.runner import AuditResult

if os.environ.get('FULL_AUDIT_LEGACY') == '1':
    from ctf_backend.security_bootstrap import bind_legacy_for_tests
    from data_security.contracts import Environment
    bind_legacy_for_tests(environment=Environment.TEST)

unittest.main(module=None, testRunner=unittest.TextTestRunner(
    verbosity=2, resultclass=AuditResult))
