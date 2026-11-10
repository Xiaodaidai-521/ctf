"""Narrow boundaries only. No default adapters, factories, or runtime singletons."""
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import ClassVar, Protocol, Self, TypeVar

from .crypto import CipherEnvelope, KeyReference, ObjectContext, SecretMaterial
from .enums import Durability, KeyPurpose, ReasonCode
from .events import AuditReceipt, ProtectionError, SecurityEvent, SecurityEventV2
from .execution import (DeliveryReceipt, ExecutionBinding, MaskReport, ProtectedResult, QuotaReceipt,
                        QuotaRecoveryEvent, ReportProof, RevealGrant, RevealRequestRecord)
from .payloads import BoundedPayload, Finding, Limits, ProtectionContext, TableSnapshot
from .plans import ActionPlan, ResolvedAction, SourceDocument
from .policies import Approval, PolicyBinding, PolicySnapshot
from .schema import DTO, count, digest, reference, require


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AIRequest(DTO):
    SCHEMA: ClassVar[str] = 'ds.ai-request.v1'
    SENSITIVE: ClassVar[bool] = True
    endpoint_ref: str
    model_ref: str
    content: BoundedPayload
    output_token_limit: int
    temperature: float

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.endpoint_ref)
        reference(self.model_ref)
        require(0 < self.output_token_limit <= 8192 and 0 <= self.temperature <= 2,
                ReasonCode.LIMIT_EXCEEDED)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AIResponse(DTO):
    SCHEMA: ClassVar[str] = 'ds.ai-response.v1'
    SENSITIVE: ClassVar[bool] = True
    content: BoundedPayload
    endpoint_ref: str
    model_ref: str
    input_tokens: int
    output_tokens: int
    trace_id: str

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.endpoint_ref, self.model_ref, self.trace_id):
            reference(value)
        count(self.input_tokens, 2**31 - 1)
        count(self.output_tokens, 8192)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EmbeddingResult(DTO):
    SCHEMA: ClassVar[str] = 'ds.embedding-result.v1'
    SENSITIVE: ClassVar[bool] = True
    vectors: tuple[tuple[float, ...], ...]
    endpoint_ref: str
    model_ref: str
    trace_id: str

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.endpoint_ref, self.model_ref, self.trace_id):
            reference(value)
        require(0 < len(self.vectors) <= 1024, ReasonCode.LIMIT_EXCEEDED)
        dimensions = {len(vector) for vector in self.vectors}
        require(len(dimensions) == 1 and 0 < next(iter(dimensions)) <= 8192)
        require(sum(map(len, self.vectors)) <= 100000, ReasonCode.LIMIT_EXCEEDED)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class StoredObject(DTO):
    SCHEMA: ClassVar[str] = 'ds.stored-object.v1'
    object_ref: str
    version: str
    ciphertext_hash: str
    size_bytes: int
    state: str

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.object_ref)
        reference(self.version)
        digest(self.ciphertext_hash)
        count(self.size_bytes, 2**53 - 1)
        require(self.state in ('candidate', 'verified', 'published'))


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class FileUploadOperation(DTO):
    """A retained upload intention, not a download grant or proof of zero effects."""
    SCHEMA: ClassVar[str] = 'ds.file-upload-operation.v1'
    SERVER_ONLY: ClassVar[bool] = True
    operation_ref: str
    actor_ref: str
    scope_ref: str
    request_hash: str
    object_uuid: str
    field_refs: tuple[str, ...]
    state: str
    result_ref: str | None

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.operation_ref, self.actor_ref, self.scope_ref, self.object_uuid, *self.field_refs):
            reference(value)
        digest(self.request_hash)
        require(0 < len(self.field_refs) <= 2 and len(set(self.field_refs)) == len(self.field_refs))
        require(self.state in ('preparing', 'prepared', 'committed', 'aborted', 'retired', 'cleaned'))
        if self.result_ref is not None:
            reference(self.result_ref)
        require(self.state not in ('committed', 'retired') or self.result_ref is not None)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class BackupRetentionRecord(DTO):
    """Controlled local registration, not a claim of successful offline recovery."""
    SCHEMA: ClassVar[str] = 'ds.backup-retention-record.v1'
    SERVER_ONLY: ClassVar[bool] = True
    backup: StoredObject
    created_at: datetime
    cadence: str
    files_hash: str
    files_size: int

    def __post_init__(self):
        DTO.__post_init__(self)
        require(self.backup.version == 'v2' and self.backup.state == 'verified')
        require(self.cadence in ('daily', 'weekly'))
        digest(self.files_hash)
        count(self.files_size, 2**53 - 1)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ReportRecord(DTO):
    """Owner record contents; loading still requires proof and current authorization checks."""
    SCHEMA: ClassVar[str] = 'ds.report-record.v1'
    SERVER_ONLY: ClassVar[bool] = True
    SENSITIVE: ClassVar[bool] = True
    binding: ExecutionBinding
    plan: ActionPlan
    context: ObjectContext
    stored: StoredObject
    report: MaskReport
    proof: ReportProof


