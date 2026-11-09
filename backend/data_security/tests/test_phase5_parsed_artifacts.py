"""Pure synthetic tests for the private parse-result governance boundary."""
import hashlib
import io
import json
import subprocess
import sys
import unittest
from dataclasses import replace

from openpyxl import Workbook

from data_security.adapters.tabular.parsed_artifacts import (
    ADAPTER_VERSION, SCHEMA_VERSION, govern_parse_result,
)
from data_security.contracts.enums import ReasonCode
from data_security.contracts.payloads import BASELINE_LIMITS, TableSnapshot
from data_security.contracts.schema import ContractViolation
from mainline1.parsing import AssetRef, ParserConfig, Scope, Selection, fingerprint, parse_table


def parsed_csv(content=b'header\nsynthetic\n', **kwargs):
    asset = AssetRef('synthetic-v1', 'test-domain', 'sha256:' + hashlib.sha256(content).hexdigest(),
                     'csv', len(content), 'private:synthetic')
    return parse_table(content, asset, **kwargs)


def parsed_xlsx(configure):
    book = Workbook()
    configure(book)
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    content = stream.getvalue()
    asset = AssetRef('synthetic-v1', 'test-domain', 'sha256:' + hashlib.sha256(content).hexdigest(),
                     'xlsx', len(content), 'private:synthetic')
    return parse_table(content, asset)


