"""Isolated random field/index keys; no reusable secret enters repository or evidence."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets

from data_security.contracts import KeyPurpose, KeyReference, KeyStatus
from data_security.tests.phase3_fixtures import configuration


@contextmanager
def field_configuration(*, dual_index=False, legacy_reads=False):
    with configuration(providers=()) as (path, config, refs, values, binding):
        manifest_path = Path(config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        indexes = []
        for version in (('v2', 'v1') if dual_index else ('v1',)):
            key = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='query-index/' + version,
                               purpose=KeyPurpose.INDEX, version=version, status=KeyStatus.ACTIVE)
            target = path.parent / ('index-' + version + '.key')
            target.write_bytes(secrets.token_bytes(32))
            target.chmod(0o600)
            manifest['entries'].append({'reference': key.to_wire(), 'file': target.name,
                                        'identities': ['service/security']})
            indexes.append(key.to_wire())
        manifest_path.write_text(json.dumps(manifest))
        proof = Path('/home/hatch/workspace/data-security-seven-phases/evidence/phase-03/phase3-backup-20261105T081657523598Z.json')
        config.update(schema_version='ds.bootstrap.v2', policy_repository={'kind': 'file', 'writable': False},
            field_storage={'index_keys': indexes, 'read_keys': [], 'legacy_reads': legacy_reads,
                'recovery_record': {'path': str(proof), 'sha256': hashlib.sha256(proof.read_bytes()).hexdigest()}})
        if dual_index:
            config['field_storage']['index_deadline'] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        path.write_text(json.dumps(config))
        yield path, config, refs, binding