class ReportRepository(Protocol):
    def begin(self, plan: ActionPlan, binding: ExecutionBinding,
              context: ObjectContext) -> bool | ProtectionError: ...
    def abort(self, binding: ExecutionBinding) -> DeliveryReceipt | None | ProtectionError: ...
    def put(self, record: ReportRecord) -> ReportRecord | ProtectionError: ...
    def read(self, binding: ExecutionBinding) -> ReportRecord | None | ProtectionError: ...
    def delivery(self, binding: ExecutionBinding) -> DeliveryReceipt | None | ProtectionError: ...
    def lock_delivery(self, binding: ExecutionBinding,
                      record_hash: str) -> DeliveryReceipt | None | ProtectionError: ...
    def record_delivery(self, receipt: DeliveryReceipt) -> DeliveryReceipt | ProtectionError: ...


class CanaryCheckPort(Protocol):
    def check(self, *, payload: BoundedPayload | TableSnapshot,
              context: ProtectionContext) -> tuple[AuditReceipt, ...] | ProtectionError: ...


class ProtectionPort(Protocol):
    def protect(self, payload: BoundedPayload, context: ProtectionContext,
                policy_binding: PolicyBinding) -> ProtectedResult | ProtectionError: ...


class CryptoPort(Protocol):
    def seal(self, data: BoundedPayload, object_context: ObjectContext,
             key_ref: KeyReference) -> CipherEnvelope | ProtectionError: ...
    def open(self, envelope: CipherEnvelope, object_context: ObjectContext,
             key_ref: KeyReference) -> BoundedPayload | ProtectionError: ...
    def blind_index(self, data: BoundedPayload, object_context: ObjectContext,
                    key_ref: KeyReference) -> bytes | ProtectionError: ...
    def authenticate(self, metadata: bytes, object_context: ObjectContext,
                     key_ref: KeyReference) -> bytes | ProtectionError: ...
    def verify_authentication(self, metadata: bytes, authentication: bytes,
                              object_context: ObjectContext,
                              key_ref: KeyReference) -> bool | ProtectionError: ...


class PolicyCatalogPort(Protocol):
    def snapshot(self, binding: PolicyBinding) -> PolicySnapshot | ProtectionError: ...
    def approve(self, snapshot: PolicySnapshot, approval: Approval,
                context: ProtectionContext) -> PolicySnapshot | ProtectionError: ...
    def retire(self, binding: PolicyBinding,
               context: ProtectionContext) -> PolicySnapshot | ProtectionError: ...


class PolicyRepository(Protocol):
    def read(self, binding: PolicyBinding) -> PolicySnapshot | ProtectionError: ...
    def put(self, snapshot: PolicySnapshot, expected_version: str | None) -> bool | ProtectionError: ...


class KeyResolverPort(Protocol):
    def resolve(self, key_ref: KeyReference, purpose: KeyPurpose,
                service_identity: str) -> SecretMaterial | ProtectionError: ...


class AuditPort(Protocol):
    def record(self, event: SecurityEvent | SecurityEventV2 | QuotaRecoveryEvent, durability: Durability) -> AuditReceipt | ProtectionError: ...


class AuditSink(Protocol):
    def append(self, event: SecurityEvent | SecurityEventV2 | QuotaRecoveryEvent, durability: Durability) -> AuditReceipt | ProtectionError: ...
    def verify(self, chain_ref: str) -> AuditReceipt | ProtectionError: ...
    def read_authenticated(self, event_id: str) -> SecurityEventV2 | QuotaRecoveryEvent | ProtectionError: ...
    def checkpoint(self, chain_ref: str) -> AuditReceipt | ProtectionError: ...


class OfficialAIPort(Protocol):
    def chat(self, request: AIRequest, context: ProtectionContext,
             binding: PolicyBinding) -> AIResponse | ProtectionError: ...
    def stream(self, request: AIRequest, context: ProtectionContext,
               binding: PolicyBinding) -> Iterator[AIResponse | ProtectionError]: ...
    def embed(self, request: AIRequest, context: ProtectionContext,
              binding: PolicyBinding) -> EmbeddingResult | ProtectionError: ...


class TableCodec(Protocol):
    def parse(self, payload: BoundedPayload, limits: Limits) -> TableSnapshot | ProtectionError: ...
    def serialize(self, snapshot: TableSnapshot, limits: Limits) -> BoundedPayload | ProtectionError: ...
    def delivery_metadata(self, snapshot: TableSnapshot,
                          limits: Limits) -> BoundedPayload | ProtectionError: ...


class SourcePlanAdapter(Protocol):
    def to_action_plan(self, source: SourceDocument, snapshot: TableSnapshot,
                       binding: PolicyBinding,
                       resolved_actions: tuple[ResolvedAction, ...]) -> ActionPlan | ProtectionError: ...


class Detect(Protocol):
    def __call__(self, payload: BoundedPayload, limits: Limits) -> tuple[Finding, ...] | ProtectionError: ...


# M6 uses the existing export_risk request/authorization DTOs and an opaque
# persisted decision reference. M0 neither imports that domain nor copies its models.
RiskRequest = TypeVar('RiskRequest', contravariant=True)
RiskDecision = TypeVar('RiskDecision', covariant=True)
RiskAuthorization = TypeVar('RiskAuthorization', covariant=True)


