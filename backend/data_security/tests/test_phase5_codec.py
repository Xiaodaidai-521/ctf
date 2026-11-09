"""Synthetic-only normal, boundary and refusal goldens for the M8 codec."""
import csv
import hashlib
import io
import unittest
import zipfile
from dataclasses import replace
from unittest.mock import patch

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment

from data_security.contracts import (BASELINE_LIMITS, BoundedPayload, MediaType, PayloadKind,
    ProtectionError, ReasonCode, TableSnapshot)
from data_security.adapters.tabular.codec import FORMULA_PREFIXES, TableCodec, neutralize_formula
from data_security.adapters.tabular.column_v1 import PlanError, transform_columns
from data_security.application.legacy_tabular import fixed_replace


def binary(content, media=MediaType.CSV, limits=BASELINE_LIMITS):
    return BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
        media_type=media, text=None, tree=None, binary=content, limits=limits)


def xlsx(rows, change=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Synthetic'
    for row in rows:
        sheet.append(row)
    if change:
        change(sheet)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def rewrite(content, member, change):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(output, 'w') as target:
        for item in source.infolist():
            value = source.read(item.filename)
            target.writestr(item.filename, change(value) if item.filename == member else value)
    return output.getvalue()


class CodecGoldenTests(unittest.TestCase):
    def parse(self, content, media=MediaType.CSV, limits=BASELINE_LIMITS):
        codec = TableCodec(asset_version='synthetic-v1')
        return codec, codec.parse(binary(content, media), limits)

    def test_csv_normal_exact_coordinates_bytes_and_hash(self):
        content = 'name,note\n合成😀,"=1+1\n第二行"\n'.encode()
        codec, snapshot = self.parse(content)
        self.assertIsInstance(snapshot, TableSnapshot)
        self.assertEqual(snapshot.input_hash, hashlib.sha256(content).hexdigest())
        self.assertEqual(snapshot.cells[2].source_spans, ((0, 1), (1, 2), (2, 3)))
        self.assertEqual(snapshot.cells[3].source_row, 2)
        expected = 'name,note\n合成😀,"\'=1+1\n第二行"\n'.encode()
        actual = codec.serialize(snapshot, BASELINE_LIMITS)
        self.assertEqual(actual.binary, expected)
        self.assertEqual(hashlib.sha256(actual.binary).hexdigest(), hashlib.sha256(expected).hexdigest())

    def test_csv_boundary_header_only_bom_and_each_formula_prefix(self):
        for prefix in FORMULA_PREFIXES:
            with self.subTest(prefix=repr(prefix)):
                output = io.StringIO(newline='')
                csv.writer(output, lineterminator='\n').writerow([prefix + 'x'])
                codec, snapshot = self.parse(b'\xef\xbb\xbf' + output.getvalue().encode())
                self.assertIsInstance(snapshot, TableSnapshot)
                protected = codec.serialize(snapshot, BASELINE_LIMITS)
                self.assertEqual(list(csv.reader(io.StringIO(protected.binary.decode()))), [["'" + prefix + 'x']])
        self.assertEqual(neutralize_formula("'=x"), "'=x")

    def test_csv_rejection_encoding_width_and_forged_type(self):
        for value in (b'\xff\xfe', b'h,n\na\n', b'%PDF-1.4\nnot,csv\n', b'h\n\0\n'):
            with self.subTest(value_hash=hashlib.sha256(value).hexdigest()):
                self.assertIsInstance(self.parse(value)[1], ProtectionError)
        self.assertIsInstance(self.parse(xlsx([['h'], ['v']]))[1], ProtectionError)

    def test_csv_header_collision_refused_at_output(self):
        codec, snapshot = self.parse(b"=x,'=x\na,b\n")
        self.assertIsInstance(codec.serialize(snapshot, BASELINE_LIMITS), ProtectionError)

    def test_xlsx_normal_readonly_and_deterministic_inert_output(self):
        content = xlsx([['name', 'note'], ['synthetic', '+1']])
        with patch('data_security.adapters.tabular.codec.load_workbook', wraps=load_workbook) as loader:
            codec, snapshot = self.parse(content, MediaType.XLSX)
            self.assertTrue(loader.call_args.kwargs['read_only'])
        self.assertIsInstance(snapshot, TableSnapshot)
        self.assertEqual(codec.sheet_names, (('xlsx:0', 'Synthetic'),))
        first = codec.serialize(snapshot, BASELINE_LIMITS)
        self.assertEqual(first, codec.serialize(snapshot, BASELINE_LIMITS))
        workbook = load_workbook(io.BytesIO(first.binary), data_only=False)
        self.assertEqual(list(workbook.active.values), [('name', 'note'), ('synthetic', "'+1")])
        self.assertEqual(workbook.active['B2'].data_type, 's')
        workbook.close()

    def test_xlsx_boundary_sparse_tail_and_false_dimension(self):
        content = xlsx([['name', 'note'], ['synthetic', None]])
        content = rewrite(content, 'xl/worksheets/sheet1.xml',
            lambda x: x.replace(b'ref="A1:B2"', b'ref="A1:A1"'))
        _, snapshot = self.parse(content, MediaType.XLSX)
        self.assertIsInstance(snapshot, TableSnapshot)
        self.assertEqual(len(snapshot.cells), 4)
        self.assertEqual(snapshot.cells[-1].original_text, '')

    def test_xlsx_rejects_hidden_merged_formula_comments_and_links(self):
        cases = (
            lambda s: setattr(s.row_dimensions[2], 'hidden', True),
            lambda s: setattr(s.column_dimensions['B'], 'hidden', True),
            lambda s: setattr(s.sheet_format, 'zeroHeight', True),
            lambda s: s.merge_cells('A2:B2'),
            lambda s: setattr(s['B2'], 'value', '=1+1'),
            lambda s: setattr(s['B2'], 'comment', Comment('synthetic', 'fixture')),
            lambda s: setattr(s['B2'], 'hyperlink', 'https://example.invalid'),
        )
        for change in cases:
            with self.subTest(change=change):
                self.assertIsInstance(self.parse(xlsx([['h', 'n'], ['a', 'b']], change), MediaType.XLSX)[1], ProtectionError)

    def test_xlsx_explicit_zero_height_or_width_is_not_made_visible(self):
        content = xlsx([['h', 'n'], ['a', 'b']])
        for old, new in ((b'<row r="2">', b'<row r="2" ht="0" customHeight="1">'),
                         (b'<sheetData>', b'<cols><col min="2" max="2" width="0" customWidth="1"/></cols><sheetData>')):
            hidden = rewrite(content, 'xl/worksheets/sheet1.xml', lambda data: data.replace(old, new))
            self.assertIsInstance(self.parse(hidden, MediaType.XLSX)[1], ProtectionError)

    def test_xlsx_declared_worksheet_relationships_cannot_disappear_or_alias(self):
        content = xlsx([['first'], ['value']], lambda s: s.parent.create_sheet('Second').append(['second']))
        for old, new in ((b'sheet1.xml', b'absent.xml'), (b'sheet2.xml', b'sheet1.xml')):
            broken = rewrite(content, 'xl/_rels/workbook.xml.rels', lambda data: data.replace(old, new))
            result = self.parse(broken, MediaType.XLSX)[1]
            self.assertIsInstance(result, ProtectionError)
            self.assertEqual(result.code, ReasonCode.UNSUPPORTED_FORMAT)

    def test_xlsx_preserves_numeric_lexemes_and_boolean_source_text(self):
        content = xlsx([['number', 'boolean'], [1.23, True]])
        content = rewrite(content, 'xl/worksheets/sheet1.xml', lambda data: data.replace(b'<v>1.23</v>', b'<v>1.2300</v>'))
        _, snapshot = self.parse(content, MediaType.XLSX)
        self.assertIsInstance(snapshot, TableSnapshot)
        self.assertEqual([c.original_text for c in snapshot.cells], ['number', 'boolean', '1.2300', 'true'])
        self.assertEqual(snapshot.cells[2].source_spans, tuple((i, i + 1) for i in range(6)))

    def test_xlsx_bad_shared_string_reference_is_a_fixed_refusal(self):
        content = rewrite(xlsx([['h'], [1]]), 'xl/worksheets/sheet1.xml',
            lambda data: data.replace(b't="n"><v>1</v>', b't="s"><v>9</v>'))
        result = self.parse(content, MediaType.XLSX)[1]
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(result.code, ReasonCode.UNSUPPORTED_FORMAT)

    def test_xlsx_rejects_entities_and_unknown_package(self):
        content = xlsx([['h'], ['v']])
        content = rewrite(content, 'xl/workbook.xml',
            lambda value: b'<!DOCTYPE workbook [<!ENTITY x "synthetic">]>' + value)
        self.assertIsInstance(self.parse(content, MediaType.XLSX)[1], ProtectionError)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('not-a-workbook.txt', 'fixture')
        self.assertIsInstance(self.parse(archive.getvalue(), MediaType.XLSX)[1], ProtectionError)

    def test_limits_rows_columns_cells_text_bytes_zip_and_expansion(self):
        csv_content = b'head,note\nvalue,other\n'
        xlsx_content = xlsx([['head', 'note'], ['value', 'other']])
        for field, cap in (('max_rows', 1), ('max_columns', 1), ('max_cells', 3),
                           ('max_text_chars', 3), ('max_bytes', 8)):
            limits = replace(BASELINE_LIMITS, **{field: cap})
            for media, content in ((MediaType.CSV, csv_content), (MediaType.XLSX, xlsx_content)):
                with self.subTest(field=field, media=media):
                    result = self.parse(content, media, limits)[1]
                    self.assertIsInstance(result, ProtectionError)
                    self.assertEqual(result.code, ReasonCode.LIMIT_EXCEEDED)
        for field in ('max_zip_members', 'max_expanded_bytes'):
            result = self.parse(xlsx_content, MediaType.XLSX, replace(BASELINE_LIMITS, **{field: 1}))[1]
            self.assertEqual(result.code, ReasonCode.LIMIT_EXCEEDED)

    def test_serialization_refuses_unknown_coverage_and_identity(self):
        codec, snapshot = self.parse(b'h\nv\n')
        coverage = replace(snapshot.coverage, processed=1, unknown=1)
        self.assertEqual(codec.serialize(replace(snapshot, coverage=coverage), BASELINE_LIMITS).code,
                         ReasonCode.SCOPE_INCOMPLETE)
        self.assertEqual(codec.serialize(replace(snapshot, asset_version='other'), BASELINE_LIMITS).code,
                         ReasonCode.HASH_MISMATCH)

    def test_serialization_rejects_gaps_instead_of_compacting_source_rows(self):
        codec, snapshot = self.parse(b'h\nx\ny\n')
        selected = (snapshot.cells[0], snapshot.cells[2])
        coverage = replace(snapshot.coverage, total=2, eligible=2, processed=2)
        result = codec.serialize(replace(snapshot, cells=selected, coverage=coverage), BASELINE_LIMITS)
        self.assertEqual(result.code, ReasonCode.UNSUPPORTED_SCOPE)

    def test_xlsx_output_text_limit_refuses_silent_openpyxl_truncation(self):
        codec, snapshot = self.parse(xlsx([['h'], ['v']]), MediaType.XLSX)
        text = 'a' * 32768
        cell = replace(snapshot.cells[-1], original_text=text, normalized_text=text,
                       source_spans=tuple((i, i + 1) for i in range(len(text))))
        result = codec.serialize(replace(snapshot, cells=(snapshot.cells[0], cell)), BASELINE_LIMITS)
        self.assertEqual(result.code, ReasonCode.LIMIT_EXCEEDED)


class ColumnFacadeTests(unittest.TestCase):
    def test_legacy_fixed_uses_injected_action_and_preserves_scope_order(self):
        for media in ('csv', 'xlsx'):
            plan = {'version': '1', 'format': media, 'scope': {'columns': ['b', 'a']},
                    'operations': [{'type': 'mask_columns', 'columns': ['b'], 'value': '***'}]}
            if media == 'xlsx':
                plan['scope']['worksheets'] = ['Synthetic']
            content = b'a,b,c\nx,y,z\n' if media == 'csv' else xlsx([['a', 'b', 'c'], ['x', 'y', 'z']])
            with patch('data_security.core.redaction.fixed_replace', wraps=fixed_replace) as operation:
                output, count = transform_columns(content, media, plan, 'mask', BASELINE_LIMITS, operation)
            self.assertEqual(count, 1)
            operation.assert_called_once_with('y', '***')
            if media == 'csv':
                self.assertEqual(output, b'b,a\n***,x\n')
            else:
                workbook = load_workbook(io.BytesIO(output))
                self.assertEqual(list(workbook.active.values), [('b', 'a'), ('***', 'x')])
                workbook.close()

    def test_xlsx_illegal_fixed_text_never_escapes_in_parser_exception(self):
        plan = {'version': '1', 'format': 'xlsx', 'scope': {'columns': ['a'], 'worksheets': ['Synthetic']},
                'operations': [{'type': 'mask_columns', 'columns': ['a'], 'value': 'synthetic\u0001value'}]}
        with self.assertRaises(PlanError) as caught:
            transform_columns(xlsx([['a'], ['v']]), 'xlsx', plan, 'mask', BASELINE_LIMITS, fixed_replace)
        self.assertEqual(str(caught.exception), 'UNSUPPORTED_FORMAT')
        self.assertTrue(caught.exception.unsupported)

    def test_legacy_refuses_duplicates_extra_fields_and_empty_output(self):
        plan = {'version': '1', 'format': 'csv', 'scope': {'columns': ['a']}, 'operations': []}
        with self.assertRaises(PlanError):
            transform_columns(b'a,a\nx,y\n', 'csv', plan, 'allow', BASELINE_LIMITS, fixed_replace)
        for change in ({'new_action': 'mask_span'}, {'operations': [{'type': 'drop_columns', 'columns': ['a']}]}):
            with self.assertRaises(PlanError):
                transform_columns(b'a\nx\n', 'csv', {**plan, **change}, 'allow', BASELINE_LIMITS, fixed_replace)
