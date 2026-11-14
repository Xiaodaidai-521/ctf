"""Verify the ordinary challenge topology without Docker or application data."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
env = os.environ.copy()
env.update(TLS_CERT_DIR='C:/logic-fixture/tls', FRPS_CONFIG_FILE='C:/logic-fixture/frps.ini')
result = subprocess.run(['docker', 'compose', 'config', '--format', 'json'],
    cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8')
if result.returncode:
    raise RuntimeError('COMPOSE_STRUCTURE_CHECK_FAILED')
config = json.loads(result.stdout)
backend = config['services']['backend']
environment = backend['environment']
networks = [config['networks'][name]['name'] for name in backend['networks']]
selected = environment['DOCKER_NETWORK']
assert selected in networks
assert config['networks']['ctf-challenge']['internal'] is True
assert not environment['CONTAINER_PROXY_HOST']
assert environment['CONTAINER_PROXY_SCHEME'] == 'https'

# Isolated settings only, with no database query and no real Docker operation.
os.environ.pop('DATA_SECURITY_CONFIG', None)
os.environ.update(SECRET_KEY='synthetic-logic-topology-framework-key',
    DATA_PROTECTION_ENABLED='false', DATABASE_BACKEND='sqlite', DEBUG='true',
    DJANGO_SETTINGS_MODULE='data_security.privacy_test_settings')
sys.path.insert(0, str(ROOT / 'backend'))
sys.argv = [sys.argv[0], 'test']
import django
django.setup()
from django.test import override_settings
from challenges.container_manager import ContainerManager
from challenges.access import build_access_url

client = Mock()
with override_settings(DOCKER_NETWORK=selected, CONTAINER_PROXY_HOST='', CONTAINER_PROXY_SCHEME='https'), \
        patch('challenges.container_manager.docker.from_env', return_value=client), \
        patch('challenges.container_manager.get_frp_manager'), \
        patch('challenges.container_manager.get_port_pool'):
    manager = ContainerManager()
    url = build_access_url(SimpleNamespace(runtime_metadata={}, user_id=101, container_id='synthetic01'))
client.networks.get.assert_called_once_with(selected)
client.networks.create.assert_not_called()
assert url == '/challenge/101-synthetic01/'
evidence = {'synthetic_only': True, 'docker_daemon_called': False, 'database_accessed': False,
    'compose_uses_placeholder_tls_frps_paths': True, 'backend_network_names': networks,
    'manager_network': manager.network_name, 'manager_network_is_shared_with_backend': True,
    'challenge_network_is_internal': True, 'ordinary_challenge_access_url': url,
    'published_ports': [entry['published'] for entry in backend['ports']],
    'explicit_public_origin_supported': True}
target = ROOT / 'artifacts/logic-fix-deployment-20261113.json'
target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(evidence, ensure_ascii=False, indent=2))
