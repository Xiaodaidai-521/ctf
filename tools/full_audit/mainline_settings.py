"""The optional internal parsing app tested separately from the public platform."""
import json
import os
from pathlib import Path

if os.environ.get('FULL_AUDIT_ISOLATED') != '1':
    raise RuntimeError('FULL_AUDIT_ISOLATED_REQUIRED')
SECRET_KEY = os.environ['SECRET_KEY']
INSTALLED_APPS = ['mainline1.apps.Mainline1Config']
_config = json.loads((Path(__file__).resolve().parents[2] / '.state' /
                      'full-audit-20261113' / 'postgres.json').read_text())
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql', 'HOST': '127.0.0.1',
    'PORT': _config['port'], 'USER': os.environ.get('FULL_AUDIT_MAINLINE_USER', 'full_audit'), 'NAME': 'full_audit',
    'OPTIONS': {'sslmode': 'disable'},
    'TEST': {'NAME': os.environ['FULL_AUDIT_TEST_DB']},
}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
TEST_RUNNER = 'tools.full_audit.runner.AuditRunner'
