"""Trusted UNIX relay inside one chroot/net/PID namespace; never a public service."""
import http.client
import http.server
import json
import os
from pathlib import Path
import resource
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time

port = int(sys.argv[1])
state = Path('/state')
state.mkdir(exist_ok=True)


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (256,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})


log = (state / 'juice.log').open('w')
env = {'PATH': '/usr/bin:/bin', 'HOME': '/tmp', 'NODE_ENV': 'production',
       'PORT': str(port), 'HOST': '127.0.0.1'}
node = subprocess.Popen(['/usr/bin/node', '--jitless', '--max-old-space-size=256',
                         '/app/build/app.js'], cwd='/app', env=env,
                        stdout=log, stderr=subprocess.STDOUT, preexec_fn=limits)


def probe():
    attempts = {}
    for label, host, target_port in (
        ('own_loopback', '127.0.0.1', port),
        ('peer_loopback', '127.0.0.1', 18212 if port == 18211 else 18211),
        ('host_control_canary', '127.0.0.1', 18390),
        ('private_network', '10.0.0.1', 443),
        ('production_canary_reserved', '192.0.2.1', 443),
        ('internet_route', '1.1.1.1', 443),
    ):
        with socket.socket() as sock:
            sock.settimeout(1)
            attempts[label] = {'host': host, 'port': target_port, 'errno': sock.connect_ex((host, target_port))}
    with socket.socket(socket.AF_INET6) as sock:
        sock.settimeout(1)
        attempts['ipv6_egress'] = {'host': '2001:db8::1', 'port': 443,
                                    'errno': sock.connect_ex(('2001:db8::1', 443))}
    memory = subprocess.run(['/usr/bin/python3', '-I', '-c',
        'import resource; resource.setrlimit(resource.RLIMIT_AS,(67108864,67108864));\n'
        'try: bytearray(134217728)\n'
        'except MemoryError: print("HOST_RLIMIT_AS_ENFORCED")\n'
        'else: raise SystemExit("limit not enforced")'], capture_output=True, text=True)
    return {
        'node_pid_in_namespace': node.pid, 'node_running': node.poll() is None,
        'namespaces': json.loads((state / 'namespaces.json').read_text()),
        'node_limits': 'Read back from host /proc by the acceptance driver; proc is deliberately absent here',
        'connect_attempts': attempts,
        'host_path_visible': Path('/home/hatch').exists(),
        'memory_enforcement_probe': {'exit_code': memory.returncode, 'stdout': memory.stdout, 'stderr': memory.stderr},
        'pids_limit': 'NOT_ENFORCED: no delegated cgroup pids controller; root uid RLIMIT_NPROC is not a boundary',
        'memory_boundary': 'RLIMIT_AS virtual memory, not cgroup RSS/aggregate memory',
    }


class Relay(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def do_GET(self):
        if self.path == '/__r2__/probe':
            data = json.dumps(probe()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        try:
            connection.request('GET', self.path, headers={'Host': f'127.0.0.1:{port}'})
            response = connection.getresponse()
            body = response.read(1024 * 1024)
            self.send_response(response.status)
            for key in ('Content-Type', 'Location'):
                if response.getheader(key):
                    self.send_header(key, response.getheader(key))
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (OSError, http.client.HTTPException) as exc:
            self.send_error(502, type(exc).__name__)
        finally:
            connection.close()

    def log_message(self, format, *args):
        print('relay', format % args, flush=True)


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


server = UnixServer('/state/relay.sock', Relay)
os.chmod('/state/relay.sock', 0o600)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    for _ in range(180):
        if node.poll() is not None:
            raise RuntimeError(f'Juice Shop exited: {node.returncode}')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                (state / 'ready.json').write_text(json.dumps({'port': port, 'pid': node.pid, 'ready_at': time.time()}))
                print('REAL_JUICE_READY', port, flush=True)
                break
        except OSError:
            time.sleep(0.5)
    else:
        raise TimeoutError('Juice Shop readiness timed out')
    while node.poll() is None:
        time.sleep(1)
finally:
    server.shutdown()
    node.terminate()
    try:
        node.wait(timeout=5)
    except subprocess.TimeoutExpired:
        node.kill()
        node.wait()
    log.close()
