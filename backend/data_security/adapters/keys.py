"""One explicit, repository-external secret directory; no environment fallback."""
import json
import os
from pathlib import Path
import stat

from data_security.contracts import (ContractViolation, Environment, KeyPurpose,
    KeyReference, KeyStatus, ProtectionError, ReasonCode, SecretMaterial)
from data_security.contracts.schema import reference, require


class FileKeyResolver:
    def __init__(self, *, manifest_path, environment, repository_root, query_index=False):
        self.manifest = Path(manifest_path)
        self.environment = environment
        require(type(query_index) is bool, ReasonCode.INVALID_TYPE)
        self.query_index = query_index
        require(type(environment) is Environment, ReasonCode.INVALID_TYPE)
        require(self.manifest.is_absolute() and self.manifest == self.manifest.resolve(),
                ReasonCode.KEY_UNAVAILABLE)
        require(not self.manifest.is_relative_to(Path(repository_root).resolve()),
                ReasonCode.KEY_UNAVAILABLE)
        directory = self.manifest.parent.stat()
        require(stat.S_ISDIR(directory.st_mode) and directory.st_uid == os.getuid() and
                stat.S_IMODE(directory.st_mode) == 0o700, ReasonCode.KEY_UNAVAILABLE)
        self._entries()

    def _read(self, path, maximum):
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= maximum,
                ReasonCode.KEY_UNAVAILABLE)
        with path.open('rb') as source:
            value = source.read(maximum + 1)
        require(0 < len(value) <= maximum, ReasonCode.KEY_UNAVAILABLE)
        return value

    def _entries(self):
        document = json.loads(self._read(self.manifest, 65536))
        require(type(document) is dict and set(document) == {'schema_version', 'environment', 'entries'},
                ReasonCode.KEY_UNAVAILABLE)
        require(document['schema_version'] == 'ds.key-manifest.v1' and
                document['environment'] == self.environment.value, ReasonCode.KEY_UNAVAILABLE)
        entries = document['entries']
        require(type(entries) is list and len(entries) <= 64, ReasonCode.KEY_UNAVAILABLE)
        result, paths = {}, set()
        for entry in entries:
            require(type(entry) is dict and set(entry) == {'reference', 'file', 'identities'},
                    ReasonCode.KEY_UNAVAILABLE)
            ref = KeyReference.from_wire(entry['reference'])
            filename, identities = entry['file'], entry['identities']
            require(type(filename) is str and filename not in ('', '.', '..') and
                    Path(filename).name == filename and filename != self.manifest.name,
                    ReasonCode.KEY_UNAVAILABLE)
            require(type(identities) is list and 0 < len(identities) <= 16,
                    ReasonCode.KEY_UNAVAILABLE)
            for identity in identities:
                reference(identity)
            require(ref.key_ref not in result and filename not in paths, ReasonCode.KEY_UNAVAILABLE)
            result[ref.key_ref] = (ref, self.manifest.parent / filename, tuple(identities))
            paths.add(filename)
        return result

    def resolve(self, key_ref, purpose, service_identity):
        try:
            require(type(key_ref) is KeyReference and type(purpose) is KeyPurpose and
                    key_ref.purpose is purpose and key_ref.status is not KeyStatus.RETIRED,
                    ReasonCode.KEY_UNAVAILABLE)
            # Query indexing is an explicit phase-four capability; association stays closed.
            require(purpose not in (KeyPurpose.LINK, KeyPurpose.PSEUDONYM) and
                    (purpose is not KeyPurpose.INDEX or self.query_index), ReasonCode.AUTHORIZATION_DENIED)
            reference(service_identity)
            entry = self._entries().get(key_ref.key_ref)
            require(entry is not None, ReasonCode.KEY_UNAVAILABLE)
            authoritative, path, identities = entry
            require(authoritative == key_ref and service_identity in identities,
                    ReasonCode.KEY_UNAVAILABLE)
            value = self._read(path, 65536)
            if purpose in (KeyPurpose.DATA, KeyPurpose.AUDIT, KeyPurpose.AUTHORITY, KeyPurpose.SHARE, KeyPurpose.INDEX):
                require(len(value) == 32, ReasonCode.KEY_UNAVAILABLE)
            return SecretMaterial(value, purpose=purpose)
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.KEY_UNAVAILABLE, retryable=False, trace_id='keys/resolve')


def legacy_teacher_inputs():
    """Default command compatibility only; formal bootstrap replaces this loader."""
    return {'username': os.environ.get('TEACHER_USERNAME', 'teacher'),
            'email': os.environ.get('TEACHER_EMAIL', ''),
            'password': os.environ.get('TEACHER_PASSWORD', ''),
            'reset_password': os.environ.get('TEACHER_RESET_PASSWORD', '').lower() in ('1', 'true', 'yes')}
