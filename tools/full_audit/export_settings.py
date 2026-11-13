"""Isolated settings for the separate controlled export reference service."""
import os
if os.environ.get('FULL_AUDIT_ISOLATED') != '1':
    raise RuntimeError('FULL_AUDIT_ISOLATED_REQUIRED')
from controlled_export_service.settings import *  # noqa: F403,E402
VAR_DIR = os.environ['CONTROLLED_EXPORT_VAR_DIR']
DATABASES['default']['TEST'] = {'NAME': os.environ['FULL_AUDIT_TEST_DB']}  # noqa: F405
TEST_RUNNER = 'tools.full_audit.runner.AuditRunner'
