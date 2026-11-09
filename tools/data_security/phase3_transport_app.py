"""Synthetic socket probe using final project settings and real Django middleware.

Only the URLConf is replaced; TLS/cookie/database/secret settings are not mocked.
Never install this route in the application URLConf or use it against real data.
"""
import os

if os.environ.get('DS_PHASE3_TRANSPORT_RUN') != '1':
    raise RuntimeError('ISOLATED_TRANSPORT_PROBE_REQUIRED')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.db import connection
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.urls import path


def probe(request):
    request.session['phase3'] = 'synthetic'
    get_token(request)
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(), host(inet_server_addr()), host(inet_client_addr()),'
                       '(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())')
        database, server, client, ssl = cursor.fetchone()
    return JsonResponse({'secure': request.is_secure(), 'debug': settings.DEBUG,
        'ssl_redirect': settings.SECURE_SSL_REDIRECT,
        'session_cookie_secure': settings.SESSION_COOKIE_SECURE,
        'csrf_cookie_secure': settings.CSRF_COOKIE_SECURE,
        'hsts_seconds': settings.SECURE_HSTS_SECONDS,
        'hsts_subdomains': settings.SECURE_HSTS_INCLUDE_SUBDOMAINS,
        'hsts_preload': settings.SECURE_HSTS_PRELOAD,
        'proxy_header': settings.SECURE_PROXY_SSL_HEADER,
        'use_forwarded_host': settings.USE_X_FORWARDED_HOST,
        'db_options': settings.DATABASES['default']['OPTIONS'],
        'database': database, 'db_server': server, 'db_client': client, 'db_ssl': ssl})


urlpatterns = [path('api/phase3-transport/', probe)]
settings.ROOT_URLCONF = __name__
application = get_wsgi_application()
