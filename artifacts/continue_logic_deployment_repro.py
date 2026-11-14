"""Inspect Compose topology and execute network selection with a fake Docker client.

Only isolated settings and synthetic container objects are used. Compose secrets
are parsed in memory and are never included in the saved or printed projection.
No Docker daemon operation, application database access, or model call occurs.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.state' / 'continue-audit-20261113' / 'deployment'
OUTPUT.mkdir(parents=True, exist_ok=True)
compose_env = os.environ.copy()
compose_env.update(TLS_CERT_DIR='C:/audit-placeholder/tls',
                   FRPS_CONFIG_FILE='C:/audit-placeholder/frps.ini')
result = subprocess.run(['docker', 'compose', 'config', '--format', 'json'],
                        cwd=ROOT, env=compose_env, capture_output=True,
                        text=True, encoding='utf-8')
if result.returncode:
    raise RuntimeError('COMPOSE_STRUCTURE_CHECK_FAILED')
config = json.loads(result.stdout)
backend = config['services']['backend']
environment = backend.get('environment', {})
manager_network = environment.get('DOCKER_NETWORK', 'ctf-challenge')
backend_networks = [config['networks'][name]['name']
                    for name in backend.get('networks', {})]

# Do not load .env or use its database configuration for the Python fixture.
os.environ.pop('DATA_SECURITY_CONFIG', None)
os.environ.update(SECRET_KEY='synthetic-deployment-audit-framework-key',
                  DATA_PROTECTION_ENABLED='false', DATABASE_BACKEND='sqlite',
                  DEBUG='true', DJANGO_SETTINGS_MODULE='data_security.privacy_test_settings')
sys.path.insert(0, str(ROOT / 'backend'))
sys.argv = [sys.argv[0], 'test']
import django
django.setup()
import docker
from django.test import override_settings
from challenges.container_manager import ContainerManager
from challenges.access import build_access_url

fake_client = Mock()
fake_client.networks.get.side_effect = docker.errors.NotFound('synthetic missing network')
with override_settings(DOCKER_NETWORK=manager_network), \
        patch('challenges.container_manager.docker.from_env', return_value=fake_client), \
        patch('challenges.container_manager.get_frp_manager'), \
        patch('challenges.container_manager.get_port_pool'):
    manager = ContainerManager()
created_network = fake_client.networks.create.call_args.args[0]

scheme = environment.get('CONTAINER_PROXY_SCHEME') or (
    'https' if str(environment.get('SECURE_SSL_REDIRECT', 'false')).lower()
    in ('true', '1', 'yes') else 'http')
host = environment.get('CONTAINER_PROXY_HOST', 'localhost:8000')
with override_settings(CONTAINER_PROXY_HOST=host, CONTAINER_PROXY_SCHEME=scheme):
    access_url = build_access_url(SimpleNamespace(runtime_metadata={},
                                 user_id=101, container_id='synthetic01'))

evidence = {
    'synthetic_only': True,
    'docker_daemon_called': False,
    'database_accessed': False,
    'compose_uses_placeholder_tls_frps_paths': True,
    'project_name': config['name'],
    'backend_network_names': backend_networks,
    'actual_manager_network_selection': manager.network_name,
    'fake_docker_network_created': created_network,
    'manager_network_is_shared_with_backend': created_network in backend_networks,
    'ordinary_challenge_access_url': access_url,
    'published_ports': [entry['published'] for entry in backend.get('ports', [])],
    'backend_only_listens_on_loopback_8000': '--bind 127.0.0.1:8000'
        in (ROOT / 'backend' / 'start.sh').read_text(encoding='utf-8'),
}
assert evidence['manager_network_is_shared_with_backend'] is False
assert host == 'localhost:8000' and '8000' not in evidence['published_ports']
path = OUTPUT / 'topology-repro.json'
path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(evidence, ensure_ascii=True, indent=2))
