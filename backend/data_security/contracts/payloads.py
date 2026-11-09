from dataclasses import dataclass
from typing import ClassVar

from .enums import (Category, Environment, Level, LocationKind, MediaType, Outlet,
                    PayloadKind, Purpose, ReasonCode, Role, Unit)
from .schema import (DTO, FrozenJSON, MAX_BYTES, MAX_ITEMS, MAX_JSON_BYTES, MAX_JSON_DEPTH,
                     MAX_JSON_FIELDS, MAX_JSON_NODES, MAX_TEXT_CHARS, count, digest,
                     reference, require)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Limits(DTO):
    SCHEMA: ClassVar[str] = 'ds.limits.v1'
    version: str
    max_bytes: int
    max_text_chars: int
    max_json_bytes: int
    max_json_depth: int
    max_json_nodes: int
    max_json_fields: int
    max_sheets: int
    max_rows: int
    max_columns: int
    max_cells: int
    max_findings: int
    max_actions: int
    max_zip_members: int
    max_expanded_bytes: int
    max_inflight_objects: int

    def __post_init__(self):
        DTO.__post_init__(self)
        require(self.version == 'limits-2026-11-04.v1', ReasonCode.UNKNOWN_SCHEMA)
        caps = {'max_bytes': MAX_BYTES, 'max_text_chars': MAX_TEXT_CHARS,
                'max_json_bytes': MAX_JSON_BYTES, 'max_json_depth': MAX_JSON_DEPTH,
                'max_json_nodes': MAX_JSON_NODES, 'max_json_fields': MAX_JSON_FIELDS,
                'max_sheets': 16, 'max_rows': 100_000, 'max_columns': 512,
                'max_cells': MAX_ITEMS, 'max_findings': 10_000, 'max_actions': 10_000,
                'max_zip_members': 1000, 'max_expanded_bytes': 100 * 1024 * 1024,
                'max_inflight_objects': 2}
        for name, cap in caps.items():
            require(0 < getattr(self, name) <= cap, ReasonCode.LIMIT_EXCEEDED)


