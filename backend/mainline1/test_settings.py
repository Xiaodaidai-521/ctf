"""Isolated test settings. Never import production settings or load .env."""
import os

SECRET_KEY = 'synthetic-tests-only-not-a-deployment-key'
INSTALLED_APPS = ['mainline1.apps.Mainline1Config']
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'HOST': '127.0.0.1',
    'PORT': os.environ['MAINLINE1_TEST_PORT'],
    'NAME': 'postgres',
    'USER': 'mainline1_test',
    'TEST': {'NAME': 'test_mainline1'},
}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
