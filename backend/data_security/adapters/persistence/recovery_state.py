"""Local isolated recovery journal. A restored database is not a traffic grant."""
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, Environment, ProtectionError, Purpose, ReasonCode, Role,
)
from data_security.contracts.schema import digest, require


STATE_FILE = '.restore-state.json'


def _read(path, maximum):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
        info = os.fstat(source.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600, ReasonCode.SOURCE_NOT_APPROVED)
        raw = source.read(maximum + 1)
    require(len(raw) <= maximum, ReasonCode.LIMIT_EXCEEDED)
    return raw


def _governance_receipt(value):
    require(type(value) is dict and value.get('state') in ('applying', 'applied'),
            ReasonCode.SOURCE_NOT_APPROVED)
    if value['state'] == 'applying':
        require(set(value) == {'state'}, ReasonCode.SOURCE_NOT_APPROVED)
        return None
    require(set(value) == {'state', 'receipt', 'inventory'} and type(value['inventory']) is dict
            and set(value['inventory']) == {'schema', 'private_files', 'pending_files'},
            ReasonCode.SOURCE_NOT_APPROVED)
    receipt = AuditReceipt.from_wire(value['receipt'])
    require(receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
            ReasonCode.SOURCE_NOT_APPROVED)
    return receipt


def recovery_admission(root, target_identity, *, limits):
    """Called once at the HTTP capability boundary, including after process restart."""
    try:
        raw = _read(Path(root) / STATE_FILE, limits.max_json_bytes)
    except FileNotFoundError:
        return True  # An existing, never-restored B2 deployment has no recovery journal.
    except (OSError, ContractViolation):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.SOURCE_NOT_APPROVED,
            retryable=False, trace_id='recovery/closed')
    try:
        state = json.loads(raw)
        require(state['schema_version'] == 'ds.recovery-state.v1' and state['state'] == 'opened'
                and state['target_identity'] == target_identity and state['environment'] in ('test', 'evaluation')
                and state['metrics']['passed'] is True and state['verification']['complete'] is True
                and state['verification']['opening_allowed'] is True, ReasonCode.SOURCE_NOT_APPROVED)
        receipt = AuditReceipt.from_wire(state['verification_receipt'])
        require(receipt.durability is Durability.DURABLE and receipt.chain_version is None,
                ReasonCode.SOURCE_NOT_APPROVED)
        if 'governance' in state:
            require(_governance_receipt(state['governance']) is not None, ReasonCode.SOURCE_NOT_APPROVED)
        return True
    except (KeyError, TypeError, ValueError):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.SOURCE_NOT_APPROVED,
            retryable=False, trace_id='recovery/closed')


class RecoveryJournal:
    def __init__(self, *, root, target_identity, code_version, environment, domain, service_identity, clock, limits):
        self.root = Path(root)
        info = self.root.lstat()
        require(self.root.is_absolute() and self.root == self.root.resolve() and stat.S_ISDIR(info.st_mode)
                and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700
                and environment in (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
        self.target_identity, self.code_version = target_identity, code_version
        self.environment, self.domain, self.service_identity = environment, domain, service_identity
        self.clock, self.limits = clock, limits

    def _allowed(self, context):
        require((context.actor_ref, context.environment, context.domain, context.role, context.purpose) ==
                (self.service_identity, self.environment, self.domain, Role.SERVICE, Purpose.STORAGE),
                ReasonCode.AUTHORIZATION_DENIED)

    def start(self, context):
        """Explicit outage declaration precedes choosing keys, restoring and verifying."""
        self._allowed(context)
        require(not any(self.root.iterdir()), ReasonCode.SOURCE_NOT_APPROVED)
        state = {'schema_version': 'ds.recovery-state.v1', 'run_ref': 'recovery/' + uuid4().hex,
                 'state': 'closed', 'environment': self.environment.value, 'domain': self.domain,
                 'target_identity': self.target_identity, 'code_version': self.code_version,
                 'outage_at': self.clock().isoformat(), 'stages': {}}
        self.save(state, context)
        return state['run_ref']

    def read(self, context):
        self._allowed(context)
        state = json.loads(_read(self.root / STATE_FILE, self.limits.max_json_bytes))
        require(type(state) is dict and state.get('schema_version') == 'ds.recovery-state.v1'
                and state.get('target_identity') == self.target_identity and state.get('code_version') == self.code_version
                and state.get('environment') == self.environment.value and state.get('domain') == self.domain
                and state.get('state') in ('closed', 'restoring', 'restored', 'verified', 'opened'),
                ReasonCode.SOURCE_NOT_APPROVED)
        if 'governance' in state:
            _governance_receipt(state['governance'])
        return state

    def save(self, state, context):
        self._allowed(context)
        encoded = json.dumps(state, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
        require(len(encoded) <= self.limits.max_json_bytes, ReasonCode.LIMIT_EXCEEDED)
        partial = self.root / (STATE_FILE + '.partial')
        with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        partial.rename(self.root / STATE_FILE)
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def proof(self, context):
        state = self.read(context)
        require(state['state'] in ('verified', 'opened'), ReasonCode.SOURCE_NOT_APPROVED)
        return {'path': str(self.root / STATE_FILE),
                'sha256': hashlib.sha256(_read(self.root / STATE_FILE, self.limits.max_json_bytes)).hexdigest()}


class VerifiedRecoveryPoint:
    """B pins a local completed proof; callers supply only the exact owner projection."""
    def __init__(self, *, path, sha256, source_identity, code_version, environment, domain, limits):
        self.path = Path(path)
        info = self.path.parent.stat()
        require(self.path.is_absolute() and self.path == self.path.resolve()
                and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                ReasonCode.SOURCE_NOT_APPROVED)
        digest(sha256)
        self.sha256, self.source_identity, self.code_version = sha256, source_identity, code_version
        self.environment, self.domain, self.limits = environment, domain, limits

    def __call__(self, principal):
        try:
            require(principal.environment is self.environment and principal.domain == self.domain
                    and principal.source_version == '1' and principal.source_hash is not None,
                    ReasonCode.AUTHORIZATION_DENIED)
            raw = _read(self.path, self.limits.max_json_bytes)
            require(hashlib.sha256(raw).hexdigest() == self.sha256, ReasonCode.HASH_MISMATCH)
            state = json.loads(raw)
            require(state['schema_version'] == 'ds.recovery-state.v1' and state['state'] in ('verified', 'opened')
                    and state['environment'] == self.environment.value and state['domain'] == self.domain
                    and state['code_version'] == self.code_version and state['verification']['complete'] is True
                    and state['restoration']['full_inventory']['source_identity'] == self.source_identity
                    and state['verification']['governance'].get(principal.source_ref) == principal.source_hash,
                    ReasonCode.SOURCE_NOT_APPROVED)
            receipt = AuditReceipt.from_wire(state['verification_receipt'])
            require(receipt.durability is Durability.DURABLE and receipt.chain_version is None,
                    ReasonCode.SOURCE_NOT_APPROVED)
            return receipt
        except ContractViolation as error:
            code = error.code
        except (OSError, ValueError, TypeError, KeyError):
            code = ReasonCode.SOURCE_NOT_APPROVED
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
            retryable=False, trace_id=principal.trace_id)
