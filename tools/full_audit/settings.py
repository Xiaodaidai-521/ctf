"""Full app and production URL set, with an owned synthetic PostgreSQL database."""
import json
import os
from pathlib import Path

if os.environ.get('FULL_AUDIT_ISOLATED') != '1':
    raise RuntimeError('FULL_AUDIT_ISOLATED_REQUIRED')

from ctf_backend.settings import *  # noqa: F403,E402

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.state' / 'full-audit-20261113'
_config = json.loads((STATE / 'postgres.json').read_text())
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql', 'HOST': '127.0.0.1',
    'PORT': _config['port'], 'USER': 'full_audit', 'NAME': 'full_audit',
    'OPTIONS': {'sslmode': 'disable'},
    'TEST': {'NAME': os.environ.get('FULL_AUDIT_TEST_DB', 'test_full_audit')},
}}
MEDIA_ROOT = STATE / 'media'
STATIC_ROOT = STATE / 'static'
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
TEST_RUNNER = 'tools.full_audit.runner.AuditRunner'
