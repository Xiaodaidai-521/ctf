"""Independent executor regression: fresh PostgreSQL, no business settings writes."""
import os
from pathlib import Path

if os.environ.get('DATA_SECURITY_ISOLATED_TEST') != '1':
    raise RuntimeError('ISOLATED_TEST_RUNNER_REQUIRED')
from tools.data_security.network_guard import install
install()

from controlled_export_service.settings import *  # noqa: E402,F403

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'HOST': os.environ['DS_TEST_PG_SOCKET'],
    'PORT': os.environ['DS_TEST_PG_PORT'],
    'USER': 'ds_phase1',
    'NAME': 'ds_phase1_export',
    'TEST': {'NAME': 'test_ds_phase1_export'},
}}
TEST_RUNNER = 'tools.data_security.test_runner.IsolatedRunner'
