"""M0 v1: immutable values and ports, without implementation or bootstrap."""
from .canary import CanarySeed
from .crypto import CipherEnvelope, KeyReference, ObjectContext, SecretMaterial
from .enums import (Algorithm, Category, Durability, Environment, EventKind, GrantState,
                    KeyPurpose, KeyStatus, Level, LocationKind, MediaType, Outcome,
                    Outlet, PayloadKind, PolicyStatus, Purpose, QuotaState, ReasonCode,
                    Replacement, RevealField, Role, ScanState, SourceFormat, SourceTrust, Unit)
from .events import AuditCheckpoint, AuditReceipt, ProtectionError, SecurityEvent, SecurityEventV2
from .execution import (DeliveryReceipt, ExecutionBinding, MaskReport, ProtectedResult,
                        QuotaReceipt, QuotaRecoveryEvent, ReportProof, RevealGrant, RevealRequestRecord)
from .payloads import (BASELINE_LIMITS, BoundedPayload, Coverage, Finding, Limits,
                       Location, Metric, ProtectionContext, TableCell, TableColumn, TableSnapshot)
from .plans import (ActionPlan, ResolvedAction, SheetScope, SourceDocument, SourcePlanBinding,
                    TableScope, Unresolved)
from .policies import (AlgorithmSpec, Approval, PolicyBinding, PolicyRule, PolicySnapshot,
                       TeachingException)
from .ports import (AIRequest, AIResponse, AuditPort, AuditSink, BackupPort, BackupRetentionRecord, CanaryCheckPort, CryptoPort,
                    Detect, EmbeddingResult, ExportPort, FileUploadOperation, KeyResolverPort, OfficialAIPort,
                    PolicyCatalogPort, PolicyRepository, PrivateStore, ProtectionPort,
                    QuotaPort, ReportRecord, ReportRepository, RevealPort, RevealRepository, RevealRequestRepository, RevealSource, RevealSourcePort, RiskPort,
                    SourcePlanAdapter, StoredObject, TableCodec, UnitOfWork)
from .schema import ContractViolation, DTO, FrozenJSON, canonical_bytes, content_hash

CONTRACT_VERSION = 'ds.m0.v1'
CONTRACT_TYPES = (
    Limits, ProtectionContext, BoundedPayload, Coverage, Metric, Location, Finding,
    TableColumn, TableCell, TableSnapshot, AlgorithmSpec, Approval, TeachingException,
    PolicyRule, PolicySnapshot, PolicyBinding, SourceDocument, SourcePlanBinding,
    SheetScope, TableScope, ResolvedAction, Unresolved, ActionPlan, KeyReference,
    ObjectContext, CipherEnvelope, ProtectionError, SecurityEvent, AuditReceipt,
    ProtectedResult, ExecutionBinding, QuotaReceipt, MaskReport, ReportProof, RevealGrant,
    DeliveryReceipt, AIRequest, AIResponse, EmbeddingResult, StoredObject, ReportRecord, SecurityEventV2,
    AuditCheckpoint, QuotaRecoveryEvent, CanarySeed, BackupRetentionRecord, FileUploadOperation, RevealSource,
    RevealRequestRecord,
)
PORT_TYPES = (
    ProtectionPort, CryptoPort, PolicyCatalogPort, PolicyRepository, KeyResolverPort,
    AuditPort, AuditSink, OfficialAIPort, TableCodec, SourcePlanAdapter, Detect,
    RiskPort, QuotaPort, PrivateStore, BackupPort, UnitOfWork, RevealRepository,
    ExportPort, RevealPort, ReportRepository, CanaryCheckPort, RevealSourcePort, RevealRequestRepository,
)
