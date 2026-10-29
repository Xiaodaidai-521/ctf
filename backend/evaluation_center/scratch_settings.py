"""Explicit disk-backed local scratch settings, never production configuration.

Create an empty /tmp/m8-scratch-* directory, then set EVALUATION_SCRATCH_DATABASE
inside it. Live requests additionally require EVALUATION_LIVE_GATEWAY=1.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .test_settings import *  # noqa: F403

raw_path = os.environ.get('EVALUATION_SCRATCH_DATABASE', '')
scratch_path = Path(raw_path).resolve()
if (not Path(raw_path).is_absolute() or scratch_path.parent.parent != Path('/tmp') or
        not scratch_path.parent.name.startswith('m8-scratch-') or scratch_path.suffix != '.sqlite3'):
    raise ImproperlyConfigured('需要独立 /tmp/m8-scratch-* 目录下的绝对 .sqlite3 路径。')
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(scratch_path)}}
DEBUG = False
EVALUATION_SCRATCH = True
EVALUATION_LIVE_GATEWAY_ENABLED = os.environ.get('EVALUATION_LIVE_GATEWAY') == '1'
EVALUATION_GATEWAY_KEY_INDEX = int(os.environ.get('EVALUATION_GATEWAY_KEY_INDEX', '0'))
EVALUATION_TEST_ADAPTER_ENABLED = False
EVALUATION_SERVICE_TOKEN = ''
FEEDBACK_PHASE3_ENABLED = True
FEEDBACK_PHASE3_RELEASE_ENABLED = False
