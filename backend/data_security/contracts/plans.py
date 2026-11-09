from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from .enums import (Algorithm, Category, LocationKind, ReasonCode, SourceFormat,
                    SourceTrust)
from .payloads import BASELINE_LIMITS, Limits, Location, TableSnapshot
from .policies import AlgorithmSpec, Approval, PolicyBinding
from .schema import DTO, FrozenJSON, content_hash, digest, reference, require


def source_digest(value, source_format):
    if source_format is SourceFormat.MAINLINE1:
        require(type(value) is str and value.startswith('sha256:'))
        digest(value[7:])
    else:
        digest(value)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class SourceDocument(DTO):
    """Opaque bounded original; only M8 may interpret its legacy domain schema."""
    SCHEMA: ClassVar[str] = 'ds.source-document.v1'
    SENSITIVE: ClassVar[bool] = True
    source_format: SourceFormat
    source_version: str
    document: FrozenJSON

    def __post_init__(self):
        DTO.__post_init__(self)
        value = self.document.to_value()
        require(type(value) is dict, ReasonCode.INVALID_TYPE)
        if self.source_format is SourceFormat.MAINLINE1:
            require(self.source_version == 'mainline1.proposed.v1', ReasonCode.UNKNOWN_SCHEMA)
            require(type(value.get('meta')) is dict and
                    value['meta'].get('schema_version') == self.source_version, ReasonCode.UNKNOWN_SCHEMA)
        else:
            require(self.source_version == '1' and value.get('version') == '1', ReasonCode.UNKNOWN_SCHEMA)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class SourcePlanBinding(DTO):
    """Reference to retained owner evidence, not proof of its approval or freshness."""
    SCHEMA: ClassVar[str] = 'ds.source-plan-binding.v1'
    source_format: SourceFormat
    source_version: str
    source_plan_hash: str
    source_record_ref: str
    source_record_version: str
    source_trust: SourceTrust
    provenance_ref: str | None
    approval_basis_ref: str | None
    approval_basis_version: str | None
    source_state: str
    source_environment: str
    source_domain: str
    evaluation_ref: str | None
    scope_hash: str
    parser_version: str | None
    parser_config_hash: str | None
    requirements_hash: str | None
    operation_contract_version: str | None

    def __post_init__(self):
        DTO.__post_init__(self)
        source_digest(self.source_plan_hash, self.source_format)
        source_digest(self.scope_hash, self.source_format)
        for value in (self.source_record_ref, self.source_record_version, self.source_domain):
            reference(value)
        for value in (self.provenance_ref, self.approval_basis_ref, self.approval_basis_version,
                      self.evaluation_ref, self.parser_version, self.operation_contract_version):
            if value is not None:
                reference(value)
        require((self.approval_basis_ref is None) == (self.approval_basis_version is None))
        require(self.source_environment in ('development', 'test', 'evaluation', 'production'))
        require(self.source_trust is SourceTrust.UNVERIFIED or self.provenance_ref is not None)
        if self.source_format is SourceFormat.MAINLINE1:
            require(self.source_version == 'mainline1.proposed.v1', ReasonCode.UNKNOWN_SCHEMA)
            require(self.source_state in ('ready', 'partial', 'invalid'))
            require(self.parser_version is not None and self.operation_contract_version is not None)
            source_digest(self.parser_config_hash, self.source_format)
            source_digest(self.requirements_hash, self.source_format)
        else:
            require(self.source_version == '1', ReasonCode.UNKNOWN_SCHEMA)
            # Legacy v1 has no approved/ready state of its own.
            require(self.source_state == 'not-declared')
            require(all(value is None for value in (self.parser_version, self.parser_config_hash,
                    self.requirements_hash, self.operation_contract_version)))


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class SheetScope(DTO):
    SCHEMA: ClassVar[str] = 'ds.sheet-scope.v1'
    sheet_id: str
    column_ids: tuple[str, ...]
    row_ranges: tuple[tuple[int, int], ...]
    includes_header: bool

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.sheet_id)
        require(0 < len(self.column_ids) <= 512 and len(set(self.column_ids)) == len(self.column_ids))
        for value in self.column_ids:
            reference(value)
        require(0 < len(self.row_ranges) <= 1024, ReasonCode.LIMIT_EXCEEDED)
        previous_end = -1
        for start, end in self.row_ranges:
            require(1 <= start <= end <= BASELINE_LIMITS.max_rows and start > previous_end + 1,
                    ReasonCode.INVALID_COORDINATE)
            previous_end = end

    def contains(self, location):
        require(type(location) is Location, ReasonCode.INVALID_TYPE)
        return (location.sheet_id == self.sheet_id and location.column_id in self.column_ids and
                (location.kind is LocationKind.COLUMN or any(
                    start <= location.source_row <= end for start, end in self.row_ranges
                    if location.source_row is not None)))


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class TableScope(DTO):
    SCHEMA: ClassVar[str] = 'ds.table-scope.v1'
    sheets: tuple[SheetScope, ...]
    coordinate_version: str

    def __post_init__(self):
        DTO.__post_init__(self)
        require(0 < len(self.sheets) <= 16 and len({s.sheet_id for s in self.sheets}) == len(self.sheets))
        require(self.coordinate_version == 'source-codepoint-half-open.v1', ReasonCode.UNKNOWN_SCHEMA)

    def contains(self, location):
        return any(sheet.contains(location) for sheet in self.sheets)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ResolvedAction(DTO):
    SCHEMA: ClassVar[str] = 'ds.resolved-action.v1'
    action_id: str
    source_operation_ref: str
    location: Location
    category: Category
    algorithm: AlgorithmSpec
    finding_refs: tuple[str, ...]
    requirement_refs: tuple[str, ...]

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.action_id, self.source_operation_ref, *self.finding_refs, *self.requirement_refs):
            reference(value)
        require(len(self.finding_refs) <= 1024 and len(self.requirement_refs) <= 1024,
                ReasonCode.LIMIT_EXCEEDED)
        require(len(set(self.finding_refs)) == len(self.finding_refs) and
                len(set(self.requirement_refs)) == len(self.requirement_refs))
        self.algorithm.validate_category(self.category)
        if self.location.kind is LocationKind.COLUMN:
            require(self.algorithm.algorithm is Algorithm.DROP)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Unresolved(DTO):
    SCHEMA: ClassVar[str] = 'ds.unresolved.v1'
    location: Location | None
    reason: ReasonCode
    source_ref: str

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.source_ref)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ActionPlan(DTO):
    SCHEMA: ClassVar[str] = 'ds.action-plan.v1'
    plan_id: str
    asset_version: str
    input_hash: str
    scope: TableScope
    actions: tuple[ResolvedAction, ...]
    policy_binding: PolicyBinding
    unresolved: tuple[Unresolved, ...]
    source: SourcePlanBinding
    adapter_version: str
    plan_hash: str
    approval: Approval | None
    created_at: datetime
    expires_at: datetime
    limits: Limits

    def content(self):
        return {name: getattr(self, name) for name in ('schema_version', 'plan_id', 'asset_version',
                'input_hash', 'scope', 'actions', 'policy_binding', 'unresolved', 'source',
                'adapter_version', 'created_at', 'expires_at', 'limits')}

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.plan_id, self.asset_version, self.adapter_version):
            reference(value)
        digest(self.input_hash)
        digest(self.plan_hash)
        require(self.created_at < self.expires_at)
        require(len(self.actions) <= self.limits.max_actions and
                len(self.unresolved) <= self.limits.max_findings, ReasonCode.LIMIT_EXCEEDED)
        require(len({action.action_id for action in self.actions}) == len(self.actions))
        for action in self.actions:
            require(self.scope.contains(action.location), ReasonCode.INVALID_COORDINATE)
        require(self.plan_hash == content_hash(self.content()), ReasonCode.HASH_MISMATCH)
        if self.approval is not None:
            require(self.approval.content_hash == self.plan_hash, ReasonCode.HASH_MISMATCH)
            require(self.created_at <= self.approval.approved_at < self.expires_at)

    def validate_snapshot(self, snapshot):
        require(type(snapshot) is TableSnapshot, ReasonCode.INVALID_TYPE)
        require(snapshot.asset_version == self.asset_version and snapshot.input_hash == self.input_hash,
                ReasonCode.HASH_MISMATCH)
        require(snapshot.limits == self.limits)
        column_keys = {(c.sheet_id, c.column_id) for c in snapshot.columns}
        for sheet in self.scope.sheets:
            require(sheet.sheet_id in snapshot.sheet_ids and all(
                (sheet.sheet_id, column) in column_keys for column in sheet.column_ids),
                ReasonCode.INVALID_COORDINATE)
        for action in self.actions:
            snapshot.validate_location(action.location)
