"""Pinned file policies; writes require an explicit composition-time capability."""
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile

from data_security.contracts import ContractViolation, PolicySnapshot, ProtectionError, ReasonCode
from data_security.contracts.schema import canonical_bytes, require
from data_security.adapters.persistence.policy_writes import check_write


class FilePolicyRepository:
    def __init__(self, *, path, writable=False):
        self.path, self.writable = Path(path), writable
        require(self.path.is_absolute() and self.path == self.path.resolve(),
                ReasonCode.POLICY_NOT_APPROVED)

    def _snapshots(self):
        info = self.path.lstat()
        require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o022 and
                info.st_size <= 1024 * 1024, ReasonCode.POLICY_NOT_APPROVED)
        with self.path.open('rb') as source:
            data = source.read(1024 * 1024 + 1)
        require(len(data) <= 1024 * 1024, ReasonCode.LIMIT_EXCEEDED)
        value = json.loads(data)
        if value.get('schema_version') == PolicySnapshot.SCHEMA:
            return [PolicySnapshot.from_json(data)]
        require(set(value) == {'schema_version', 'snapshots'} and
                value['schema_version'] == 'ds.policy-store.v1' and
                type(value['snapshots']) is list, ReasonCode.POLICY_NOT_APPROVED)
        snapshots = [PolicySnapshot.from_wire(item) for item in value['snapshots']]
        require(len({item.version for item in snapshots}) == len(snapshots), ReasonCode.DUPLICATE_FIELD)
        return snapshots

    def read(self, binding):
        try:
            snapshots = self._snapshots()
            snapshot = next((item for item in snapshots if
                (item.version, item.content_hash) ==
                (binding.protection_version, binding.protection_hash)), None)
            require(snapshot is not None, ReasonCode.POLICY_NOT_APPROVED)
            return snapshot
        except (OSError, ValueError, TypeError, AttributeError, ContractViolation):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.POLICY_NOT_APPROVED, retryable=False, trace_id='policy/file')

    def put(self, snapshot, expected_version):
        if not self.writable:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUTHORIZATION_DENIED, retryable=False, trace_id='policy/file')
        temporary = None
        try:
            # The separate lock survives atomic replacement of the document.
            with os.fdopen(os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), 'rb') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                snapshots = self._snapshots() if self.path.exists() else []
                check_write(snapshots, snapshot, expected_version)
                snapshots = [snapshot if item.version == snapshot.version else item for item in snapshots]
                if not any(item.version == snapshot.version for item in snapshots):
                    snapshots.append(snapshot)
                data = canonical_bytes({'schema_version': 'ds.policy-store.v1', 'snapshots': tuple(snapshots)})
                require(len(data) <= 1024 * 1024, ReasonCode.LIMIT_EXCEEDED)
                fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix='.policy-')
                with os.fdopen(fd, 'wb') as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
                temporary = None
            return True
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=error.code, retryable=False, trace_id='policy/file')
        except (OSError, ValueError, TypeError, AttributeError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.POLICY_NOT_APPROVED, retryable=False, trace_id='policy/file')
        finally:
            if temporary is not None:
                os.unlink(temporary)
