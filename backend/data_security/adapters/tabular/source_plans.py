"""M8 source-schema conversion, without policy lookup or execution authority.

The owner supplies retained approval, asset and scope evidence explicitly. A
converted plan is NOT approved for delivery: its target approval stays absent.
Legacy fixed values outside M0's replacement vocabulary cannot be represented
and are rejected. Formula escaping remains the codec's serialization invariant,
including when the old plan omits its optional sanitize_formulas operation.
"""
from datetime import datetime
import hashlib
import json
import re

from data_security.contracts import (
    ActionPlan, Algorithm, Approval, ContractViolation, FrozenJSON, Location, LocationKind,
    MediaType, PolicyBinding, ProtectionError, ReasonCode, Replacement,
    ResolvedAction, SourceDocument, SourceFormat, SourcePlanBinding, SourceTrust,
    TableScope, TableSnapshot, content_hash,
)
from data_security.contracts.schema import digest, reference, require, utc


ADAPTER_VERSION = 'source-plans-v1'
MAINLINE_HASH_VERSION = 'mainline1-plan-sha256-v1'
LEGACY_HASH_VERSION = 'controlled-export-json-sha256-v1'


def _fields(value, required, optional=()):
    require(type(value) is dict, ReasonCode.INVALID_TYPE)
    require(not set(value) - set(required) - set(optional), ReasonCode.UNKNOWN_FIELD)
    require(not set(required) - set(value), ReasonCode.MISSING_FIELD)


def _strings(value, *, maximum=160):
    require(type(value) is list and bool(value) and all(
        type(item) is str and 0 < len(item) <= maximum for item in value), ReasonCode.INVALID_VALUE)
    require(len(value) == len(set(value)), ReasonCode.INVALID_VALUE)


def _uuid(value):
    require(type(value) is str and re.fullmatch(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value) is not None)


def _source_digest(value, *, mainline):
    # These are the two source contracts' JSON algorithms, not ds-json-v1.
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    result = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return 'sha256:' + result if mainline else result


