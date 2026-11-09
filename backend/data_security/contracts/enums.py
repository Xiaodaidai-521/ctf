from enum import Enum


class Category(str, Enum):
    EMAIL = 'email_address'
    IPV4 = 'ip_address'
    CARD = 'payment_card_candidate'
    SECRET = 'secret_credential'


class Level(str, Enum):
    L1 = 'L1'
    L2 = 'L2'
    L3 = 'L3'


class Environment(str, Enum):
    TEST = 'test'
    EVALUATION = 'evaluation'
    PRODUCTION = 'production'


class Outlet(str, Enum):
    MODEL = 'model'
    EMBEDDING = 'embedding'
    LOG = 'log'
    AUDIT = 'audit'
    API = 'api'
    EXPORT = 'export'
    RAG = 'rag'


class Role(str, Enum):
    STUDENT = 'student'
    TEACHER = 'teacher'
    ADMIN = 'admin'
    SERVICE = 'service'


class Purpose(str, Enum):
    DISPLAY = 'display'
    TEACHING = 'teaching'
    ANALYSIS = 'analysis'
    DELIVERY = 'delivery'
    RETRIEVAL = 'retrieval'
    SECURITY_AUDIT = 'security_audit'
    STORAGE = 'storage'
    INVESTIGATION = 'investigation'


class PayloadKind(str, Enum):
    TEXT = 'text'
    JSON = 'json'
    BINARY = 'binary'


class MediaType(str, Enum):
    TEXT = 'text/plain'
    JSON = 'application/json'
    CSV = 'text/csv'
    XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    BINARY = 'application/octet-stream'


class Unit(str, Enum):
    TEXT = 'text'
    FIELD = 'field'
    CELL = 'cell'
    RECORD = 'record'
    OUTLET = 'outlet'


class LocationKind(str, Enum):
    TEXT_SPAN = 'text_span'
    JSON_FIELD = 'json_field'
    CELL_SPAN = 'cell_span'
    CELL = 'cell'
    COLUMN = 'column'


class Algorithm(str, Enum):
    DROP = 'drop'
    REPLACE = 'replace'
    MASK = 'mask'
    TRUNCATE = 'truncate'
    HMAC = 'hmac'
    PSEUDONYM = 'pseudonym'
    GENERALIZE = 'generalize'


class Replacement(str, Enum):
    EMAIL = '[EMAIL]'
    IPV4 = '[IPV4]'
    CARD = '[CARD]'
    SECRET = '[SECRET]'
    REDACTED = '[REDACTED]'


class PolicyStatus(str, Enum):
    DRAFT = 'draft'
    APPROVED = 'approved'
    RETIRED = 'retired'


class SourceFormat(str, Enum):
    MAINLINE1 = 'mainline1'
    COLUMN_V1 = 'controlled-export'


class SourceTrust(str, Enum):
    SYNTHETIC = 'synthetic'
    PRODUCTION = 'production'
    UNVERIFIED = 'unverified'


class KeyPurpose(str, Enum):
    DATA = 'enc-data'
    LINK = 'mask-link'
    PSEUDONYM = 'mask-pseudonym'
    INDEX = 'query-index'
    AUDIT = 'audit-auth'
    PROVIDER = 'provider'
    FRAMEWORK = 'framework-signing'
    AUTHORITY = 'export-authority'
    SHARE = 'share-pepper'
    BACKUP_PUBLIC = 'backup-recipient'
    BACKUP_PRIVATE = 'backup-identity'


class KeyStatus(str, Enum):
    ACTIVE = 'active-write'
    READ_ONLY = 'decrypt-or-verify-only'
    RETIRED = 'retired'


class Durability(str, Enum):
    DURABLE = 'durable'
    LEDGER_CONFIRMED = 'ledger-confirmed'


class EventKind(str, Enum):
    PROTECTION = 'protection'
    POLICY = 'policy'
    AUTHORIZATION = 'authorization'
    DELIVERY = 'delivery'
    REVEAL = 'reveal'
    KEY_REFERENCE = 'key-reference'
    BACKUP = 'backup'


class Outcome(str, Enum):
    SUCCEEDED = 'succeeded'
    DENIED = 'denied'
    FAILED = 'failed'
    UNKNOWN = 'unknown'


class ScanState(str, Enum):
    COMPLETE = 'complete'
    FAILED = 'failed'
    UNKNOWN = 'unknown'
    UNSCANNED = 'unscanned'


class QuotaState(str, Enum):
    RESERVED = 'reserved'
    COMMITTED = 'committed'
    RELEASED = 'released'
    UNKNOWN = 'unknown'


class GrantState(str, Enum):
    ACTIVE = 'active'
    CONSUMED = 'consumed'
    REVOKED = 'revoked'


class RevealField(str, Enum):
    EMAIL = 'email'
    CONVERSATION = 'conversation'
    EVIDENCE = 'evidence'
    REPORT = 'report'


class ReasonCode(str, Enum):
    INVALID_TYPE = 'INVALID_TYPE'
    MISSING_FIELD = 'MISSING_FIELD'
    UNKNOWN_FIELD = 'UNKNOWN_FIELD'
    UNKNOWN_SCHEMA = 'UNKNOWN_SCHEMA'
    INVALID_VALUE = 'INVALID_VALUE'
    INVALID_COORDINATE = 'INVALID_COORDINATE'
    LIMIT_EXCEEDED = 'LIMIT_EXCEEDED'
    HASH_MISMATCH = 'HASH_MISMATCH'
    DUPLICATE_FIELD = 'DUPLICATE_FIELD'
    TRUSTED_CONSTRUCTION_REQUIRED = 'TRUSTED_CONSTRUCTION_REQUIRED'
    SENSITIVE_SERIALIZATION_FORBIDDEN = 'SENSITIVE_SERIALIZATION_FORBIDDEN'
    POLICY_NOT_APPROVED = 'POLICY_NOT_APPROVED'
    SCOPE_INCOMPLETE = 'SCOPE_INCOMPLETE'
    KEY_UNAVAILABLE = 'KEY_UNAVAILABLE'
    CIPHERTEXT_INVALID = 'CIPHERTEXT_INVALID'
    REPORT_MISMATCH = 'REPORT_MISMATCH'
    AUTHORIZATION_EXPIRED = 'AUTHORIZATION_EXPIRED'
    AUTHORIZATION_DENIED = 'AUTHORIZATION_DENIED'
    SOURCE_NOT_APPROVED = 'SOURCE_NOT_APPROVED'
    DELIVERY_UNKNOWN = 'DELIVERY_UNKNOWN'
    IDEMPOTENCY_CONFLICT = 'IDEMPOTENCY_CONFLICT'
    UNSUPPORTED_FORMAT = 'UNSUPPORTED_FORMAT'
    AUDIT_UNAVAILABLE = 'AUDIT_UNAVAILABLE'
    PROVIDER_UNAVAILABLE = 'PROVIDER_UNAVAILABLE'
    MATCHED_FORMAT = 'MATCHED_FORMAT'
    MATCHED_CONTEXT = 'MATCHED_CONTEXT'
    UNSUPPORTED_SCOPE = 'UNSUPPORTED_SCOPE'