class ParsedArtifactTests(unittest.TestCase):
    def govern(self, result, limits=BASELINE_LIMITS):
        return govern_parse_result(result, limits=limits).tree.to_value()

    def rejects(self, result, code, limits=BASELINE_LIMITS):
        with self.assertRaises(ContractViolation) as found:
            self.govern(result, limits)
        self.assertEqual(found.exception.code, code)
        self.assertEqual(str(found.exception), code.value)

    def test_private_versioned_snapshot_and_no_raw_payload_duplicate(self):
        parsed = parsed_csv()
        governed = govern_parse_result(parsed, limits=BASELINE_LIMITS)
        value = governed.tree.to_value()
        self.assertEqual(set(value), {'schema_version', 'adapter_version', 'snapshot', 'source'})
        self.assertEqual((value['schema_version'], value['adapter_version']), (SCHEMA_VERSION, ADAPTER_VERSION))
        snapshot = TableSnapshot.from_wire(value['snapshot'])
        self.assertEqual(snapshot.asset_version, parsed.asset_version_id)
        self.assertEqual(snapshot.input_hash, parsed.input_content_hash[7:])
        self.assertEqual(snapshot.cells[0].original_text, 'synthetic')
        self.assertEqual(snapshot.columns[0].label, '')
        self.assertEqual(value['source']['column_label_rows'], [None])
        self.assertEqual(value['source']['scope_hash'], parsed.scope_hash)
        self.assertEqual(value['source']['config_hash'], parsed.config_hash)
        self.assertEqual(value['source']['coverage'], json.loads(parsed.coverage_json))
        self.assertEqual((snapshot.coverage.total, snapshot.coverage.excluded), (2, 1))
        self.assertNotIn('synthetic', repr(governed))
        self.assertNotIn('source_text', json.dumps(value))
        self.assertNotIn('cells', value['source'])
        self.assertNotIn('config_json', value['source'])
        with self.assertRaises(ContractViolation):
            governed.to_wire()
        self.assertEqual(value, self.govern(parsed))

    def test_multiline_unicode_original_coordinates_and_duplicate_headers(self):
        content = '重复,重复,\r\n"甲\r\n😀",Ａéﬃ,\r\n'.encode()
        result = self.govern(parsed_csv(content, config=ParserConfig(
            include_header=True, normalization='nfkc-mapped-v1')))
        table = TableSnapshot.from_wire(result['snapshot'])
        self.assertEqual([column.label for column in table.columns], ['重复', '重复', ''])
        self.assertEqual([column.column_id for column in table.columns], ['c1', 'c2', 'c3'])
        self.assertEqual(result['source']['column_label_rows'], [1, 1, 1])
        cell = table.cells[3]
        self.assertEqual((cell.source_row, cell.logical_record, cell.original_text), (2, 2, '甲\r\n😀'))
        normalized = table.cells[4]
        self.assertEqual(normalized.original_text, 'Ａéﬃ')
        self.assertEqual(normalized.normalized_text, 'Aéffi')
        self.assertEqual(normalized.source_spans, ((0, 1), (1, 3), (3, 4), (3, 4), (3, 4)))

    def test_unproven_mapping_is_preserved_without_inventing_offsets(self):
        value = self.govern(parsed_csv('h\n가\n'.encode(), config=ParserConfig(normalization='nfkc-mapped-v1')))
        cell = TableSnapshot.from_wire(value['snapshot']).cells[0]
        self.assertEqual((cell.original_text, cell.normalized_text), ('가', '가'))
        self.assertFalse(cell.mapping_proven)
        self.assertEqual(cell.source_spans, ())
        self.assertEqual(value['source']['warnings'], ['CHARACTER_MAPPING_UNRELIABLE'])

    def test_projection_does_not_renumber_or_expand_scope(self):
        scope = Scope('synthetic-v1', (Selection('csv:0', ((3, 3),), ((2, 2),)),))
        value = self.govern(parsed_csv(b'a,b\n1,2\n3,4\n', scope=scope))
        snapshot = TableSnapshot.from_wire(value['snapshot'])
        self.assertEqual([(cell.source_row, cell.column_id, cell.original_text) for cell in snapshot.cells],
                         [(3, 'c2', '4')])
        self.assertEqual([(column.source_index, column.label) for column in snapshot.columns], [(2, '')])
        self.assertEqual(value['source']['scope']['selections'][0]['rows'], [[3, 3]])
        self.assertEqual(snapshot.coverage.total, 1)

    def test_no_header_and_header_only_exclusion_are_explicit(self):
        without = self.govern(parsed_csv(b'0012\n', config=ParserConfig(header_row=None)))
        self.assertEqual(without['source']['column_label_rows'], [None])
        self.assertEqual(without['snapshot']['cells'][0]['original_text'], '0012')
        only = self.govern(parsed_csv(b'header\n'))
        self.assertEqual(only['snapshot']['cells'], [])
        self.assertEqual(only['snapshot']['coverage']['excluded'], 1)

    def test_xlsx_source_types_formats_and_names_survive(self):
        def configure(book):
            sheet = book.active
            sheet.title = '合成工作表'
            sheet.append(['h', 'h', 'h', 'h'])
            sheet.append([12, True, '', None])
            sheet['A2'].number_format = '0000'
            other = book.create_sheet('other')
            other.append(['h'])
            other.append(['text'])
        result = parsed_xlsx(configure)
        value = self.govern(result)
        self.assertEqual(value['snapshot']['sheet_ids'], ['xlsx:0', 'xlsx:1'])
        self.assertEqual([cell['original_text'] for cell in value['snapshot']['cells']], ['12', 'true', '', '', 'text'])
        self.assertEqual([cell['value_type'] for cell in value['source']['cell_metadata']],
                         ['number', 'boolean', 'text', 'missing', 'text'])
        self.assertEqual(value['source']['cell_metadata'][0]['number_format'], '0000')
        self.assertEqual(value['source']['structures'], json.loads(result.structure_json))
        self.assertEqual(value['source']['excluded_contents'], list(result.excluded_contents))

    def test_xlsx_hidden_merged_and_formula_content_is_not_flattened(self):
        for feature in ('row', 'column', 'sheet', 'merge', 'formula'):
            def configure(book):
                sheet = book.active
                sheet.append(['a', 'b'])
                sheet.append(['x', 'y'])
                if feature == 'row':
                    sheet.row_dimensions[2].hidden = True
                elif feature == 'column':
                    sheet.column_dimensions['B'].hidden = True
                elif feature == 'sheet':
                    book.create_sheet('hidden').sheet_state = 'hidden'
                elif feature == 'merge':
                    sheet.merge_cells('A2:B2')
                else:
                    sheet['B2'] = '=1+1'
            with self.subTest(feature=feature):
                self.rejects(parsed_xlsx(configure), ReasonCode.UNSUPPORTED_FORMAT)

    def test_unknown_parser_metadata_and_scope_drift_are_rejected(self):
        result = parsed_csv()
        self.rejects(replace(result, parser_version='internal-table-future'), ReasonCode.UNKNOWN_SCHEMA)
        self.rejects(replace(result, scope_hash='sha256:' + '0' * 64), ReasonCode.INVALID_VALUE)
        structures = json.loads(result.structure_json)
        structures[0]['raw_payload'] = 'not a governed coordinate'
        self.rejects(replace(result, structure_json=json.dumps(structures)), ReasonCode.UNKNOWN_FIELD)
        self.rejects(replace(result, cells=result.cells * 2), ReasonCode.INVALID_VALUE)

    def test_incomplete_scope_and_forged_exclusions_cannot_claim_complete_coverage(self):
        result = parsed_csv()
        coverage = json.loads(result.coverage_json)
        coverage['parse'].update(target_count=0, processed_count=0, processed_locations=[], ratio=None)
        self.rejects(replace(result, cells=(), coverage_json=json.dumps(coverage)), ReasonCode.INVALID_COORDINATE)
        for key, value in (('sheet_id', 'csv:9'), ('column', 2), ('row', 2)):
            coverage = json.loads(result.coverage_json)
            coverage['parse']['excluded_locations'][0][key] = value
            self.rejects(replace(result, coverage_json=json.dumps(coverage)), ReasonCode.INVALID_COORDINATE)

    def test_unicode_version_drift_is_rejected_before_remapping(self):
        result = parsed_csv()
        config = json.loads(result.config_json)
        config['unicode_version'] = 'unknown-version'
        self.rejects(replace(result, config_json=json.dumps(config), config_hash=fingerprint(config)),
                     ReasonCode.UNKNOWN_SCHEMA)

    def test_all_explicit_m0_limits_apply_to_complete_representation(self):
        result = parsed_csv(b'a,b\nx,y\n')
        for key, cap in (('max_rows', 1), ('max_columns', 1), ('max_cells', 3),
                         ('max_bytes', 1), ('max_json_depth', 2), ('max_json_nodes', 2),
                         ('max_json_fields', 2), ('max_json_bytes', 1)):
            with self.subTest(limit=key):
                self.rejects(result, ReasonCode.LIMIT_EXCEEDED, replace(BASELINE_LIMITS, **{key: cap}))
        self.rejects(parsed_csv(), ReasonCode.LIMIT_EXCEEDED, replace(BASELINE_LIMITS, max_text_chars=2))
        multiple = parsed_xlsx(lambda book: (book.active.append(['h']), book.create_sheet('other').append(['h'])))
        self.rejects(multiple, ReasonCode.LIMIT_EXCEEDED, replace(BASELINE_LIMITS, max_sheets=1))

    def test_json_byte_limit_includes_metadata_not_just_cell_text(self):
        def configure(book):
            book.active.append(['h'] * 12)
            book.active.append([1] * 12)
            for cell in book.active[2]:
                cell.number_format = '数' * 30_000
        # Real XLSX formats are metadata, but their aggregate representation is still bounded.
        self.rejects(parsed_xlsx(configure), ReasonCode.LIMIT_EXCEEDED)

    def test_json_byte_boundary_and_snapshot_round_trip(self):
        result = parsed_csv()
        initial = self.govern(result)
        size = len(json.dumps(initial, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
        # The limits themselves are in the persisted snapshot, so find the stable exact size.
        while True:
            generous = replace(BASELINE_LIMITS, max_json_bytes=size + 100)
            value = self.govern(result, generous)
            actual = len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
            if actual == size:
                break
            size = actual
        value = self.govern(result, replace(BASELINE_LIMITS, max_json_bytes=size))
        self.assertEqual(len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()), size)
        self.rejects(result, ReasonCode.LIMIT_EXCEEDED, replace(BASELINE_LIMITS, max_json_bytes=size - 1))
        restored = TableSnapshot.from_wire(value['snapshot'])
        self.assertEqual(restored.to_wire(include_payload=True), value['snapshot'])

    def test_bridge_imports_without_django_or_network(self):
        script = '''import sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'django', 'socket', 'requests', 'httpx'}:
            raise RuntimeError('FORBIDDEN_IMPORT')
sys.meta_path.insert(0, Block())
from data_security.adapters.tabular.parsed_artifacts import govern_parse_result
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
