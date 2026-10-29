"""Disposable local acceptance infrastructure, not a production runtime adapter.

Two independent actual releases, network/PID/mount namespaces and root filesystems.
The observer ports only expose the fixed read API; student ports consult the real
platform identity/lifecycle API on every request. No deployment approval is made.
"""
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'evidence/module5'
TOOLS = Path(__file__).resolve().parent
release = Path(sys.argv[1]).resolve()
runtime = Path(tempfile.mkdtemp(prefix='module5-r2-live-', dir='/var/tmp'))
control_path = runtime / 'control.json'
control_path.write_text('{}')
os.chmod(control_path, 0o600)
manifest = {'runtime': str(runtime), 'control': str(control_path), 'platform': 'http://127.0.0.1:18380', 'instances': {}}
processes, servers, logs = [], [], []
stop = threading.Event()


def unix_get(path, target):
    connection = http.client.HTTPConnection('localhost', timeout=12)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.settimeout(12)
    connection.sock.connect(str(path))
    try:
        connection.request('GET', target)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read(1024 * 1024)
    finally:
        connection.close()


def handler(instance, observer):
    class Gateway(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if observer:
                if self.path != '/api/Challenges':
                    self.send_error(404)
                    return
            else:
                if self.path.startswith('/__r2__/'):
                    self.send_error(404)
                    return
                try:
                    control = json.loads(control_path.read_text())
                    assignment = control.get('assignments', {}).get(instance['name'])
                    auth = self.headers.get('Authorization', '')
                    if not assignment or not auth.startswith('Token '):
                        self.send_error(401)
                        return
                    connection = http.client.HTTPConnection('127.0.0.1', 18380, timeout=5)
                    try:
                        connection.request('GET', f'/api/practical-training/assignments/{assignment}/',
                                           headers={'Authorization': auth})
                        response = connection.getresponse()
                        payload = json.loads(response.read())
                        if response.status != 200 or payload.get('state') != 'active':
                            self.send_error(403)
                            return
                    finally:
                        connection.close()
                except (OSError, ValueError, http.client.HTTPException):
                    self.send_error(503)
                    return
            try:
                status, headers, body = unix_get(instance['socket'], self.path)
                self.send_response(status)
                for key in ('Content-Type', 'Location'):
                    if key in headers:
                        self.send_header(key, headers[key])
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (OSError, http.client.HTTPException):
                self.send_error(502)

        def log_message(self, format, *args):
            print(instance['name'], 'observer' if observer else 'student', format % args, flush=True)
    return Gateway


def close_all():
    receipt = {'stopped_at': time.time(), 'instances': {}}
    for server in servers:
        server.shutdown()
        server.server_close()
    for name, instance in manifest['instances'].items():
        pid = instance['supervisor_pid']
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    for name, instance in manifest['instances'].items():
        errors = {}
        for key in ('student_port', 'observer_port'):
            with socket.socket() as sock:
                sock.settimeout(1)
                errors[key] = sock.connect_ex(('127.0.0.1', instance[key]))
        receipt['instances'][name] = {'ports_errno': errors, 'supervisor_gone': not Path(f"/proc/{instance['supervisor_pid']}").exists()}
        state = Path(instance['root']) / 'state'
        for filename in ('juice.log', 'ready.json'):
            if (state / filename).exists():
                shutil.copy2(state / filename, EVIDENCE / f'r2-{name}-{filename}')
    (EVIDENCE / 'r2-runtime-cleanup.json').write_text(json.dumps(receipt, indent=2))
    for log in logs:
        log.close()


signal.signal(signal.SIGTERM, lambda *_: stop.set())
signal.signal(signal.SIGINT, lambda *_: stop.set())
try:
    class Canary(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'local host-control canary, not a production service')

        def log_message(self, format, *args):
            pass

    canary = http.server.ThreadingHTTPServer(('127.0.0.1', 18390), Canary)
    servers.append(canary)
    threading.Thread(target=canary.serve_forever, daemon=True).start()
    for index, name in enumerate(('student-a', 'student-b')):
        sandbox = runtime / name
        sandbox.mkdir(mode=0o700)
        shutil.copytree(release, sandbox / 'app', symlinks=True)
        (sandbox / 'r2').mkdir()
        shutil.copy2(TOOLS / 'worker.py', sandbox / 'r2/worker.py')
        (sandbox / 'state').mkdir()
        log = (EVIDENCE / f'r2-{name}-supervisor.log').open('w')
        logs.append(log)
        process = subprocess.Popen([
            'unshare', '--user', '--map-root-user', '--mount', '--pid', '--fork', '--net', '--kill-child',
            '/usr/bin/python3', '-I', str(TOOLS / 'sandbox_bootstrap.py'), str(sandbox), str(18211 + index),
        ], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        instance = {'name': name, 'root': str(sandbox), 'socket': str(sandbox / 'state/relay.sock'),
                    'supervisor_pid': process.pid, 'app_port': 18211 + index,
                    'student_port': 18411 + index, 'observer_port': 18111 + index}
        manifest['instances'][name] = instance
        (EVIDENCE / 'r2-live-manifest.json').write_text(json.dumps(manifest, indent=2))
        for _ in range(240):
            if process.poll() is not None:
                raise RuntimeError(f'{name} supervisor exited {process.returncode}; inspect its log')
            if (sandbox / 'state/ready.json').exists():
                break
            time.sleep(0.5)
        else:
            raise TimeoutError(f'{name} did not become ready')
        for observer, key in ((True, 'observer_port'), (False, 'student_port')):
            server = http.server.ThreadingHTTPServer(('127.0.0.1', instance[key]), handler(instance, observer))
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        status, _, body = unix_get(instance['socket'], '/__r2__/probe')
        assert status == 200
        (EVIDENCE / f'r2-{name}-isolation.json').write_bytes(body)
    (EVIDENCE / 'r2-live-manifest.json').write_text(json.dumps(manifest, indent=2))
    print('TWO_REAL_JUICE_INSTANCES_READY', flush=True)
    deadline = time.time() + 3600
    while not stop.wait(0.5):
        if any(process.poll() is not None for process in processes):
            raise RuntimeError('An instance exited unexpectedly')
        config = json.loads(control_path.read_text())
        if time.time() >= min(deadline, config.get('expire_at', deadline)):
            print('REAL_EXPIRY_RECLAMATION', flush=True)
            break
finally:
    close_all()
