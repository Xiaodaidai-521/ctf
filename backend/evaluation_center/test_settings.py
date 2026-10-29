"""Explicit isolated configuration. Never import from production settings/URLs."""
import os

from ctf_backend.settings import *  # noqa: F403

ROOT_URLCONF = 'evaluation_center.test_urls'
EVALUATION_ISOLATED_TESTS = True
EVALUATION_TEST_ADAPTER_ENABLED = True
# No known default credential. Tests override these with independent accounts.
EVALUATION_SERVICE_TOKEN = os.environ.get('EVALUATION_SERVICE_TOKEN', '')
EVALUATION_SERVICE_ACCOUNT_ID = None
EVALUATION_UNAVAILABLE_DEPENDENCIES = ()
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
