"""Bounded private persistence bridge for mainline1's internal-table-v2 result.

This is not an export codec or an authorization decision. Only selected cells
are mapped; excluded headers are never re-read or invented. Their column labels
are empty and ``column_label_rows`` records whether a source header was present.
The source metadata preserves parser/config/scope identities, exclusions and
cell types; it contains no second copy of the original cell payload.
"""
import json
import unicodedata
from dataclasses import asdict

from mainline1.parsing import PARSER_VERSION, ParseResult, fingerprint, normalize_scope

from data_security.contracts.enums import MediaType, PayloadKind, ReasonCode, Unit
from data_security.contracts.payloads import (
    BoundedPayload, Coverage, Limits, TableCell, TableColumn, TableSnapshot,
)
from data_security.contracts.schema import FrozenJSON, primitive, require

SCHEMA_VERSION = 'ds.parsed-artifact.v1'
ADAPTER_VERSION = 'parsed-artifact-2026-11-06.v1'


def govern_parse_result(result: ParseResult, *, limits: Limits) -> BoundedPayload:
    """Map a known parser result to one versioned, M0-bounded JSON representation.

    XLSX hidden/merged structures and formula channels cannot be represented as
    ordinary M0 cells and are rejected, not flattened. Numeric/date source text
    and formatting metadata are retained exactly, without display conversion.
    Unproven Unicode mappings remain unproven (cell-only operations).
    """
    require(type(result) is ParseResult and type(limits) is Limits, ReasonCode.INVALID_TYPE)
    require(result.parser_version == PARSER_VERSION, ReasonCode.UNKNOWN_SCHEMA)
    for value in (result.config_json, result.structure_json, result.coverage_json):
        require(len(value.encode('utf-8')) <= limits.max_json_bytes, ReasonCode.LIMIT_EXCEEDED)
    config = json.loads(result.config_json)
    structures = json.loads(result.structure_json)
    coverage = json.loads(result.coverage_json)
    require(set(config) == {'parser', 'limits', 'unicode_version'}, ReasonCode.UNKNOWN_FIELD)
    require(config['unicode_version'] == unicodedata.unidata_version, ReasonCode.UNKNOWN_SCHEMA)
    require(set(config['parser']) == {
        'encoding', 'delimiter', 'quotechar', 'doublequote', 'header_row', 'include_header',
        'hidden_policy', 'formula_policy', 'normalization',
    }, ReasonCode.UNKNOWN_FIELD)
    require(set(config['limits']) == {
        'max_bytes', 'max_rows', 'max_columns', 'max_cells', 'max_cell_codepoints',
        'max_zip_entries', 'max_uncompressed_bytes', 'max_seconds',
    }, ReasonCode.UNKNOWN_FIELD)
    require(fingerprint(config) == result.config_hash and
            fingerprint(asdict(result.scope)) == result.scope_hash)
    require(normalize_scope(result.scope) == result.scope and
            result.scope.asset_version_id == result.asset_version_id, ReasonCode.INVALID_COORDINATE)
    require(result.scope.include_header == config['parser']['include_header'])
    require(result.input_content_hash.startswith('sha256:'))
    require(0 < len(structures) <= limits.max_sheets, ReasonCode.LIMIT_EXCEEDED)
    csv = structures[0]['sheet_id'] == 'csv:0'
    media_type = MediaType.CSV if csv else MediaType.XLSX
    require(not csv or len(structures) == 1, ReasonCode.INVALID_COORDINATE)
    dimensions = {}
    for index, sheet in enumerate(structures):
        expected = {'sheet_id', 'rows', 'columns'}
        if not csv:
            expected |= {'name', 'hidden', 'hidden_rows', 'hidden_columns', 'merged'}
            require(not (sheet['hidden'] or sheet['hidden_rows'] or sheet['hidden_columns'] or
                         sheet['merged']), ReasonCode.UNSUPPORTED_FORMAT)
        require(set(sheet) == expected, ReasonCode.UNKNOWN_FIELD)
        require(sheet['sheet_id'] == ('csv:0' if csv else f'xlsx:{index}'), ReasonCode.INVALID_COORDINATE)
        require(0 <= sheet['rows'] <= limits.max_rows and
                0 <= sheet['columns'] <= limits.max_columns, ReasonCode.LIMIT_EXCEEDED)
        dimensions[sheet['sheet_id']] = sheet['rows'], sheet['columns']
    require(sum(rows * columns for rows, columns in dimensions.values()) <= limits.max_cells,
            ReasonCode.LIMIT_EXCEEDED)
    selections = {item.sheet_id: item for item in result.scope.selections}
    for sid, selection in selections.items():
        require(sid in dimensions, ReasonCode.INVALID_COORDINATE)
        rows, columns = dimensions[sid]
        require(selection.rows[-1][1] <= rows and selection.columns[-1][1] <= columns,
                ReasonCode.INVALID_COORDINATE)
    require(len(result.cells) <= limits.max_cells, ReasonCode.LIMIT_EXCEEDED)
    cells, cell_metadata = [], []
    mapping_nodes = 0
    for cell in result.cells:
        require(cell.sheet_id in selections, ReasonCode.INVALID_COORDINATE)
        selection = selections[cell.sheet_id]
        require(any(start <= cell.row <= end for start, end in selection.rows) and
                any(start <= cell.column <= end for start, end in selection.columns) and
                (result.scope.include_header or cell.row != config['parser']['header_row']),
                ReasonCode.INVALID_COORDINATE)
        require(cell.value_type in ('text', 'number', 'boolean', 'date', 'missing') and
                cell.channel == 'value' and cell.cache_status == 'not_applicable',
                ReasonCode.UNSUPPORTED_FORMAT)
        require(cell.normalization == config['parser']['normalization'])
        require(len(cell.source_text) <= limits.max_text_chars, ReasonCode.LIMIT_EXCEEDED)
        normalized, spans = cell.mapping()
        # Each span contributes an array and two integers to the final JSON budget.
        mapping_nodes += 3 * len(spans or ())
        require(mapping_nodes <= limits.max_json_nodes, ReasonCode.LIMIT_EXCEEDED)
        cells.append(TableCell(
            schema_version=TableCell.SCHEMA, sheet_id=cell.sheet_id, column_id=f'c{cell.column}',
            source_row=cell.row, logical_record=cell.row, original_text=cell.source_text,
            normalized_text=normalized, source_spans=spans if spans is not None else (),
            mapping_proven=spans is not None,
        ))
        # Position in this array is the position in snapshot.cells, not a new coordinate system.
        cell_metadata.append(dict(value_type=cell.value_type, channel=cell.channel,
                                  cache_status=cell.cache_status, number_format=cell.number_format,
                                  normalization=cell.normalization))
    header_row = config['parser']['header_row']
    headers = {(cell.sheet_id, cell.column_id): cell.original_text
               for cell in cells if cell.source_row == header_row}
    columns, label_rows = [], []
    for sid, selection in selections.items():
        for start, end in selection.columns:
            for index in range(start, end + 1):
                key = sid, f'c{index}'
                columns.append(TableColumn(schema_version=TableColumn.SCHEMA, sheet_id=sid,
                                           column_id=key[1], source_index=index,
                                           label=headers.get(key, '')))
                label_rows.append(header_row if key in headers else None)
    require(set(coverage) == {'parse', 'rule', 'semantic', 'combination'}, ReasonCode.UNKNOWN_FIELD)
    parsed = coverage['parse']
    require(set(parsed) == {
        'status', 'unit', 'target_count', 'processed_count', 'failed_count', 'skipped_count',
        'ratio', 'excluded_locations', 'processed_locations',
    }, ReasonCode.UNKNOWN_FIELD)
    require(parsed['status'] == 'complete' and parsed['unit'] == 'cell' and
            parsed['target_count'] == parsed['processed_count'] == len(cells) and
            parsed['failed_count'] == parsed['skipped_count'] == 0 and
            parsed['ratio'] == (1 if cells else None))
    require(parsed['processed_locations'] == [[cell.sheet_id, cell.row, cell.column]
                                             for cell in result.cells], ReasonCode.INVALID_COORDINATE)
    excluded = set()
    for item in parsed['excluded_locations']:
        require(set(item) == {'sheet_id', 'row', 'column', 'reason'}, ReasonCode.UNKNOWN_FIELD)
        require(item['reason'] == 'HEADER_EXCLUDED' and item['row'] == header_row and
                not result.scope.include_header and item['sheet_id'] in selections,
                ReasonCode.INVALID_COORDINATE)
        selection = selections[item['sheet_id']]
        require(any(start <= item['row'] <= end for start, end in selection.rows) and
                any(start <= item['column'] <= end for start, end in selection.columns),
                ReasonCode.INVALID_COORDINATE)
        excluded.add((item['sheet_id'], item['row'], item['column']))
    selected_count = sum(sum(end - start + 1 for start, end in item.rows) *
                         sum(end - start + 1 for start, end in item.columns)
                         for item in selections.values())
    require(len(excluded) == len(parsed['excluded_locations']) and
            len(cells) + len(excluded) == selected_count and
            not excluded.intersection((cell.sheet_id, cell.row, cell.column) for cell in result.cells),
            ReasonCode.INVALID_COORDINATE)
    for layer in ('rule', 'semantic', 'combination'):
        require(coverage[layer] == dict(status='not_run', target_count=None, processed_count=0,
                                       ratio=None, reason='DETECTION_NOT_STARTED'))
    require(set(result.warnings) <= {'NON_CELL_CONTENT_EXCLUDED', 'FORMULA_CACHES_NOT_SCANNED',
                                    'CHARACTER_MAPPING_UNRELIABLE'}, ReasonCode.UNSUPPORTED_FORMAT)
    require(result.excluded_contents == (() if csv else (
        'comments', 'hyperlink_targets', 'textboxes', 'images', 'formula_cached_values',
    )), ReasonCode.UNSUPPORTED_FORMAT)
    snapshot = TableSnapshot(
        schema_version=TableSnapshot.SCHEMA, asset_version=result.asset_version_id,
        input_hash=result.input_content_hash.removeprefix('sha256:'), media_type=media_type,
        sheet_ids=tuple(selections), columns=tuple(columns), cells=tuple(cells),
        coverage=Coverage(schema_version=Coverage.SCHEMA, unit=Unit.CELL,
                          total=len(cells) + len(parsed['excluded_locations']), eligible=len(cells),
                          processed=len(cells), excluded=len(parsed['excluded_locations']),
                          failed=0, unknown=0, unscanned=0, version=ADAPTER_VERSION),
        limits=limits, coordinate_version='source-codepoint-half-open.v1',
    )
    tree = FrozenJSON(dict(
        schema_version=SCHEMA_VERSION, adapter_version=ADAPTER_VERSION,
        snapshot=snapshot.to_wire(include_payload=True),
        source=dict(parser_version=result.parser_version, config=config, config_hash=result.config_hash,
                    scope=primitive(asdict(result.scope)), scope_hash=result.scope_hash,
                    structures=structures, coverage=coverage, warnings=list(result.warnings),
                    excluded_contents=list(result.excluded_contents), cell_metadata=cell_metadata,
                    column_label_rows=label_rows),
    ), max_depth=limits.max_json_depth, max_nodes=limits.max_json_nodes,
        max_fields=limits.max_json_fields, max_text_chars=limits.max_text_chars,
        max_bytes=limits.max_json_bytes)
    return BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.JSON,
                          media_type=MediaType.JSON, text=None, binary=None, tree=tree, limits=limits)
