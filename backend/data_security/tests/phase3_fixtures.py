"""Synthetic repository-external files; never used by the application bootstrap."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory

from data_security.contracts import KeyPurpose, KeyReference, KeyStatus, PolicyBinding, PolicySnapshot
from data_security.contracts.schema import content_hash
from data_security.adapters.llm.official import ENDPOINTS

ROOT = Path(__file__).resolve().parents[3]
MODELS = {'volcano': 'doubao-seed-2-0-lite-260428', 'deepseek': 'deepseek-v4-pro',
          'moonshot': 'moonshot-v1-8k', 'qwen': 'qwen-max', 'wenxin': 'ernie-bot-4', 'spark': 'generalv3.5'}


@contextmanager
def configuration(providers=tuple(ENDPOINTS)):
    with TemporaryDirectory(prefix='ds-phase3-synthetic-', dir='/tmp') as directory:
        directory = Path(directory)
        entries, refs, values = [], {}, {}
        for name, purpose in [('framework_key', KeyPurpose.FRAMEWORK), ('data_key', KeyPurpose.DATA),
                              ('audit_key', KeyPurpose.AUDIT)] + [(name, KeyPurpose.PROVIDER) for name in providers]:
            key_ref = f'provider/{name}/v1' if purpose is KeyPurpose.PROVIDER else purpose.value + '/v1'
            ref = KeyReference(schema_version=KeyReference.SCHEMA, key_ref=key_ref,
                               purpose=purpose, version='v1', status=KeyStatus.ACTIVE)
            value = secrets.token_bytes(32)
            if purpose in (KeyPurpose.FRAMEWORK, KeyPurpose.PROVIDER):
                value = ('synthetic-' + secrets.token_hex(32)).encode()
            if name == 'wenxin':
                value += b'|' + ('synthetic-' + secrets.token_hex(32)).encode()
            elif name == 'spark':
                value += b'|' + ('synthetic-' + secrets.token_hex(32)).encode() + b'|' + secrets.token_hex(32).encode()
            path = directory / (name + '.key')
            path.write_bytes(value)
            path.chmod(0o600)
            entries.append({'reference': ref.to_wire(), 'file': path.name, 'identities': ['service/security']})
            refs[name], values[name] = ref, value
        manifest = directory / 'manifest.json'
        manifest.write_text(json.dumps({'schema_version': 'ds.key-manifest.v1',
                                       'environment': 'evaluation', 'entries': entries}))
        manifest.chmod(0o600)
        policy_file = directory / 'approved-policy.json'
        policy_file.write_bytes((ROOT / 'docs/data-security/phase3-policy.json').read_bytes())
        policy_file.chmod(0o600)
        snapshot = PolicySnapshot.from_json(policy_file.read_bytes())
        binding = PolicyBinding(schema_version=PolicyBinding.SCHEMA, protection_version=snapshot.version,
            protection_hash=snapshot.content_hash, risk_version='risk/disabled-phase3',
            risk_hash=content_hash({'risk': 'disabled-phase3'}), contract_version='ds.m0.v1')
        config = {'schema_version': 'ds.bootstrap.v1', 'environment': 'evaluation',
            'key_manifest': str(manifest), 'policy_file': str(policy_file), 'policy_binding': binding.to_wire(),
            **{name: refs[name].to_wire() for name in ('framework_key', 'data_key', 'audit_key')},
            'providers': [{'endpoint_ref': name, 'base_url': ENDPOINTS[name],
                           'models': [MODELS[name]] + (['embedding-v1'] if name in ('qwen', 'volcano') else []),
                           'key_ref': refs[name].to_wire()} for name in providers], 'backup': None}
        path = directory / 'bootstrap.json'
        path.write_text(json.dumps(config))
        path.chmod(0o600)
        yield path, config, refs, values, binding
