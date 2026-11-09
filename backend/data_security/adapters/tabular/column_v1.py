"""Retained column-v1 shape/format boundary, with an explicitly injected M1 action."""
from dataclasses import replace
from typing import Callable

from data_security.contracts import (BoundedPayload, MediaType, PayloadKind, ProtectionError)
from .codec import TableCodec


class PlanError(ValueError):
    def __init__(self, code, *, unsupported=False):
        self.code = code
        self.unsupported = unsupported
        super().__init__(code)


def validate_plan(plan, input_format, effective_action):
    if not isinstance(plan, dict) or plan.get('version') != '1':
        raise PlanError('PLAN_INVALID')
    if set(plan) - {'version', 'format', 'scope', 'operations'}:
        raise PlanError('PLAN_INVALID')
    if plan.get('format') != input_format:
        raise PlanError('PLAN_FORMAT_MISMATCH')
    scope = plan.get('scope')
    if not isinstance(scope, dict) or set(scope) != ({'columns', 'worksheets'} if input_format == 'xlsx' else {'columns'}):
        raise PlanError('PLAN_SCOPE_INVALID')
    operations = plan.get('operations', [])
    if not isinstance(operations, list):
        raise PlanError('PLAN_INVALID')
    lists = [scope.get('columns')]
    if input_format == 'xlsx':
        lists.append(scope.get('worksheets'))
    has_protection = False
    for operation in operations:
        if not isinstance(operation, dict) or operation.get('type') not in ('mask_columns', 'drop_columns', 'sanitize_formulas'):
            raise PlanError('PLAN_OPERATION_UNSUPPORTED', unsupported=True)
        kind = operation['type']
        allowed = {'type', 'columns', 'strategy', 'value'} if kind == 'mask_columns' else (
            {'type', 'columns'} if kind == 'drop_columns' else {'type'})
        if set(operation) - allowed:
            raise PlanError('PLAN_OPERATION_UNSUPPORTED', unsupported=True)
        if kind in ('mask_columns', 'drop_columns'):
            lists.append(operation.get('columns'))
            has_protection = True
        if kind == 'mask_columns':
            if operation.get('strategy', 'fixed') != 'fixed':
                raise PlanError('MASK_STRATEGY_UNSUPPORTED', unsupported=True)
            value = operation.get('value', '***')
            if not isinstance(value, str) or len(value) > 256:
                raise PlanError('MASK_VALUE_INVALID')
    for values in lists:
        if (not isinstance(values, list) or not values or
                any(not isinstance(v, str) or not v or len(v) > 200 for v in values) or
                len(set(values)) != len(values)):
            raise PlanError('PLAN_SCOPE_INVALID')
    if effective_action == 'mask' and not has_protection:
        raise PlanError('MASK_PLAN_REQUIRED')
    if effective_action not in ('allow', 'mask'):
        raise PlanError('PLAN_INVALID')
    return scope, operations


def transform_columns(content, input_format, plan, effective_action, limits,
                      replace_value: Callable[[str, str], str]):
    scope, operations = validate_plan(plan, input_format, effective_action)
    if len(operations) > limits.max_actions:
        raise PlanError('PLAN_OPERATION_LIMIT')
    drops, masks = set(), {}
    for operation in operations:
        names = operation.get('columns', [])
        if set(names) - set(scope['columns']):
            raise PlanError('PLAN_SCOPE_MISMATCH')
        if operation['type'] == 'drop_columns':
            drops.update(names)
        elif operation['type'] == 'mask_columns':
            value = operation.get('value', '***')
            for name in names:
                if name in masks and masks[name] != value:
                    raise PlanError('PLAN_OPERATION_CONFLICT')
                masks[name] = value
    if drops.intersection(masks):
        raise PlanError('PLAN_OPERATION_CONFLICT')
    output_names = [name for name in scope['columns'] if name not in drops]
    if not output_names:
        raise PlanError('PLAN_EMPTY_OUTPUT')
    codec = TableCodec(asset_version='legacy-column-v1')
    payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
        media_type=MediaType.CSV if input_format == 'csv' else MediaType.XLSX,
        text=None, tree=None, binary=content, limits=limits)
    snapshot = codec.parse(payload, limits)
    if isinstance(snapshot, ProtectionError):
        raise PlanError(snapshot.code.value, unsupported=True)
    titles = dict(codec.sheet_names)
    selected = scope.get('worksheets', ['CSV'])
    if set(selected) - set(titles.values()):
        raise PlanError('PLAN_SCOPE_MISMATCH')
    sheets = tuple(s for title in selected for s, name in codec.sheet_names if name == title)
    output_columns, cells = [], []
    count = 0
    for sheet in sheets:
        columns = [c for c in snapshot.columns if c.sheet_id == sheet]
        labels = [c.label for c in columns]
        if len(set(labels)) != len(labels) or any(not name for name in labels):
            raise PlanError('HEADER_INVALID', unsupported=True)
        if set(scope['columns']) - set(labels):
            raise PlanError('PLAN_SCOPE_MISMATCH')
        by_name = {c.label: c for c in columns}
        output_columns.extend(by_name[name] for name in output_names)
        by_id = {by_name[name].column_id: name for name in output_names}
        rows = set()
        for cell in snapshot.cells:
            if cell.sheet_id != sheet or cell.column_id not in by_id:
                continue
            name = by_id[cell.column_id]
            if cell.source_row != 1:
                rows.add(cell.source_row)
                if name in masks:
                    text = replace_value(cell.original_text, masks[name])
                    cell = replace(cell, original_text=text, normalized_text=text,
                        source_spans=tuple((i, i + 1) for i in range(len(text))))
            cells.append(cell)
        count += len(rows)
    if count > limits.max_rows:
        raise PlanError('ROW_LIMIT', unsupported=True)
    coverage = replace(snapshot.coverage, total=len(cells), eligible=len(cells), processed=len(cells))
    protected = replace(snapshot, sheet_ids=sheets, columns=tuple(output_columns), cells=tuple(cells), coverage=coverage)
    output = codec.serialize(protected, limits)
    if isinstance(output, ProtectionError):
        raise PlanError(output.code.value, unsupported=True)
    return output.binary, count
