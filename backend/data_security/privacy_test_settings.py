"""Isolated SQLite tests for public privacy projections, never deployment settings."""
from evaluation_center.test_settings import *  # noqa: F403

ROOT_URLCONF = 'ctf_backend.urls'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
