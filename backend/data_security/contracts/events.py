from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from .enums import Durability, EventKind, Outcome, ReasonCode
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
