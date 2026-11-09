"""Isolated regression settings; production settings are read, never changed."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.state'
for directory in (ROOT, ROOT / 'backend', Path.cwd()):
    if (directory / '.env').exists():
        raise RuntimeError('ISOLATED_TEST_DOTENV_FORBIDDEN')
if os.environ.get('DATA_SECURITY_ISOLATED_TEST') != '1':
    raise RuntimeError('ISOLATED_TEST_RUNNER_REQUIRED')

from tools.data_security.network_guard import install
install()

from ctf_backend.settings import *  # noqa: E402,F403

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'HOST': os.environ['DS_TEST_PG_SOCKET'],
    'PORT': os.environ['DS_TEST_PG_PORT'],
    'USER': 'ds_phase1',
    'NAME': 'ds_phase1_main',
    'TEST': {'NAME': 'test_ds_phase1_main'},
}}
MEDIA_ROOT = STATE / 'media'
STATIC_ROOT = STATE / 'static'
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
# Existing legacy suites run with their original assertions, not weaker hashers.
TEST_RUNNER = 'tools.data_security.test_runner.IsolatedRunner'
