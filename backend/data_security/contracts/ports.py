"""Narrow boundaries only. No default adapters, factories, or runtime singletons."""
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import ClassVar, Protocol, Self, TypeVar

from .crypto import CipherEnvelope, KeyReference, ObjectContext, SecretMaterial
from .enums import Durability, KeyPurpose, ReasonCode
from .events import AuditReceipt, ProtectionError, SecurityEvent
from .execution import (DeliveryReceipt, ExecutionBinding, ProtectedResult, QuotaReceipt,
                        RevealGrant)
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
    def record(self, event: SecurityEvent, durability: Durability) -> AuditReceipt | ProtectionError: ...


class AuditSink(Protocol):
    def append(self, event: SecurityEvent, durability: Durability) -> AuditReceipt | ProtectionError: ...
    def verify(self, chain_ref: str) -> AuditReceipt | ProtectionError: ...
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


class SourcePlanAdapter(Protocol):
    def to_action_plan(self, source: SourceDocument, snapshot: TableSnapshot,
                       binding: PolicyBinding,
                       resolved_actions: tuple[ResolvedAction, ...]) -> ActionPlan | ProtectionError: ...


class Detect(Protocol):
    def __call__(self, payload: BoundedPayload, limits: Limits) -> tuple[Finding, ...] | ProtectionError: ...


# M6 specializes these type parameters to the existing export_risk DTOs. M0 must
# neither import that domain nor copy its request, decision, or authorization.
RiskRequest = TypeVar('RiskRequest', contravariant=True)
RiskDecision = TypeVar('RiskDecision', covariant=True)
RiskAuthorization = TypeVar('RiskAuthorization', covariant=True)


class RiskPort(Protocol[RiskRequest, RiskDecision, RiskAuthorization]):
    def decide(self, request: RiskRequest, binding: PolicyBinding) -> RiskDecision | ProtectionError: ...
    def issue(self, execution: ExecutionBinding) -> RiskAuthorization | ProtectionError: ...
    def recheck(self, execution: ExecutionBinding) -> RiskAuthorization | ProtectionError: ...


class QuotaPort(Protocol):
    def reserve(self, binding: ExecutionBinding) -> QuotaReceipt | ProtectionError: ...
    def require_active(self, binding: ExecutionBinding) -> QuotaReceipt | ProtectionError: ...
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
               context: ProtectionContext) -> StoredObject | ProtectionError: ...
    def restore(self, backup: StoredObject, context: ProtectionContext) -> AuditReceipt | ProtectionError: ...


class UnitOfWork(Protocol):
    def __enter__(self) -> Self: ...
    def commit(self) -> None: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 traceback: TracebackType | None) -> None: ...


class RevealRepository(Protocol):
    def consume(self, grant: RevealGrant, context: ProtectionContext,
                expected_version: str, at: datetime) -> RevealGrant | ProtectionError: ...


class ExportPort(Protocol):
    def execute(self, plan: ActionPlan, binding: ExecutionBinding,
                context: ProtectionContext) -> DeliveryReceipt | ProtectionError: ...


class RevealPort(Protocol):
    def reveal(self, grant: RevealGrant, context: ProtectionContext) -> BoundedPayload | ProtectionError: ...
