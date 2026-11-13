"""Isolated Windows nginx + stdlib HTTP fixtures; no platform data or Docker."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection, HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
import socket
import ssl
import subprocess
import threading
import time
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

PROJECT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
location = json.loads((OUT / 'runtime-nginx-location.json').read_text())
work = Path(location['root'])
nginx = Path(location['nginx'])
checks = {}
seen = []


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        seen.append({'path': self.path, 'host': self.headers.get('Host'),
                     'scheme': self.headers.get('X-Forwarded-Proto')})
        body = b'healthy\n' if self.path == '/proxy/health/' else b'upstream-fixture'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        result = json.dumps({'bytes': len(body), 'path': self.path}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(result)))
        self.end_headers()
        self.wfile.write(result)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


upstream = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
threading.Thread(target=upstream.serve_forever, daemon=True).start()
upstream_port = upstream.server_address[1]
http_port, https_port = free_port(), free_port()
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
now = datetime.now(timezone.utc)
cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), False)
        .sign(key, hashes.SHA256()))
cert_path, key_path = work / 'server.crt', work / 'server.key'
cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                     serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
for subdir in ('html', 'media', 'static', 'body', 'proxy', 'logs', 'temp'):
    (work / subdir).mkdir(exist_ok=True)
(work / 'html/index.html').write_text('SPA fixture')
(work / 'media/resource_covers').mkdir(exist_ok=True)
(work / 'media/resource_covers/cover.png').write_bytes(b'cover-fixture')
(work / 'media/feedback_evidence').mkdir(exist_ok=True)
(work / 'media/feedback_evidence/secret.txt').write_bytes(b'private-fixture')
(work / 'static/app.js').write_bytes(b'static-fixture')
source = (PROJECT / 'frontend/nginx.conf').read_text('utf-8')
source = source.replace('listen 80;', f'listen 127.0.0.1:{http_port};')
source = source.replace('listen 443 ssl;', f'listen 127.0.0.1:{https_port} ssl;')
source = source.replace('/etc/nginx/tls/', work.as_posix() + '/')
source = source.replace('/usr/share/nginx/html', (work / 'html').as_posix())
source = source.replace('/usr/share/nginx/media/', (work / 'media').as_posix() + '/')
source = source.replace('/usr/share/nginx/static/', (work / 'static').as_posix() + '/')
source = source.replace('127.0.0.1:8000', f'127.0.0.1:{upstream_port}')
source = source.replace('error_log /dev/null;', 'error_log off;')
config = (f'pid {work.as_posix()}/nginx.pid; error_log {work.as_posix()}/error.log;\n'
          f'events {{ worker_connections 64; }}\nhttp {{\n'
          f'client_body_temp_path {work.as_posix()}/body;\n'
          f'proxy_temp_path {work.as_posix()}/proxy;\n{source}\n}}\n')
config_path = work / 'audit.conf'
config_path.write_text(config, encoding='utf-8')
args = [str(nginx), '-p', work.as_posix() + '/', '-c', str(config_path)]
process = None


def request(path, body=None):
    context = ssl.create_default_context(cafile=str(cert_path))
    connection = HTTPSConnection('localhost', https_port, context=context, timeout=8)
    try:
        connection.request('GET' if body is None else 'POST', path, body=body)
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        connection.close()


try:
    syntax = subprocess.run(args + ['-t'], capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    checks['nginx_configuration_valid'] = syntax.returncode == 0
    if syntax.returncode:
        raise RuntimeError(syntax.stderr)
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(50):
        try:
            with socket.create_connection(('127.0.0.1', https_port), timeout=.1):
                break
        except OSError:
            time.sleep(.1)
    status, body, headers = request('/learning/map/deep-link')
    checks['spa_deep_link'] = status == 200 and body == b'SPA fixture'
    checks['tls_and_hsts'] = headers.get('Strict-Transport-Security') == 'max-age=300'
    status, body, _ = request('/static/app.js')
    checks['django_static_alias_over_regex'] = status == 200 and body == b'static-fixture'
    status, body, _ = request('/media/resource_covers/cover.png')
    checks['media_alias_over_regex'] = status == 200 and body == b'cover-fixture'
    checks['feedback_attachment_public_path_denied'] = request('/media/feedback_evidence/secret.txt')[0] == 404
    checks['resource_public_path_denied'] = request('/media/resources/private.pdf')[0] == 404
    status, body, _ = request('/challenge/example/app.js')
    checks['challenge_static_forwarded'] = status == 200 and body == b'upstream-fixture' and seen[-1]['path'] == '/challenge/example/app.js'
    checks['upstream_secure_scheme'] = seen[-1]['scheme'] == 'https'
    status, body, _ = request('/api/resources/upload/', b'x' * (2 * 1024 * 1024))
    checks['two_mib_upload_forwarded'] = status == 200 and json.loads(body)['bytes'] == 2 * 1024 * 1024
    checks['private_proxy_temporary_files_absent'] = not list((work / 'body').rglob('*')) and not list((work / 'proxy').rglob('*'))
    context = ssl.create_default_context(cafile=str(cert_path))
    conn = HTTPSConnection('localhost', https_port, context=context, timeout=5)
    conn.request('POST', '/api/resources/upload/', headers={'Content-Length': str(57 * 1024 * 1024)})
    response = conn.getresponse()
    checks['oversized_upload_denied'] = response.status == 413
    response.read()
    conn.close()
    conn = HTTPConnection('localhost', http_port, timeout=5)
    conn.request('GET', '/test')
    response = conn.getresponse()
    checks['http_redirects_to_https'] = response.status == 308 and response.getheader('Location').startswith('https://')
    response.read()
    conn.close()
    spec = importlib.util.spec_from_file_location('readiness', PROJECT / 'backend/healthcheck.py')
    readiness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(readiness)
    with patch.object(readiness, 'HTTPConnection', side_effect=lambda *a, **kw: HTTPConnection('127.0.0.1', upstream_port, timeout=5)):
        with patch.dict(os.environ, {'ALLOWED_HOSTS': '.example.test,localhost'}):
            checks['readiness_probe_success'] = readiness.main() == 0
            checks['readiness_probe_host_and_scheme'] = seen[-1] == {'path': '/proxy/health/', 'host': 'example.test', 'scheme': 'https'}
    with patch.object(readiness, 'HTTPConnection', side_effect=lambda *a, **kw: HTTPConnection('127.0.0.1', free_port(), timeout=1)):
        checks['readiness_probe_connection_failure'] = readiness.main() == 1
    print(json.dumps(checks, indent=2))
    assert all(checks.values())
finally:
    if process is not None:
        subprocess.run(args + ['-s', 'quit'], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
    upstream.shutdown()
    upstream.server_close()
    cert_path.unlink(missing_ok=True)
    key_path.unlink(missing_ok=True)
    (OUT / 'runtime-smoke-results.json').write_text(json.dumps({
        'scope': 'isolated nginx 1.28.0 Windows; loopback fixtures, generated one-hour TLS certificate',
        'checks': checks, 'all_passed': bool(checks) and all(checks.values()),
        'production_data_accessed': False, 'docker_executed': False,
        'real_django_gunicorn_chain_verified': False,
        'temporary_tls_key_removed': not key_path.exists(),
        'nginx_stopped': process is None or process.poll() is not None,
    }, indent=2), encoding='utf-8')