class RiskPort(Protocol[RiskRequest, RiskDecision, RiskAuthorization]):
    def decide(self, request: RiskRequest, binding: PolicyBinding) -> RiskDecision | ProtectionError: ...
    def issue(self, execution: ExecutionBinding) -> RiskAuthorization | ProtectionError: ...
    def recheck(self, execution: ExecutionBinding) -> RiskAuthorization | ProtectionError: ...
    def recheck_delivered(self, execution: ExecutionBinding) -> bool | ProtectionError: ...
    def consume(self, execution: ExecutionBinding) -> RiskAuthorization | ProtectionError: ...


class QuotaPort(Protocol):
    def reserve(self, binding: ExecutionBinding) -> QuotaReceipt | ProtectionError: ...
    def require_active(self, binding: ExecutionBinding) -> QuotaReceipt | ProtectionError: ...
    def read_committed(self, binding: ExecutionBinding) -> QuotaReceipt | ProtectionError:
        """Read the original committed receipt without renewing or settling the binding."""
        ...
    def commit(self, binding: ExecutionBinding, delivered: int) -> QuotaReceipt | ProtectionError: ...
    def release(self, binding: ExecutionBinding, no_delivery_evidence: str) -> QuotaReceipt | ProtectionError: ...
    def reconcile(self, binding: ExecutionBinding, delivered: int | None,
                  evidence_ref: str) -> QuotaReceipt | ProtectionError: ...


class PrivateStore(Protocol):
    def write_candidate(self, envelope: CipherEnvelope,
                        context: ObjectContext) -> StoredObject | ProtectionError: ...
    def verify(self, candidate: StoredObject, context: ObjectContext) -> StoredObject | ProtectionError: ...
    def publish(self, candidate: StoredObject, context: ObjectContext) -> StoredObject | ProtectionError: ...
    def read(self, stored: StoredObject, context: ObjectContext) -> CipherEnvelope | ProtectionError: ...


class BackupPort(Protocol):
    def create(self, snapshot_ref: str, recipient: KeyReference,
               context: ProtectionContext, *, cadence: str | None = None) -> StoredObject | ProtectionError: ...
    def restore(self, backup: StoredObject, context: ProtectionContext) -> AuditReceipt | ProtectionError: ...
    def retention_inventory(self, context: ProtectionContext, limits: Limits
                            ) -> tuple[BackupRetentionRecord, ...] | ProtectionError: ...
    def retire(self, record: BackupRetentionRecord,
               context: ProtectionContext) -> AuditReceipt | ProtectionError: ...


class UnitOfWork(Protocol):
    def __enter__(self) -> Self: ...
    def commit(self) -> None: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 traceback: TracebackType | None) -> None: ...


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class RevealSource(DTO):
    """Locked owner ciphertexts with their original, field-specific storage AAD."""
    SCHEMA: ClassVar[str] = 'ds.reveal-source.v1'
    SERVER_ONLY: ClassVar[bool] = True
    SENSITIVE: ClassVar[bool] = True
    object_ref: str
    object_version: str
    fields: tuple[tuple[ObjectContext, CipherEnvelope], ...]

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.object_ref)
        reference(self.object_version)
        require(0 < len(self.fields) <= 16)
        require(len({context.field_ref for context, envelope in self.fields}) == len(self.fields),
                ReasonCode.DUPLICATE_FIELD)
        require(all(context.object_uuid == self.object_ref for context, envelope in self.fields),
                ReasonCode.AUTHORIZATION_DENIED)


class RevealRepository(Protocol):
    def consume(self, grant: RevealGrant, context: ProtectionContext,
                expected_version: str, at: datetime) -> RevealGrant | ProtectionError: ...


class RevealSourcePort(Protocol):
    def read(self, grant: RevealGrant, context: ProtectionContext) -> RevealSource | ProtectionError:
        """Load only after consume, under the same owner UnitOfWork; never decrypt."""
        ...


class RevealRequestRepository(Protocol):
    def submit(self, record: RevealRequestRecord,
               context: ProtectionContext) -> RevealRequestRecord | ProtectionError: ...
    def lock(self, request_ref: str, context: ProtectionContext,
             operation: str) -> RevealRequestRecord | ProtectionError: ...
    def put(self, record: RevealRequestRecord,
            context: ProtectionContext) -> RevealRequestRecord | ProtectionError: ...
    def approved(self, request_ref: str,
                 context: ProtectionContext) -> RevealRequestRecord | ProtectionError: ...
    def list(self, context: ProtectionContext, *, offset: int,
             limit: int) -> tuple[RevealRequestRecord, ...] | ProtectionError: ...


class ExportPort(Protocol):
    def execute(self, plan: ActionPlan, binding: ExecutionBinding,
                context: ProtectionContext) -> DeliveryReceipt | ProtectionError: ...


class RevealPort(Protocol):
    def reveal(self, grant: RevealGrant, context: ProtectionContext) -> BoundedPayload | ProtectionError: ...
