from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from .enums import (Algorithm, Category, Outlet, PolicyStatus, Purpose, ReasonCode,
                    Replacement, Role)
from .schema import DTO, MAX_TEXT_CHARS, content_hash, digest, reference, require


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AlgorithmSpec(DTO):
    SCHEMA: ClassVar[str] = 'ds.algorithm-spec.v1'
    algorithm: Algorithm
    version: str
    replacement: Replacement | None
    keep_prefix: int | None
    keep_suffix: int | None
    mask_symbol: str | None
    max_length: int | None
    ipv4_prefix: int | None
    pseudonym_bits: int | None
    key_ref: str | None

    def __post_init__(self):
        DTO.__post_init__(self)
        require(self.version == 'v1', ReasonCode.UNKNOWN_SCHEMA)
        parameters = ('replacement', 'keep_prefix', 'keep_suffix', 'mask_symbol',
                      'max_length', 'ipv4_prefix', 'pseudonym_bits', 'key_ref')
        allowed = {
            Algorithm.DROP: (), Algorithm.REPLACE: ('replacement',),
            Algorithm.MASK: ('keep_prefix', 'keep_suffix', 'mask_symbol'),
            Algorithm.TRUNCATE: ('max_length',), Algorithm.HMAC: ('key_ref',),
            Algorithm.PSEUDONYM: ('key_ref', 'pseudonym_bits'),
            Algorithm.GENERALIZE: ('ipv4_prefix',),
        }[self.algorithm]
        require(all((getattr(self, key) is not None) == (key in allowed) for key in parameters))
        if self.algorithm is Algorithm.MASK:
            require(0 <= self.keep_prefix <= 64 and 0 <= self.keep_suffix <= 64)
            require(self.mask_symbol in ('*', '•'))
        if self.max_length is not None:
            require(0 < self.max_length <= MAX_TEXT_CHARS, ReasonCode.LIMIT_EXCEEDED)
        if self.ipv4_prefix is not None:
            require(self.ipv4_prefix == 24)
        if self.pseudonym_bits is not None:
            require(128 <= self.pseudonym_bits <= 256 and self.pseudonym_bits % 8 == 0)
        if self.key_ref is not None:
            reference(self.key_ref)
            prefix = 'mask-link/' if self.algorithm is Algorithm.HMAC else 'mask-pseudonym/'
            require(self.key_ref.startswith(prefix) and len(self.key_ref.split('/')) == 2)
            reference(self.key_ref.split('/')[-1], maximum=32)

    def validate_category(self, category):
        require(type(category) is Category, ReasonCode.INVALID_TYPE)
        # Truncation may follow protection but cannot be its primary action.
        require(self.algorithm is not Algorithm.TRUNCATE)
        if category in (Category.CARD, Category.SECRET):
            require(self.algorithm not in (Algorithm.MASK, Algorithm.GENERALIZE))
        if self.algorithm is Algorithm.GENERALIZE:
            require(category is Category.IPV4)
        if category is Category.SECRET:
            require(self.algorithm in (Algorithm.DROP, Algorithm.REPLACE))


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Approval(DTO):
    SCHEMA: ClassVar[str] = 'ds.approval.v1'
    approval_ref: str
    requested_by: str
    approved_by: str
    approved_at: datetime
    content_hash: str

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.approval_ref, self.requested_by, self.approved_by):
            reference(value)
        require(self.requested_by != self.approved_by)
        digest(self.content_hash)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class TeachingException(DTO):
    SCHEMA: ClassVar[str] = 'ds.teaching-exception.v1'
    source_ref: str
    source_version: str
    source_hash: str
    field_refs: tuple[str, ...]
    category: Category
    outlet: Outlet
    purpose: Purpose
    expires_at: datetime
    approval: Approval

    def content(self):
        return {name: getattr(self, name) for name in ('schema_version', 'source_ref', 'source_version',
                'source_hash', 'field_refs', 'category', 'outlet', 'purpose', 'expires_at')}

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.source_ref, self.source_version, *self.field_refs):
            reference(value)
        require(0 < len(self.field_refs) <= 1024 and len(set(self.field_refs)) == len(self.field_refs))
        digest(self.source_hash)
        # Fake flags remain the existing CTF domain's rule, never a new detector.
        require(self.category is Category.IPV4 and self.purpose is Purpose.TEACHING)
        require(self.expires_at > self.approval.approved_at)
        require(self.approval.content_hash == content_hash(self.content()), ReasonCode.HASH_MISMATCH)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class PolicyRule(DTO):
    SCHEMA: ClassVar[str] = 'ds.policy-rule.v1'
    category: Category
    outlet: Outlet
    role: Role
    purpose: Purpose
    action: AlgorithmSpec

    def __post_init__(self):
        DTO.__post_init__(self)
        self.action.validate_category(self.category)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class PolicySnapshot(DTO):
    SCHEMA: ClassVar[str] = 'ds.policy-snapshot.v1'
    version: str
    status: PolicyStatus
    content_hash: str
    rules: tuple[PolicyRule, ...]
    teaching_exceptions: tuple[TeachingException, ...]
    effective_at: datetime
    expires_at: datetime
    approval: Approval | None

    def content(self):
        return {name: getattr(self, name) for name in ('schema_version', 'version', 'rules',
                'teaching_exceptions', 'effective_at', 'expires_at')}

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.version)
        digest(self.content_hash)
        require(len(self.rules) <= 1024 and len(self.teaching_exceptions) <= 1024,
                ReasonCode.LIMIT_EXCEEDED)
        keys = {(r.category, r.outlet, r.role, r.purpose) for r in self.rules}
        require(len(keys) == len(self.rules))
        require(self.effective_at < self.expires_at)
        require(self.content_hash == content_hash(self.content()), ReasonCode.HASH_MISMATCH)
        if self.status is PolicyStatus.APPROVED:
            require(self.approval is not None and bool(self.rules), ReasonCode.POLICY_NOT_APPROVED)
        if self.approval is not None:
            require(self.approval.content_hash == self.content_hash, ReasonCode.HASH_MISMATCH)
            require(self.approval.approved_at <= self.effective_at)
        for exception in self.teaching_exceptions:
            require(exception.expires_at <= self.expires_at)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class PolicyBinding(DTO):
    SCHEMA: ClassVar[str] = 'ds.policy-binding.v1'
    protection_version: str
    protection_hash: str
    risk_version: str
    risk_hash: str
    contract_version: str

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.protection_version)
        reference(self.risk_version)
        digest(self.protection_hash)
        digest(self.risk_hash)
        require(self.contract_version == 'ds.m0.v1', ReasonCode.UNKNOWN_SCHEMA)
