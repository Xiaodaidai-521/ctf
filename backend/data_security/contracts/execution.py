from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from .crypto import KeyReference
from .enums import (EventKind, GrantState, KeyPurpose, Outcome, PayloadKind, QuotaState, ReasonCode, RevealField,
                    ScanState, SourceFormat, Unit)
from .events import AuditReceipt, SecurityEvent
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
class QuotaRecoveryEvent(SecurityEvent):
    """One authorized recovery observation, with the authority's immutable receipt."""
    SCHEMA: ClassVar[str] = 'ds.quota-recovery-event.v1'
    operation: str
    authorization_ref: str
    quota: QuotaReceipt

    def __post_init__(self):
        SecurityEvent.__post_init__(self)
        reference(self.authorization_ref)
        require(self.operation in ('release', 'reconcile', 'unknown'))
        binding = self.quota.binding
        require(self.kind is EventKind.AUTHORIZATION and
                (self.object_ref, self.object_version, self.correlation_ref, self.policy_binding) ==
                (binding.reservation_id, binding.asset_version, binding.execution_id, binding.policy_binding))
        expected = {'release': QuotaState.RELEASED, 'reconcile': QuotaState.COMMITTED,
                    'unknown': QuotaState.UNKNOWN}[self.operation]
        require(self.quota.state is expected and
                (self.operation != 'reconcile' or self.quota.settled_amount == 0))
        require(self.outcome is (Outcome.UNKNOWN if self.operation == 'unknown' else Outcome.SUCCEEDED))
        require(self.counts == (('unknown', binding.quantity),) if self.operation == 'unknown'
                else self.counts == (('records', 0),))
        require(self.occurred_at >= self.quota.observed_at)
        require(not self.algorithm_versions and not self.key_versions and self.reason is None)


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
class ReportProof(DTO):
    """Untrusted wire receipt until its MAC and current owner bindings are verified."""
    SCHEMA: ClassVar[str] = 'ds.report-proof.v1'
    report_hash: str
    execution_hash: str
    context_hash: str
    key: KeyReference
    authentication: bytes

    def content(self):
        return dict(schema_version=self.schema_version, report_hash=self.report_hash,
                    execution_hash=self.execution_hash, context_hash=self.context_hash, key=self.key)

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.report_hash, self.execution_hash, self.context_hash):
            digest(value)
        require(self.key.purpose is KeyPurpose.AUDIT, ReasonCode.KEY_UNAVAILABLE)
        require(len(self.authentication) == 32, ReasonCode.REPORT_MISMATCH)


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
class RevealRequestRecord(DTO):
    """Server state; the reason is protected before the repository may store it."""
    SCHEMA: ClassVar[str] = 'ds.reveal-request-record.v1'
    SERVER_ONLY: ClassVar[bool] = True
    SENSITIVE: ClassVar[bool] = True
    request_ref: str
    subject_ref: str
    course_id: int | None
    object_ref: str
    object_version: str
    fields: tuple[tuple[RevealField, str], ...]
    purpose_ref: str
    reason: BoundedPayload
    requested_at: datetime
    state: str
    grant: RevealGrant | None
    decided_by: str | None
    decided_at: datetime | None
    decision_event_ref: str | None

    def authorization_content(self):
        # The protected reason is not a public low-entropy evidence digest.
        return {name: getattr(self, name) for name in (
            'schema_version', 'request_ref', 'subject_ref', 'course_id', 'object_ref',
            'object_version', 'fields', 'purpose_ref', 'requested_at', 'state',
            'grant', 'decided_by', 'decided_at')}

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.request_ref, self.subject_ref, self.object_ref, self.object_version,
                      self.purpose_ref):
            reference(value)
        if self.course_id is not None:
            count(self.course_id, 2**53 - 1)
            require(self.course_id > 0)
        require(0 < len(self.fields) <= 16)
        require(len({field_ref for category, field_ref in self.fields}) == len(self.fields),
                ReasonCode.DUPLICATE_FIELD)
        for category, field_ref in self.fields:
            reference(field_ref)
        require(self.reason.kind is PayloadKind.TEXT and bool(self.reason.text.strip()))
        require(self.state in ('pending', 'approved', 'rejected', 'consumed', 'revoked'))
        require((self.grant is not None) == (self.state in ('approved', 'consumed', 'revoked')))
        if self.state == 'pending':
            require(self.decided_by is self.decided_at is self.decision_event_ref is None)
        else:
            reference(self.decided_by)
            require(self.decided_at is not None and self.decided_at >= self.requested_at)
        if self.decision_event_ref is not None:
            digest(self.decision_event_ref)
        if self.grant is not None:
            require((self.grant.subject_ref, self.grant.object_ref, self.grant.object_version,
                     self.grant.fields, self.grant.purpose_ref) ==
                    (self.subject_ref, self.object_ref, self.object_version, self.fields, self.purpose_ref),
                    ReasonCode.AUTHORIZATION_DENIED)
            require(self.grant.state is {'approved': GrantState.ACTIVE, 'consumed': GrantState.CONSUMED,
                                         'revoked': GrantState.REVOKED}[self.state])
        if self.state == 'approved':
            require(self.decided_by == self.grant.approval.approved_by and
                    self.decided_at == self.grant.issued_at)


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
