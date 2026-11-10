from dataclasses import dataclass, fields
from datetime import datetime
from typing import ClassVar

from .crypto import KeyReference
from .enums import Durability, EventKind, KeyPurpose, KeyStatus, Outcome, ReasonCode
from .policies import PolicyBinding
from .schema import DTO, count, digest, reference, require


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ProtectionError(DTO):
    SCHEMA: ClassVar[str] = 'ds.protection-error.v1'
    code: ReasonCode
    retryable: bool
    trace_id: str

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.trace_id)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class SecurityEvent(DTO):
    SCHEMA: ClassVar[str] = 'ds.security-event.v1'
    event_id: str
    kind: EventKind
    actor_ref: str
    object_ref: str
    object_version: str
    outcome: Outcome
    occurred_at: datetime
    counts: tuple[tuple[str, int], ...]
    policy_binding: PolicyBinding
    algorithm_versions: tuple[str, ...]
    key_versions: tuple[str, ...]
    correlation_ref: str
    reason: ReasonCode | None

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.event_id, maximum=64)
        for value in (self.actor_ref, self.object_ref, self.object_version, self.correlation_ref,
                      *self.algorithm_versions, *self.key_versions):
            reference(value)
        allowed = {'hit', 'processed', 'excluded', 'failed', 'unknown', 'unscanned', 'records', 'bytes'}
        require(len(self.counts) <= len(allowed) and len({k for k, v in self.counts}) == len(self.counts))
        for name, value in self.counts:
            require(name in allowed)
            count(value, 2**53 - 1)
        require(len(self.algorithm_versions) <= 16 and len(self.key_versions) <= 16, ReasonCode.LIMIT_EXCEEDED)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class SecurityEventV2(SecurityEvent):
    """Owner-computed evidence digests, never a caller-supplied report body."""
    SCHEMA: ClassVar[str] = 'ds.security-event.v2'
    evidence_hashes: tuple[tuple[str, str], ...]

    def __post_init__(self):
        SecurityEvent.__post_init__(self)
        names = tuple(name for name, value in self.evidence_hashes)
        require(len(names) <= 3 and len(set(names)) == len(names))
        require(names == tuple(sorted(names)))
        for name, value in self.evidence_hashes:
            require(name in ('archive', 'ciphertext', 'report'))
            digest(value)
        if self.kind is EventKind.DELIVERY and self.outcome is Outcome.SUCCEEDED:
            require('report' in names and 'ciphertext' in names, ReasonCode.REPORT_MISMATCH)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AuditReceipt(DTO):
    SCHEMA: ClassVar[str] = 'ds.audit-receipt.v1'
    event_id: str
    durability: Durability
    stored_at: datetime
    chain_version: str | None
    entry_ref: str | None
    sequence: int | None
    entry_hash: str | None
    checkpoint_ref: str | None

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.event_id, maximum=64)
        ledger = (self.chain_version, self.entry_ref, self.sequence, self.entry_hash)
        if self.durability is Durability.DURABLE:
            require(all(value is None for value in ledger) and self.checkpoint_ref is None)
        else:
            require(all(value is not None for value in ledger))
            require(self.chain_version in ('v1', 'ds.audit.v2'), ReasonCode.UNKNOWN_SCHEMA)
            reference(self.entry_ref)
            count(self.sequence, 2**53 - 1)
            require(self.sequence > 0)
            digest(self.entry_hash)
            if self.checkpoint_ref is not None:
                reference(self.checkpoint_ref)
                require(self.chain_version != 'v1')


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AuditCheckpoint(DTO):
    SCHEMA: ClassVar[str] = 'ds.audit-checkpoint.v1'
    chain_identity: str
    receipt: AuditReceipt
    checkpointed_at: datetime
    key: KeyReference
    authentication: bytes

    def __post_init__(self):
        DTO.__post_init__(self)
        digest(self.chain_identity)
        require(self.receipt.durability is Durability.LEDGER_CONFIRMED and
                self.receipt.chain_version == 'ds.audit.v2' and self.receipt.checkpoint_ref is None)
        require(self.checkpointed_at >= self.receipt.stored_at)
        require(self.key.purpose is KeyPurpose.AUDIT and self.key.status is KeyStatus.ACTIVE)
        require(len(self.authentication) == 32)

    def content(self):
        return {field.name: getattr(self, field.name) for field in fields(self)
                if field.name != 'authentication'}