BASELINE_LIMITS = Limits(
    schema_version=Limits.SCHEMA, version='limits-2026-11-04.v1', max_bytes=MAX_BYTES,
    max_text_chars=MAX_TEXT_CHARS, max_json_bytes=MAX_JSON_BYTES, max_json_depth=MAX_JSON_DEPTH,
    max_json_nodes=MAX_JSON_NODES, max_json_fields=MAX_JSON_FIELDS, max_sheets=16,
    max_rows=100_000, max_columns=512, max_cells=100_000, max_findings=10_000,
    max_actions=10_000, max_zip_members=1000, max_expanded_bytes=100 * 1024 * 1024,
    max_inflight_objects=2,
)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ProtectionContext(DTO):
    SCHEMA: ClassVar[str] = 'ds.protection-context.v1'
    SERVER_ONLY: ClassVar[bool] = True
    actor_ref: str
    authorization_ref: str
    scope_refs: tuple[str, ...]
    environment: Environment
    domain: str
    outlet: Outlet
    purpose: Purpose
    role: Role
    object_ref: str
    object_version: str
    source_ref: str | None
    source_version: str | None
    source_hash: str | None
    trace_id: str

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.actor_ref, self.authorization_ref, self.domain, self.object_ref,
                      self.object_version, self.trace_id, *self.scope_refs):
            reference(value)
        require(0 < len(self.scope_refs) <= 1024 and len(set(self.scope_refs)) == len(self.scope_refs))
        source = (self.source_ref, self.source_version, self.source_hash)
        require(all(item is None for item in source) or all(item is not None for item in source))
        if self.source_ref is not None:
            reference(self.source_ref)
            reference(self.source_version)
            digest(self.source_hash)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class BoundedPayload(DTO):
    SCHEMA: ClassVar[str] = 'ds.bounded-payload.v1'
    SENSITIVE: ClassVar[bool] = True
    kind: PayloadKind
    media_type: MediaType
    text: str | None
    tree: FrozenJSON | None
    binary: bytes | None
    limits: Limits

    def __post_init__(self):
        DTO.__post_init__(self)
        require(sum(item is not None for item in (self.text, self.tree, self.binary)) == 1)
        if self.kind is PayloadKind.TEXT:
            require(self.text is not None and self.media_type is MediaType.TEXT)
            require(len(self.text) <= self.limits.max_text_chars and
                    len(self.text.encode('utf-8')) <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
        elif self.kind is PayloadKind.JSON:
            require(self.tree is not None and self.media_type is MediaType.JSON)
            FrozenJSON(self.tree.to_value(), max_depth=self.limits.max_json_depth,
                       max_nodes=self.limits.max_json_nodes, max_fields=self.limits.max_json_fields,
                       max_text_chars=self.limits.max_text_chars, max_bytes=self.limits.max_json_bytes)
        else:
            require(self.binary is not None and self.media_type in (MediaType.CSV, MediaType.XLSX, MediaType.BINARY))
            require(len(self.binary) <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Coverage(DTO):
    SCHEMA: ClassVar[str] = 'ds.coverage.v1'
    unit: Unit
    total: int
    eligible: int
    processed: int
    excluded: int
    failed: int
    unknown: int
    unscanned: int
    version: str

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.total, self.eligible, self.processed, self.excluded,
                      self.failed, self.unknown, self.unscanned):
            count(value, 2**53 - 1)
        require(self.total == self.eligible + self.excluded)
        require(self.eligible == self.processed + self.failed + self.unknown + self.unscanned)
        reference(self.version)

    @property
    def ratio(self):
        return self.processed / self.eligible if self.eligible else None


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Metric(DTO):
    SCHEMA: ClassVar[str] = 'ds.metric.v1'
    numerator: int
    denominator: int
    version: str
    zero_reason: ReasonCode | None

    def __post_init__(self):
        DTO.__post_init__(self)
        count(self.numerator, 2**53 - 1)
        count(self.denominator, 2**53 - 1)
        require(self.numerator <= self.denominator)
        require((self.denominator == 0) == (self.zero_reason is not None))
        reference(self.version)

    @property
    def ratio(self):
        return self.numerator / self.denominator if self.denominator else None


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Location(DTO):
    SCHEMA: ClassVar[str] = 'ds.location.v1'
    kind: LocationKind
    sheet_id: str | None
    source_row: int | None
    column_id: str | None
    start: int | None
    end: int | None
    json_path: tuple[str | int, ...]

    def __post_init__(self):
        DTO.__post_init__(self)
        table = self.kind in (LocationKind.CELL, LocationKind.CELL_SPAN, LocationKind.COLUMN)
        span = self.kind in (LocationKind.TEXT_SPAN, LocationKind.CELL_SPAN)
        require(table == (self.sheet_id is not None and self.column_id is not None), ReasonCode.INVALID_COORDINATE)
        if table:
            reference(self.sheet_id)
            reference(self.column_id)
            require(not self.json_path, ReasonCode.INVALID_COORDINATE)
        else:
            require(self.sheet_id is None and self.column_id is None and self.source_row is None,
                    ReasonCode.INVALID_COORDINATE)
        if self.kind in (LocationKind.CELL, LocationKind.CELL_SPAN):
            require(self.source_row is not None and 1 <= self.source_row <= 100_000,
                    ReasonCode.INVALID_COORDINATE)
        else:
            require(self.source_row is None, ReasonCode.INVALID_COORDINATE)
        if span:
            require(self.start is not None and self.end is not None and
                    0 <= self.start < self.end <= MAX_TEXT_CHARS, ReasonCode.INVALID_COORDINATE)
        else:
            require(self.start is None and self.end is None, ReasonCode.INVALID_COORDINATE)
        require((self.kind is LocationKind.JSON_FIELD) == bool(self.json_path), ReasonCode.INVALID_COORDINATE)
        require(len(self.json_path) <= MAX_JSON_DEPTH, ReasonCode.LIMIT_EXCEEDED)
        for part in self.json_path:
            if type(part) is int:
                count(part)
            else:
                require(0 < len(part) <= 256)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Finding(DTO):
    SCHEMA: ClassVar[str] = 'ds.finding.v1'
    category: Category
    level: Level
    rule_version: str
    location: Location
    reason: ReasonCode

    def __post_init__(self):
        DTO.__post_init__(self)
        expected = {Category.EMAIL: Level.L2, Category.IPV4: Level.L1,
                    Category.CARD: Level.L3, Category.SECRET: Level.L3}
        require(self.level is expected[self.category])
        reference(self.rule_version)
        require(self.reason in (ReasonCode.MATCHED_FORMAT, ReasonCode.MATCHED_CONTEXT))


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class TableColumn(DTO):
    SCHEMA: ClassVar[str] = 'ds.table-column.v1'
    SENSITIVE: ClassVar[bool] = True
    sheet_id: str
    column_id: str
    source_index: int
    label: str

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.sheet_id)
        reference(self.column_id)
        require(1 <= self.source_index <= 512, ReasonCode.INVALID_COORDINATE)
        require(len(self.label) <= MAX_TEXT_CHARS, ReasonCode.LIMIT_EXCEEDED)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class TableCell(DTO):
    SCHEMA: ClassVar[str] = 'ds.table-cell.v1'
    SENSITIVE: ClassVar[bool] = True
    sheet_id: str
    column_id: str
    source_row: int
    logical_record: int
    original_text: str
    normalized_text: str
    source_spans: tuple[tuple[int, int], ...]
    mapping_proven: bool

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.sheet_id)
        reference(self.column_id)
        require(1 <= self.source_row <= 100_000 and 1 <= self.logical_record <= 100_000,
                ReasonCode.INVALID_COORDINATE)
        require(len(self.original_text) <= MAX_TEXT_CHARS and len(self.normalized_text) <= MAX_TEXT_CHARS,
                ReasonCode.LIMIT_EXCEEDED)
        if self.mapping_proven:
            require(len(self.source_spans) == len(self.normalized_text), ReasonCode.INVALID_COORDINATE)
            previous = (0, 0)
            for start, end in self.source_spans:
                require(0 <= start < end <= len(self.original_text) and start >= previous[0]
                        and end >= previous[1], ReasonCode.INVALID_COORDINATE)
                previous = (start, end)
        else:
            require(not self.source_spans, ReasonCode.INVALID_COORDINATE)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class TableSnapshot(DTO):
    SCHEMA: ClassVar[str] = 'ds.table-snapshot.v1'
    SENSITIVE: ClassVar[bool] = True
    asset_version: str
    input_hash: str
    media_type: MediaType
    sheet_ids: tuple[str, ...]
    columns: tuple[TableColumn, ...]
    cells: tuple[TableCell, ...]
    coverage: Coverage
    limits: Limits
    coordinate_version: str

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.asset_version)
        digest(self.input_hash)
        require(self.media_type in (MediaType.CSV, MediaType.XLSX))
        require(self.coordinate_version == 'source-codepoint-half-open.v1', ReasonCode.UNKNOWN_SCHEMA)
        require(0 < len(self.sheet_ids) <= self.limits.max_sheets and
                len(set(self.sheet_ids)) == len(self.sheet_ids), ReasonCode.LIMIT_EXCEEDED)
        for item in self.sheet_ids:
            reference(item)
        require(len(self.cells) <= self.limits.max_cells, ReasonCode.LIMIT_EXCEEDED)
        column_keys = {(column.sheet_id, column.column_id) for column in self.columns}
        indices = {(column.sheet_id, column.source_index) for column in self.columns}
        require(len(column_keys) == len(indices) == len(self.columns), ReasonCode.INVALID_COORDINATE)
        require(all(column.sheet_id in self.sheet_ids for column in self.columns), ReasonCode.INVALID_COORDINATE)
        for sheet_id in self.sheet_ids:
            require(sum(column.sheet_id == sheet_id for column in self.columns) <= self.limits.max_columns,
                    ReasonCode.LIMIT_EXCEEDED)
        seen = set()
        size = sum(len(column.label.encode('utf-8')) for column in self.columns)
        for cell in self.cells:
            key = (cell.sheet_id, cell.source_row, cell.column_id)
            require((cell.sheet_id, cell.column_id) in column_keys and key not in seen,
                    ReasonCode.INVALID_COORDINATE)
            seen.add(key)
            require(cell.source_row <= self.limits.max_rows and cell.logical_record <= self.limits.max_rows,
                    ReasonCode.LIMIT_EXCEEDED)
            require(max(len(cell.original_text), len(cell.normalized_text)) <= self.limits.max_text_chars,
                    ReasonCode.LIMIT_EXCEEDED)
            size += len(cell.original_text.encode('utf-8')) + len(cell.normalized_text.encode('utf-8'))
        require(size <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
        require(self.coverage.unit is Unit.CELL and self.coverage.total >= len(self.cells))

    def validate_location(self, location):
        require(type(location) is Location, ReasonCode.INVALID_TYPE)
        require(location.sheet_id in self.sheet_ids and any(
            c.sheet_id == location.sheet_id and c.column_id == location.column_id for c in self.columns),
            ReasonCode.INVALID_COORDINATE)
        if location.kind is LocationKind.COLUMN:
            return
        matches = [cell for cell in self.cells if (cell.sheet_id, cell.source_row, cell.column_id) ==
                   (location.sheet_id, location.source_row, location.column_id)]
        require(len(matches) == 1, ReasonCode.INVALID_COORDINATE)
        if location.kind is LocationKind.CELL_SPAN:
            require(matches[0].mapping_proven and location.end <= len(matches[0].original_text),
                    ReasonCode.INVALID_COORDINATE)
