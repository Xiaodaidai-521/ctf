"""Original mainline1 app set, with an identified isolated PostgreSQL database."""
import os

if os.environ.get('DATA_SECURITY_ISOLATED_TEST') != '1':
    raise RuntimeError('ISOLATED_TEST_OPT_IN_REQUIRED')

from mainline1.test_settings import *

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'HOST': os.environ['DS_TEST_PG_SOCKET'],
    'PORT': os.environ['DS_TEST_PG_PORT'],
    'NAME': 'ds_phase1_mainline',
    'USER': 'mainline1_test',
    'TEST': {'NAME': 'test_mainline1'},
}}
TEST_RUNNER = 'tools.data_security.test_runner.IsolatedRunner'
