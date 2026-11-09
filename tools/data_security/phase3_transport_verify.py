"""Real loopback TLS -> nginx -> Gunicorn -> final Django -> dedicated PG probe.

No Docker daemon, privileged ports, real providers, or host trust-store changes.
Cert/key inputs stay in a new external mode-0700 directory; E3 contains booleans,
versions and public configuration digests, never response cookies or private keys.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection, HTTPSConnection
from http.cookies import SimpleCookie
import json
import os
import pwd
import grp
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tools', required=True, type=Path)
    parser.add_argument('--controlled-parent', type=Path,
        default=Path('/home/hatch/workspace/data-security-seven-phases/isolated-material'))
    parser.add_argument('--evidence', type=Path,
        default=Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-03'))
    args = parser.parse_args()
    args.controlled_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='phase3-transport-', dir=args.controlled_parent))
    if work.resolve().is_relative_to(ROOT) or work.resolve().is_relative_to(args.evidence.resolve()):
        raise RuntimeError('EXTERNAL_CONTROLLED_DIRECTORY_REQUIRED')
    os.umask(0o077)
    cluster = json.loads((ROOT / '.state/postgres.json').read_text())
    assert cluster['synthetic_only'] and cluster['socket'] == str(ROOT / '.state/pg-run')
    pg = dict(host='127.0.0.1', port=cluster['port'], user=cluster['user'], dbname='postgres', sslmode='disable')
    database = 'phase3_backup_tls_' + uuid4().hex[:12]
    compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
    services = compose['services']
    configured = dict(item.split('=', 1) for item in services['backend']['environment'])
    assert services['frontend']['network_mode'] == 'service:backend'
    assert services['backend']['ports'] == ['127.0.0.1:80:80', '127.0.0.1:443:443']
    assert 'ports' not in services['postgres']
    assert any('TLS_CERT_DIR:?' in value and value.endswith(':/etc/nginx/tls:ro')
               for value in services['frontend']['volumes'])
    assert any('FRPS_CONFIG_FILE:?' in value and value.endswith(':/etc/frp/frps.ini:ro')
               for value in services['frp-server']['volumes'])
    assert configured['GUNICORN_CMD_ARGS'] == '--forwarded-allow-ips=127.0.0.1,::1'
    for service in ('backend', 'container-cleanup', 'analytics-scheduler'):
        values = dict(item.split('=', 1) for item in services[service]['environment'])
        assert values['DB_TRANSPORT'] == 'local' and values['DB_SSLMODE'] == 'disable'
    transport = {key: configured[key] for key in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE',
        'CSRF_COOKIE_SECURE', 'SECURE_HSTS_SECONDS', 'DB_TRANSPORT', 'DB_SSLMODE', 'GUNICORN_CMD_ARGS')}
    for name in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE'):
        assert transport[name] == 'True'
    evidence = {'scope': 'isolated local test certificates and synthetic PostgreSQL only', 'checks': {},
        'compose_daemon_started': False, 'startup_script_executed': False,
        'production_rotation_verified': False,
        'certificate_trust_store_modified': False, 'deployment_topology_approved': False,
        'independent_export_service': 'not deployed or enabled in phase 3; legacy isolated regression only',
        'risk_quota_delivery_enabled': False, 'independent_service_tls_covered': False,
        'versions': {'nginx': '1.24.0-2ubuntu7.19', 'nginx_license': 'BSD-2-Clause',
                     'nginx_packaging_licenses': ['BSD-2-Clause', 'MIT', 'GPL-2.0-or-later'],
                     'nginx_package_sha512': 'f4dc29550101ed5d3ca12f17013fe11922a0e15e0c14f44e69678c7d4497d1ebf0b5782d8553cd0dac796cbe0f87102f58c898b3ed72011329b2720960972144',
                     'gunicorn': '23.0.0', 'gunicorn_license': 'MIT',
                     'openssl': ssl.OPENSSL_VERSION, 'openssl_license': 'Apache-2.0'},
        'security_update_owner': 'deployment maintainer; review pinned packages before deployment',
        'configuration_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / 'docker-compose.yml', ROOT / 'frontend/nginx.conf',
                         ROOT / 'backend/nginx.conf', ROOT / 'backend/ctf_backend/settings.py',
                         ROOT / 'backend/start.sh')}}
    subprocess.run(['bash', '-n', str(ROOT / 'backend/start.sh')], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    evidence['startup_shell_syntax_valid'] = True
    checks = evidence['checks']
    processes = []
    db_created = False
    try:
        with closing(psycopg2.connect(**pg)) as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
            db_created = True
        # Only one isolated session table is needed to observe a real DB-backed cookie.
        with psycopg2.connect(**dict(pg, dbname=database)) as connection:
            with connection.cursor() as cursor:
                cursor.execute('CREATE TABLE django_session (session_key varchar(40) PRIMARY KEY, '
                               'session_data text NOT NULL, expire_date timestamptz NOT NULL)')
        for command in (
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
             '-subj', '/CN=Phase3 Isolated Test CA', '-keyout', str(work / 'ca.key'), '-out', str(work / 'ca.crt')],
            ['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=localhost',
             '-keyout', str(work / 'server.key'), '-out', str(work / 'server.csr')],
        ):
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        (work / 'extensions.cnf').write_text('subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n')
        subprocess.run(['openssl', 'x509', '-req', '-in', str(work / 'server.csr'), '-CA', str(work / 'ca.crt'),
            '-CAkey', str(work / 'ca.key'), '-CAcreateserial', '-days', '1', '-extfile', str(work / 'extensions.cnf'),
            '-out', str(work / 'server.crt')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        for name in ('server.key', 'ca.key'):
            (work / name).chmod(0o400)
        ports = []
        for _ in range(5):
            with socket.socket() as candidate:
                candidate.bind(('127.0.0.1', 0))
                ports.append(candidate.getsockname()[1])
        app_port, http_port, https_port, backend_http, backend_https = ports
        assert len(set(ports)) == 5
        env = dict(os.environ, **transport, DEBUG='False', ALLOWED_HOSTS='localhost,127.0.0.1',
            SECRET_KEY=secrets.token_urlsafe(64), DATA_SECURITY_CONFIG='', DS_PHASE3_TRANSPORT_RUN='1',
            DATABASE_BACKEND='postgres', DATABASE_URL='', DB_HOST='127.0.0.1', DB_PORT=str(cluster['port']),
            DB_USER=cluster['user'], DB_NAME=database, DB_PASSWORD='', PYTHONDONTWRITEBYTECODE='1',
            DJANGO_SETTINGS_MODULE='ctf_backend.settings', PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT / 'backend'))))
        gunicorn = subprocess.Popen([sys.executable, '-B', '-m', 'gunicorn', '--bind', f'127.0.0.1:{app_port}',
            '--workers', '1', '--access-logfile', '/dev/null', '--error-logfile', str(work / 'gunicorn.log'),
            'tools.data_security.phase3_transport_app:application'], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(gunicorn)
        (work / 'html').mkdir()
        (work / 'html/index.html').write_text('<!doctype html><title>Isolated transport</title>')
        for source, plain, secure in ((ROOT / 'frontend/nginx.conf', http_port, https_port),
                                      (ROOT / 'backend/nginx.conf', backend_http, backend_https)):
            configuration = source.read_text().replace('listen 80;', f'listen 127.0.0.1:{plain};')
            configuration = configuration.replace('listen 443 ssl;', f'listen 127.0.0.1:{secure} ssl;')
            configuration = configuration.replace('https://$host$request_uri', f'https://$host:{secure}$request_uri')
            configuration = configuration.replace('/etc/nginx/tls/', str(work) + '/')
            configuration = configuration.replace('127.0.0.1:8000', f'127.0.0.1:{app_port}')
            configuration = configuration.replace('frps-server:9123', f'127.0.0.1:{app_port}')
            configuration = configuration.replace('/usr/share/nginx/html', str(work / 'html'))
            configuration = configuration.replace('/var/log/nginx/', str(work) + '/')
            wrapped = (f'user {pwd.getpwuid(os.getuid()).pw_name} {grp.getgrgid(os.getgid()).gr_name};\n'
                       f'pid {work}/nginx-{plain}.pid; error_log {work}/nginx-{plain}.log;\n'
                       f'events {{}}\nhttp {{ access_log off; client_body_temp_path {work}/body-{plain};\n'
                       f'proxy_temp_path {work}/proxy-{plain}; fastcgi_temp_path {work}/fastcgi-{plain};\n'
                       f'uwsgi_temp_path {work}/uwsgi-{plain}; scgi_temp_path {work}/scgi-{plain};\n'
                       f'{configuration}\n}}\n')
            config_path = work / f'nginx-{plain}.conf'
            config_path.write_text(wrapped)
            process = subprocess.Popen([str(args.tools / 'usr/sbin/nginx'), '-p', str(work), '-c', str(config_path),
                '-g', 'daemon off; master_process off;'], cwd=ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(process)
        for port in (app_port, http_port, https_port, backend_http, backend_https):
            deadline = time.monotonic() + 25
            while True:
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError('ISOLATED_TRANSPORT_PROCESS_FAILED')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('ISOLATED_TRANSPORT_START_TIMEOUT') from None
                    time.sleep(0.1)
        context = ssl.create_default_context(cafile=str(work / 'ca.crt'))
        for port, path in ((http_port, '/api/phase3-transport/'), (backend_http, '/health')):
            with closing(HTTPConnection('127.0.0.1', port, timeout=5)) as client:
                client.request('GET', path, headers={'X-Forwarded-Proto': 'https'})
                response = client.getresponse()
                assert response.status == 308 and response.getheader('Location').startswith('https://')
                response.read()
        checks['http_redirect_frontend_and_optional_backend'] = True
        with closing(HTTPSConnection('localhost', https_port, context=context, timeout=5)) as client:
            client.request('GET', '/api/phase3-transport/', headers={
                'X-Forwarded-Proto': 'http', 'X-Forwarded-SSL': 'on', 'X-Forwarded-Protocol': 'ssl',
                'X-Forwarded-For': '203.0.113.90', 'X-Forwarded-Host': 'untrusted.invalid'})
            response = client.getresponse()
            assert response.status == 200
            body = json.loads(response.read())
            assert body['secure'] and not body['debug'] and body['ssl_redirect']
            assert body['proxy_header'] is None and not body['use_forwarded_host']
            assert body['session_cookie_secure'] and body['csrf_cookie_secure']
            assert body['hsts_seconds'] == 300 and not body['hsts_preload'] and not body['hsts_subdomains']
            assert 'max-age=300' in response.getheader('Strict-Transport-Security')
            cookies = SimpleCookie()
            for name, value in response.getheaders():
                if name.lower() == 'set-cookie':
                    cookies.load(value)
            assert cookies['sessionid']['secure'] and cookies['sessionid']['httponly']
            assert cookies['csrftoken']['secure']
            assert body['db_options']['sslmode'] == 'disable'
            assert body['database'] == database and body['db_server'] == body['db_client'] == '127.0.0.1'
            assert body['db_ssl'] is False
            checks['final_settings_compose_cookie_proxy_hsts_postgresql'] = True
            evidence['effective_settings'] = {key: value for key, value in body.items() if key != 'database'}
        # A different peer address is NOT trusted, even when it forges all scheme headers.
        with closing(HTTPConnection('127.0.0.1', app_port, timeout=5, source_address=('127.0.0.2', 0))) as client:
            client.request('GET', '/api/phase3-transport/', headers={'X-Forwarded-Proto': 'https'})
            response = client.getresponse()
            assert response.status == 301
            response.read()
        checks['untrusted_peer_cannot_forge_https'] = True
        for protocol in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            tls = ssl.create_default_context(cafile=str(work / 'ca.crt'))
            tls.minimum_version = tls.maximum_version = protocol
            with socket.create_connection(('127.0.0.1', https_port)) as tcp:
                with tls.wrap_socket(tcp, server_hostname='localhost') as secured:
                    assert secured.version() in ('TLSv1.2', 'TLSv1.3')
            checks[protocol.name] = True
        try:
            with socket.create_connection(('127.0.0.1', https_port)) as tcp:
                with ssl.create_default_context().wrap_socket(tcp, server_hostname='localhost'):
                    raise AssertionError('TEST_CA_WAS_GLOBALLY_TRUSTED')
        except ssl.SSLCertVerificationError:
            checks['untrusted_test_ca_rejected'] = True
        with closing(HTTPSConnection('localhost', backend_https, context=context, timeout=5)) as client:
            client.request('GET', '/health')
            response = client.getresponse()
            assert response.status == 200 and 'max-age=300' in response.getheader('Strict-Transport-Security')
            response.read()
        checks['optional_backend_nginx_actual_tls_hsts'] = True
        for mode, sslmode, expected in (('tls', 'disable', 1), ('tls', 'verify-full', 0),
                                        ('local', 'require', 1)):
            check_env = dict(env, DB_TRANSPORT=mode, DB_SSLMODE=sslmode)
            result = subprocess.run([sys.executable, '-B', '-c',
                'from ctf_backend.settings import DATABASES; assert DATABASES["default"]["OPTIONS"]["sslmode"] == "verify-full"'],
                cwd=ROOT, env=check_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            assert (result.returncode != 0) == bool(expected)
        checks['cross_host_insecure_db_modes_rejected'] = True
        evidence['returncode'] = 0
    except Exception as error:
        # Raw process errors/config/env/cookies are never copied to evidence.
        evidence['returncode'] = 1
        evidence['failure_type'] = type(error).__name__
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)
        if db_created:
            with closing(psycopg2.connect(**pg)) as connection:
                connection.autocommit = True
                with connection.cursor() as cursor:
                    cursor.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
        args.evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        evidence_path = args.evidence / ('phase3-transport-' + timestamp + '.json')
        with evidence_path.open('x') as output:
            json.dump(evidence, output, sort_keys=True, indent=2)
    print(json.dumps({'checks': checks, 'returncode': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
