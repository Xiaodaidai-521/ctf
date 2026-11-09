from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from .enums import (GrantState, Outcome, QuotaState, ReasonCode, RevealField,
                    ScanState, SourceFormat, Unit)
from .events import AuditReceipt
from .payloads import BoundedPayload, Coverage
from .plans import SourcePlanBinding, TableScope, Unresolved
from .policies import Approval, PolicyBinding
from .schema import DTO, content_hash, count, digest, reference, require


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ProtectedResult(DTO):
    SCHEMA: ClassVar[str] = 'ds.protected-result.v1'
    SENSITIVE: ClassVar[bool] = True
    SERVER_ONLY: ClassVar[bool] = True
    payload: BoundedPayload
    policy_binding: PolicyBinding
    coverage: Coverage
    protection_version: str
    trace_id: str

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.protection_version)
        reference(self.trace_id)
        require(self.coverage.failed == self.coverage.unknown == self.coverage.unscanned == 0,
                ReasonCode.SCOPE_INCOMPLETE)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ExecutionBinding(DTO):
    SCHEMA: ClassVar[str] = 'ds.execution-binding.v1'
    idempotency_key: str
    request_fingerprint: str
    request_id: str
    authorization_id: str
    decision_id: str
    asset_version: str
    execution_id: str
    reservation_id: str
    subject_ref: str
    domain_ref: str
    environment: str
    scope: TableScope
    quantity: int
    quantity_unit: Unit
    expires_at: datetime
    policy_binding: PolicyBinding

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.idempotency_key, self.request_id, self.authorization_id, self.decision_id,
                      self.asset_version, self.execution_id, self.reservation_id, self.subject_ref,
                      self.domain_ref):
            reference(value)
        digest(self.request_fingerprint)
        require(self.environment in ('test', 'evaluation', 'production'))
        count(self.quantity, 2**53 - 1)
        require(self.quantity > 0 and self.quantity_unit is Unit.RECORD)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class QuotaReceipt(DTO):
    SCHEMA: ClassVar[str] = 'ds.quota-receipt.v1'
    binding: ExecutionBinding
    state: QuotaState
    settled_amount: int | None
    observed_at: datetime
    evidence_ref: str

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.evidence_ref)
        if self.state is QuotaState.COMMITTED:
            require(self.settled_amount is not None)
            count(self.settled_amount, self.binding.quantity)
        else:
            require(self.settled_amount is None)

    @property
    def held_amount(self):
        return self.binding.quantity if self.state in (QuotaState.RESERVED, QuotaState.UNKNOWN) else 0


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class MaskReport(DTO):
    SCHEMA: ClassVar[str] = 'ds.mask-report.v1'
    SERVER_ONLY: ClassVar[bool] = True
    execution_id: str
    executor_ref: str
    asset_version: str
    source: SourcePlanBinding
    action_plan_hash: str
    input_hash: str
    output_hash: str | None
    ciphertext_hash: str | None
    policy_binding: PolicyBinding
    algorithm_versions: tuple[str, ...]
    coverage: Coverage
    hit_count: int
    excluded: tuple[Unresolved, ...]
    unresolved: tuple[Unresolved, ...]
    rescan_state: ScanState
    rescan_coverage: Coverage
    outcome: Outcome
    created_at: datetime
    report_hash: str

    def content(self):
        return {name: getattr(self, name) for name in (
            'schema_version', 'execution_id', 'executor_ref', 'asset_version', 'source',
            'action_plan_hash', 'input_hash', 'output_hash', 'ciphertext_hash', 'policy_binding',
            'algorithm_versions', 'coverage', 'hit_count', 'excluded', 'unresolved',
            'rescan_state', 'rescan_coverage', 'outcome', 'created_at')}

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.execution_id, self.executor_ref, self.asset_version, *self.algorithm_versions):
            reference(value)
        for value in (self.action_plan_hash, self.input_hash, self.report_hash):
            digest(value)
        for value in (self.output_hash, self.ciphertext_hash):
            if value is not None:
                digest(value)
        require(len(self.algorithm_versions) <= 16 and len(self.excluded) <= 10000 and
                len(self.unresolved) <= 10000, ReasonCode.LIMIT_EXCEEDED)
        count(self.hit_count)
        if self.outcome is Outcome.SUCCEEDED:
            require(self.output_hash is not None and not self.unresolved)
            require(self.rescan_state is ScanState.COMPLETE)
            for coverage in (self.coverage, self.rescan_coverage):
                require(coverage.failed == coverage.unknown == coverage.unscanned == 0,
                        ReasonCode.SCOPE_INCOMPLETE)
        else:
            require(self.output_hash is None and self.ciphertext_hash is None)
        require(self.report_hash == content_hash(self.content()), ReasonCode.HASH_MISMATCH)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class RevealGrant(DTO):
    SCHEMA: ClassVar[str] = 'ds.reveal-grant.v1'
    SERVER_ONLY: ClassVar[bool] = True
    grant_id: str
    subject_ref: str
    object_ref: str
    object_version: str
    fields: tuple[tuple[RevealField, str], ...]
    purpose_ref: str
    authorization_ref: str
    issued_at: datetime
    expires_at: datetime
    approval: Approval
    state: GrantState
    consumed_at: datetime | None
    revoked_at: datetime | None

    def approved_content(self):
        return {name: getattr(self, name) for name in ('schema_version', 'grant_id', 'subject_ref',
            'object_ref', 'object_version', 'fields', 'purpose_ref', 'authorization_ref',
            'issued_at', 'expires_at')}

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.grant_id, self.subject_ref, self.object_ref, self.object_version,
                      self.purpose_ref, self.authorization_ref):
            reference(value)
        require(0 < len(self.fields) <= 16 and len(set(self.fields)) == len(self.fields))
        for category, field_ref in self.fields:
            reference(field_ref)
        require(0 < (self.expires_at - self.issued_at).total_seconds() <= 900,
                ReasonCode.AUTHORIZATION_EXPIRED)
        require(self.approval.requested_by == self.subject_ref and
                self.approval.approved_at <= self.issued_at)
        require(self.approval.content_hash == content_hash(self.approved_content()), ReasonCode.HASH_MISMATCH)
        require((self.consumed_at is not None) == (self.state is GrantState.CONSUMED))
        require((self.revoked_at is not None) == (self.state is GrantState.REVOKED))
        if self.consumed_at is not None:
            require(self.issued_at <= self.consumed_at < self.expires_at)
        if self.revoked_at is not None:
            require(self.revoked_at >= self.issued_at)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DeliveryReceipt(DTO):
    SCHEMA: ClassVar[str] = 'ds.delivery-receipt.v1'
    binding: ExecutionBinding
    outcome: Outcome
    delivered_records: int | None
    evidence_ref: str
    audit: AuditReceipt

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.evidence_ref)
        if self.outcome is Outcome.SUCCEEDED:
            require(self.delivered_records is not None)
            count(self.delivered_records, self.binding.quantity)
        else:
            require(self.delivered_records is None)