class SourcePlanAdapter:
    """Pure conversion of one retained source plan and its immutable evidence.

    ``scope`` is the authorized input/output projection, preserving column and
    worksheet order. ``sheet_names`` supplies XLSX identity/title pairs retained
    by the owner; names never replace column identities. Legacy resolved actions
    reference ``operations/<zero-based-index>`` and mask every selected data cell
    (not headers). Mainline actions reference the original operation UUID.

    Evidence must come from the authorized owner boundary, not a client DTO.
    Mainline ``snapshot_source`` is the bounded FrozenJSON ``source`` metadata
    from the same governed envelope as the snapshot, independently of the plan
    binding. It retains parser/config identity, actual header policy and full
    worksheet dimensions; selected TableSnapshot cells cannot prove those facts.
    SourcePlanBinding alone is deliberately insufficient proof of approval.
    Freshness/revocation and target-plan approval remain the caller's job.
    """

    def __init__(self, *, source_binding: SourcePlanBinding, source_approval: Approval | None,
                 scope: TableScope, asset_version: str, input_hash: str, plan_id: str,
                 created_at: datetime, expires_at: datetime,
                 sheet_names: tuple[tuple[str, str], ...] = (),
                 snapshot_source: FrozenJSON | None = None):
        require(type(source_binding) is SourcePlanBinding and type(scope) is TableScope,
                ReasonCode.INVALID_TYPE)
        require(source_approval is None or type(source_approval) is Approval, ReasonCode.INVALID_TYPE)
        for value in (asset_version, plan_id):
            reference(value)
        digest(input_hash)
        utc(created_at)
        utc(expires_at)
        require(created_at < expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
        require(type(sheet_names) is tuple and all(type(pair) is tuple and len(pair) == 2
                and all(type(v) is str and v for v in pair) for pair in sheet_names), ReasonCode.INVALID_TYPE)
        require(len({p[0] for p in sheet_names}) == len(sheet_names)
                and len({p[1] for p in sheet_names}) == len(sheet_names), ReasonCode.INVALID_COORDINATE)
        require(snapshot_source is None or type(snapshot_source) is FrozenJSON, ReasonCode.INVALID_TYPE)
        self.snapshot_source = snapshot_source
        self.source_binding, self.source_approval, self.scope = source_binding, source_approval, scope
        self.asset_version, self.input_hash, self.plan_id = asset_version, input_hash, plan_id
        self.created_at, self.expires_at, self.sheet_names = created_at, expires_at, sheet_names

    def to_action_plan(self, source: SourceDocument, snapshot: TableSnapshot,
                       binding: PolicyBinding,
                       resolved_actions: tuple[ResolvedAction, ...]) -> ActionPlan | ProtectionError:
        try:
            require(type(source) is SourceDocument and type(snapshot) is TableSnapshot
                    and type(binding) is PolicyBinding and type(resolved_actions) is tuple
                    and all(type(a) is ResolvedAction for a in resolved_actions), ReasonCode.INVALID_TYPE)
            retained, approval = self.source_binding, self.source_approval
            require((source.source_format, source.source_version) ==
                    (retained.source_format, retained.source_version), ReasonCode.UNKNOWN_SCHEMA)
            require(retained.source_trust is not SourceTrust.UNVERIFIED and approval is not None
                    and retained.approval_basis_ref == approval.approval_ref
                    and retained.approval_basis_version is not None, ReasonCode.SOURCE_NOT_APPROVED)
            require(approval.content_hash == retained.source_plan_hash.removeprefix('sha256:'),
                    ReasonCode.HASH_MISMATCH)
            require(approval.approved_at <= self.created_at, ReasonCode.SOURCE_NOT_APPROVED)
            require((snapshot.asset_version, snapshot.input_hash) == (self.asset_version, self.input_hash),
                    ReasonCode.HASH_MISMATCH)
            require(len(resolved_actions) <= snapshot.limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
            coverage = snapshot.coverage
            require(coverage.total == coverage.processed == len(snapshot.cells)
                    and not any((coverage.excluded, coverage.failed, coverage.unknown, coverage.unscanned)),
                    ReasonCode.SCOPE_INCOMPLETE)
            columns = {(c.sheet_id, c.column_id): c for c in snapshot.columns}
            cells = {(c.sheet_id, c.source_row, c.column_id): c for c in snapshot.cells}
            header_row = 1  # Retained column-v1 always uses the first row as headers.
            if source.source_format is SourceFormat.MAINLINE1:
                require(self.snapshot_source is not None, ReasonCode.MISSING_FIELD)
                metadata = self.snapshot_source.to_value()
                _fields(metadata, ('parser_version', 'config_hash', 'config', 'structures'),
                    ('scope', 'scope_hash', 'coverage', 'warnings', 'excluded_contents',
                     'cell_metadata', 'column_label_rows'))
                require((metadata['parser_version'], metadata['config_hash']) ==
                        (retained.parser_version, retained.parser_config_hash), ReasonCode.HASH_MISMATCH)
                config = metadata['config']
                require(type(config) is dict and type(config.get('parser')) is dict, ReasonCode.INVALID_TYPE)
                require('header_row' in config['parser'], ReasonCode.MISSING_FIELD)
                require(_source_digest(config, mainline=True) == metadata['config_hash'], ReasonCode.HASH_MISMATCH)
                header_row = config['parser']['header_row']
                require(header_row is None or type(header_row) is int and
                        1 <= header_row <= snapshot.limits.max_rows, ReasonCode.INVALID_COORDINATE)
                structures = metadata['structures']
                require(type(structures) is list, ReasonCode.INVALID_TYPE)
                require(0 < len(structures) <= snapshot.limits.max_sheets, ReasonCode.LIMIT_EXCEEDED)
                rows = {}
                for sheet in structures:
                    _fields(sheet, ('sheet_id', 'rows', 'columns'),
                            ('name', 'hidden', 'hidden_rows', 'hidden_columns', 'merged'))
                    reference(sheet['sheet_id'])
                    require(sheet['sheet_id'] not in rows, ReasonCode.INVALID_COORDINATE)
                    require(type(sheet['rows']) is int and 0 <= sheet['rows'] <= snapshot.limits.max_rows,
                            ReasonCode.LIMIT_EXCEEDED)
                    rows[sheet['sheet_id']] = sheet['rows']
                require(set(snapshot.sheet_ids) <= rows.keys() and all(
                    c.source_row <= rows[c.sheet_id] for c in snapshot.cells), ReasonCode.INVALID_COORDINATE)
            else:
                rows = {sheet: max((c.source_row for c in snapshot.cells if c.sheet_id == sheet), default=0)
                        for sheet in snapshot.sheet_ids}
            for selection in self.scope.sheets:
                require(selection.sheet_id in rows and all((selection.sheet_id, col) in columns
                        for col in selection.column_ids), ReasonCode.INVALID_COORDINATE)
                for start, end in selection.row_ranges:
                    require(end <= rows[selection.sheet_id] and all(
                        (selection.sheet_id, row, col) in cells
                        for row in range(start, end + 1) for col in selection.column_ids
                        if row != header_row or selection.includes_header), ReasonCode.SCOPE_INCOMPLETE)
            document = source.document.to_value()
            if source.source_format is SourceFormat.MAINLINE1:
                actions = self._mainline(document, columns, resolved_actions)
            else:
                actions = self._legacy(document, snapshot, columns, rows, resolved_actions)

            # Structural deletion cannot operate on a partial row/header scope.
            drops, occupied = set(), {}
            for action in actions:
                loc = action.location
                require(self.scope.contains(loc) and (header_row is None or loc.source_row != header_row or any(
                    s.sheet_id == loc.sheet_id and s.includes_header for s in self.scope.sheets)),
                    ReasonCode.AUTHORIZATION_DENIED)
                key = (loc.sheet_id, loc.column_id)
                if loc.kind is LocationKind.COLUMN:
                    require(key not in drops, ReasonCode.INVALID_COORDINATE)
                    drops.add(key)
                    selection = next(s for s in self.scope.sheets if s.sheet_id == loc.sheet_id)
                    require(selection.includes_header and selection.row_ranges == ((1, rows[loc.sheet_id]),)
                            and all((loc.sheet_id, row, loc.column_id) in cells
                                    for row in range(1, rows[loc.sheet_id] + 1)), ReasonCode.UNSUPPORTED_SCOPE)
                else:
                    cell = cells.get((loc.sheet_id, loc.source_row, loc.column_id))
                    require(cell is not None, ReasonCode.INVALID_COORDINATE)
                    if loc.kind is LocationKind.CELL_SPAN:
                        require(cell.mapping_proven and loc.end <= len(cell.original_text)
                                and loc.start in {a for a, _ in cell.source_spans}
                                and loc.end in {b for _, b in cell.source_spans}, ReasonCode.INVALID_COORDINATE)
                    interval = (loc.start, loc.end) if loc.kind is LocationKind.CELL_SPAN else (0, float('inf'))
                    occupied.setdefault((loc.sheet_id, loc.column_id, loc.source_row), []).append(interval)
            for (sheet, column, _), intervals in occupied.items():
                require((sheet, column) not in drops, ReasonCode.INVALID_COORDINATE)
                ordered = sorted(intervals)
                require(all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])), ReasonCode.INVALID_COORDINATE)
            for selection in self.scope.sheets:
                require(any((selection.sheet_id, col) not in drops for col in selection.column_ids),
                        ReasonCode.UNSUPPORTED_SCOPE)
            fields = dict(schema_version=ActionPlan.SCHEMA, plan_id=self.plan_id,
                asset_version=self.asset_version, input_hash=self.input_hash, scope=self.scope,
                actions=actions, policy_binding=binding, unresolved=(), source=retained,
                adapter_version=ADAPTER_VERSION, created_at=self.created_at, expires_at=self.expires_at,
                limits=snapshot.limits)
            return ActionPlan(**fields, plan_hash=content_hash(fields), approval=None)
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=self.plan_id)

    def _mainline(self, doc, columns, resolved):
        _fields(doc, ('meta', 'asset', 'scan_id', 'profile_id', 'scope_hash', 'parser_version',
            'parser_config_hash', 'policy_version', 'redaction_policy_version', 'requirements',
            'requirements_hash', 'operation_contract_version', 'plan_id', 'operations', 'operation_count',
            'unresolved', 'validation_errors', 'status', 'checked_applicability_version', 'validation_ref', 'plan_hash'))
        _fields(doc['meta'], ('schema_version', 'trace_id', 'environment', 'evaluation_run_id', 'domain_id', 'created_at'))
        _fields(doc['asset'], ('asset_id', 'asset_version_id', 'content_hash'))
        retained = self.source_binding
        for value in (doc['plan_id'], doc['scan_id'], doc['profile_id'], doc['asset']['asset_id'],
                      doc['asset']['asset_version_id'], doc['meta']['trace_id']):
            _uuid(value)
        meta = doc['meta']
        require(meta['schema_version'] == 'mainline1.proposed.v1', ReasonCode.UNKNOWN_SCHEMA)
        require(meta['environment'] in ('development', 'test', 'production') and
                (meta['environment'], meta['domain_id'], meta['evaluation_run_id']) ==
                (retained.source_environment, retained.source_domain, retained.evaluation_ref), ReasonCode.HASH_MISMATCH)
        if meta['evaluation_run_id'] is not None:
            _uuid(meta['evaluation_run_id'])
        require(type(meta['created_at']) is str)
        try:
            source_created_at = datetime.fromisoformat(meta['created_at'].replace('Z', '+00:00'))
        except ValueError:
            raise ContractViolation(ReasonCode.INVALID_VALUE) from None
        require(source_created_at.tzinfo is not None)
        require(retained.source_state == doc['status'] == 'ready', ReasonCode.SOURCE_NOT_APPROVED)
        require(doc['unresolved'] == [] and doc['validation_errors'] == [], ReasonCode.SCOPE_INCOMPLETE)
        require(type(doc['checked_applicability_version']) is int and doc['checked_applicability_version'] > 0)
        require(doc['validation_ref'] == 'private:plan-validation:' + doc['plan_id'])
        require(doc['parser_version'] == retained.parser_version == 'internal-table-v2'
                and doc['operation_contract_version'] == retained.operation_contract_version ==
                'original-snapshot-v1-proposed', ReasonCode.UNKNOWN_SCHEMA)
        for name in ('parser_config_hash', 'scope_hash', 'requirements_hash'):
            require(doc[name] == getattr(retained, name), ReasonCode.HASH_MISMATCH)
        for name in ('policy_version', 'redaction_policy_version'):
            reference(doc[name])
        require((doc['asset']['asset_version_id'], doc['asset']['content_hash']) ==
                (self.asset_version, 'sha256:' + self.input_hash), ReasonCode.HASH_MISMATCH)
        content = dict(doc, meta={k: v for k, v in meta.items() if k != 'trace_id'})
        content.pop('plan_hash')
        require(doc['plan_hash'] == retained.source_plan_hash == _source_digest(content, mainline=True),
                ReasonCode.HASH_MISMATCH)

        # Reconstruct mainline's normalized Scope from fixed identities, not names.
        selections = []
        includes_header = {s.includes_header for s in self.scope.sheets}
        require(len(includes_header) == 1, ReasonCode.UNSUPPORTED_SCOPE)
        for sheet in sorted(self.scope.sheets, key=lambda s: s.sheet_id):
            indices = [columns[sheet.sheet_id, col].source_index for col in sheet.column_ids]
            require(indices == sorted(indices), ReasonCode.UNSUPPORTED_SCOPE)
            ranges = []
            for index in indices:
                if ranges and index == ranges[-1][1] + 1:
                    ranges[-1][1] = index
                else:
                    ranges.append([index, index])
            selections.append(dict(sheet_id=sheet.sheet_id, rows=sheet.row_ranges, columns=ranges))
        scope = dict(asset_version_id=self.asset_version, selections=selections,
                     include_header=next(iter(includes_header)))
        require(_source_digest(scope, mainline=True) == retained.scope_hash, ReasonCode.HASH_MISMATCH)
        require(type(doc['requirements']) is list and 0 < len(doc['requirements']) <= 100,
                ReasonCode.INVALID_VALUE)
        requirements = {}
        for req in doc['requirements']:
            _fields(req, ('requirement_id', 'version', 'category_ids', 'allowed_operations',
                          'allow_drop_column', 'require_complete_coverage', 'allow_unresolved'))
            reference(req['requirement_id'])
            reference(req['version'])
            require(req['requirement_id'] not in requirements)
            requirements[req['requirement_id']] = req
            for name in ('category_ids', 'allowed_operations'):
                _strings(req[name])
                require(req[name] == sorted(req[name]))
            require(all(op in ('mask_span', 'mask_cell', 'drop_column') for op in req['allowed_operations']),
                    ReasonCode.UNSUPPORTED_SCOPE)
            require(all(type(req[name]) is bool for name in ('allow_drop_column', 'require_complete_coverage', 'allow_unresolved')))
            require('drop_column' not in req['allowed_operations'] or req['allow_drop_column'])
        require(list(requirements) == sorted(requirements))
        require(_source_digest(doc['requirements'], mainline=True) == retained.requirements_hash,
                ReasonCode.HASH_MISMATCH)
        require(type(doc['operations']) is list and len(doc['operations']) <= 1000, ReasonCode.LIMIT_EXCEEDED)
        require(type(doc['operation_count']) is int and doc['operation_count'] == len(doc['operations']))
        by_ref = {a.source_operation_ref: a for a in resolved}
        require(len(by_ref) == len(resolved) == len(doc['operations']), ReasonCode.SCOPE_INCOMPLETE)
        indexed_columns = {(c.sheet_id, c.source_index): c.column_id for c in columns.values()}
        actions, seen = [], set()
        kinds = {'mask_span': LocationKind.CELL_SPAN, 'mask_cell': LocationKind.CELL, 'drop_column': LocationKind.COLUMN}
        for op in doc['operations']:
            _fields(op, ('operation_id', 'type', 'target', 'replacement', 'match_ref', 'finding_ids', 'requirement_ids'))
            _uuid(op['operation_id'])
            require(op['operation_id'] not in seen)
            seen.add(op['operation_id'])
            require(type(op['type']) is str and op['type'] in kinds, ReasonCode.UNSUPPORTED_SCOPE)
            require(op['replacement'] == (None if op['type'] == 'drop_column' else '[REDACTED]'))
            require(op['match_ref'] == 'private:plan-match:' + doc['plan_id'] + ':' + op['operation_id'])
            for name in ('finding_ids', 'requirement_ids'):
                _strings(op[name])
                require(op[name] == sorted(op[name]))
            require(all(rid in requirements for rid in op['requirement_ids']))
            loc = op['target']
            _fields(loc, ('kind', 'sheet_id', 'row', 'column', 'channel', 'span'))
            require(type(loc['sheet_id']) is str and type(loc['column']) is int
                    and (loc['sheet_id'], loc['column']) in indexed_columns, ReasonCode.INVALID_COORDINATE)
            kind = kinds[op['type']]
            require(loc['kind'] == {LocationKind.CELL_SPAN: 'span', LocationKind.CELL: 'cell',
                    LocationKind.COLUMN: 'column'}[kind] and loc['channel'] == 'value', ReasonCode.UNSUPPORTED_SCOPE)
            start = end = None
            if kind is LocationKind.CELL_SPAN:
                _fields(loc['span'], ('start', 'end'))
                start, end = loc['span']['start'], loc['span']['end']
            else:
                require(loc['span'] is None, ReasonCode.INVALID_COORDINATE)
            target = Location(schema_version=Location.SCHEMA, kind=kind, sheet_id=loc['sheet_id'],
                source_row=loc['row'], column_id=indexed_columns[loc['sheet_id'], loc['column']],
                start=start, end=end, json_path=())
            action = by_ref.get(op['operation_id'])
            require(action is not None, ReasonCode.SCOPE_INCOMPLETE)
            require(action.location == target and action.finding_refs == tuple(op['finding_ids'])
                    and action.requirement_refs == tuple(op['requirement_ids']), ReasonCode.INVALID_COORDINATE)
            # Whole-cell execution cannot apply a fragment-preserving algorithm.
            require(kind is not LocationKind.CELL or action.algorithm.algorithm in (Algorithm.DROP, Algorithm.REPLACE),
                    ReasonCode.UNSUPPORTED_SCOPE)
            require(all(op['type'] in requirements[rid]['allowed_operations'] and
                        action.category.value in requirements[rid]['category_ids'] for rid in op['requirement_ids']),
                    ReasonCode.AUTHORIZATION_DENIED)
            actions.append(action)
        return tuple(actions)

    def _legacy(self, doc, snapshot, columns, rows, resolved):
        _fields(doc, ('version', 'format', 'scope'), ('operations',))
        require(doc['version'] == '1', ReasonCode.UNKNOWN_SCHEMA)
        expected_format = 'csv' if snapshot.media_type is MediaType.CSV else 'xlsx'
        require(doc['format'] == expected_format, ReasonCode.UNSUPPORTED_FORMAT)
        scope = doc['scope']
        _fields(scope, ('columns',) if expected_format == 'csv' else ('columns', 'worksheets'))
        _strings(scope['columns'], maximum=200)
        require(_source_digest(doc, mainline=False) == self.source_binding.source_plan_hash
                and _source_digest(scope, mainline=False) == self.source_binding.scope_hash, ReasonCode.HASH_MISMATCH)
        if expected_format == 'csv':
            require(snapshot.sheet_ids == ('csv:0',), ReasonCode.INVALID_COORDINATE)
            selected = ('csv:0',)
        else:
            _strings(scope['worksheets'])
            names = {name: sheet for sheet, name in self.sheet_names}
            require(all(sheet in snapshot.sheet_ids for sheet, _ in self.sheet_names)
                    and all(name in names for name in scope['worksheets']), ReasonCode.INVALID_COORDINATE)
            selected = tuple(names[name] for name in scope['worksheets'])
        require(tuple(s.sheet_id for s in self.scope.sheets) == selected, ReasonCode.AUTHORIZATION_DENIED)
        selected_columns = {}
        for selection in self.scope.sheets:
            header = [c for c in columns.values() if c.sheet_id == selection.sheet_id]
            require(all(c.label for c in header) and len({c.label for c in header}) == len(header),
                    ReasonCode.INVALID_COORDINATE)
            by_name = {c.label: c.column_id for c in header}
            require(all(label in by_name for label in scope['columns']), ReasonCode.INVALID_COORDINATE)
            ids = tuple(by_name[label] for label in scope['columns'])
            require(selection.column_ids == ids and selection.includes_header
                    and selection.row_ranges == ((1, rows[selection.sheet_id]),), ReasonCode.AUTHORIZATION_DENIED)
            selected_columns[selection.sheet_id] = by_name
        operations = doc.get('operations', [])
        require(type(operations) is list, ReasonCode.INVALID_TYPE)
        expected = {}
        for index, op in enumerate(operations):
            require(type(op) is dict and type(op.get('type')) is str, ReasonCode.INVALID_TYPE)
            kind = op['type']
            require(kind in ('mask_columns', 'drop_columns', 'sanitize_formulas'), ReasonCode.UNSUPPORTED_SCOPE)
            _fields(op, ('type',) if kind == 'sanitize_formulas' else ('type', 'columns'),
                    ('strategy', 'value') if kind == 'mask_columns' else ())
            if kind == 'sanitize_formulas':
                continue  # Serialization always neutralizes formulas, never optional.
            _strings(op['columns'], maximum=200)
            require(set(op['columns']) <= set(scope['columns']), ReasonCode.AUTHORIZATION_DENIED)
            replacement = None
            if kind == 'mask_columns':
                require(op.get('strategy', 'fixed') == 'fixed', ReasonCode.UNSUPPORTED_SCOPE)
                replacement = op.get('value', '***')
                require(type(replacement) is str and len(replacement) <= 256)
                require(replacement in {r.value for r in Replacement}, ReasonCode.UNSUPPORTED_SCOPE)
            for sheet in selected:
                for label in op['columns']:
                    column = selected_columns[sheet][label]
                    for row in (None,) if kind == 'drop_columns' else range(2, rows[sheet] + 1):
                        loc = Location(schema_version=Location.SCHEMA,
                            kind=LocationKind.COLUMN if row is None else LocationKind.CELL,
                            sheet_id=sheet, source_row=row, column_id=column, start=None, end=None, json_path=())
                        expected[('operations/' + str(index), loc)] = replacement
                        require(len(expected) <= snapshot.limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
        by_target = {(a.source_operation_ref, a.location): a for a in resolved}
        require(len(by_target) == len(resolved) and set(by_target) == set(expected), ReasonCode.SCOPE_INCOMPLETE)
        actions = []
        for key, replacement in expected.items():
            action = by_target[key]
            require(action.algorithm.algorithm is (Algorithm.DROP if replacement is None else Algorithm.REPLACE)
                    and (replacement is None or action.algorithm.replacement.value == replacement),
                    ReasonCode.UNSUPPORTED_SCOPE)
            actions.append(action)
        return tuple(actions)
