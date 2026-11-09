"""Codec -> retained source mapping -> M1 -> codec, using only fictitious approvals."""
import csv
from dataclasses import replace
from datetime import datetime
import hashlib
import io
import unittest
from unittest.mock import patch
import zipfile

from openpyxl import Workbook, load_workbook

from data_security.adapters.tabular.codec import CODEC_VERSION, TableCodec
from data_security.adapters.tabular.parsed_artifacts import govern_parse_result
from data_security.contracts import BASELINE_LIMITS, FrozenJSON, MediaType, TableSnapshot, ActionPlan
from data_security.core.redaction import apply_actions
from data_security.tests.test_phase5_codec import binary
from data_security.tests.test_source_plans import ASSET, convert, fixture, rebind
from mainline1.parsing import AssetRef, ParserConfig, parse_table


def pipeline_fixture(kind, fmt):
    f = fixture(kind, fmt)
    rows = [('Email', 'Notes', 'Remove'), ('Ａ🙂é a@example.invalid', '=1+1', 'unused'),
            ('b@example.invalid', 'quoted\nrecord', 'unused')]
    if fmt == 'csv':
        output = io.StringIO(newline='')
        csv.writer(output, lineterminator='\n').writerows(rows)
        content = output.getvalue().encode()
    else:
        workbook = Workbook()
        workbook.remove(workbook.active)
        workbook.properties.created = workbook.properties.modified = datetime(2000, 1, 1)
        for name in ('明细', 'Archive'):
            sheet = workbook.create_sheet(name)
            for row in rows:
                sheet.append(row)
                for cell in sheet[sheet.max_row]:
                    cell.data_type = 's'
        output = io.BytesIO()
        workbook.save(output)
        fixed = io.BytesIO()
        with zipfile.ZipFile(output) as source, zipfile.ZipFile(fixed, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(source.namelist()):
                info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                data = source.read(name)
                if name == 'docProps/core.xml':
                    data = data.replace(workbook.properties.modified.isoformat(timespec='seconds').encode(),
                                        b'2000-01-01T00:00:00')
                archive.writestr(info, data)
        content = fixed.getvalue()
    codec = TableCodec(asset_version=ASSET)
    snapshot = codec.parse(binary(content, MediaType.CSV if fmt == 'csv' else MediaType.XLSX), BASELINE_LIMITS)
    assert isinstance(snapshot, TableSnapshot)
    f.options['input_hash'] = snapshot.input_hash
    if kind == 'mainline':
        parsed = parse_table(content, AssetRef(ASSET, 'synthetic-test-domain', 'sha256:' + snapshot.input_hash,
            fmt, len(content), 'private:synthetic'), config=ParserConfig(include_header=True))
        governed = govern_parse_result(parsed, limits=BASELINE_LIMITS).tree.to_value()
        owner_snapshot = TableSnapshot.from_wire(governed['snapshot'])
        assert owner_snapshot.cells == snapshot.cells
        f.snapshot = owner_snapshot
        source = governed['source']
        f.doc['asset']['content_hash'] = 'sha256:' + snapshot.input_hash
        f.doc['parser_config_hash'] = source['config_hash']
        f.options['source_binding'] = replace(f.options['source_binding'], parser_config_hash=source['config_hash'])
        f.options['snapshot_source'] = FrozenJSON(source)
    else:
        f.snapshot = snapshot
    rebind(f)
    plan = convert(f)
    assert isinstance(plan, ActionPlan)
    protected = apply_actions(f.snapshot, plan.actions, BASELINE_LIMITS)
    # Output projection is explicit scope order, not a new source coordinate system.
    order = [(s.sheet_id, column) for s in plan.scope.sheets for column in s.column_ids]
    columns = {(c.sheet_id, c.column_id): c for c in protected.columns}
    protected = replace(protected, sheet_ids=tuple(s.sheet_id for s in plan.scope.sheets),
        columns=tuple(columns[key] for key in order if key in columns))
    output = codec.serialize(protected, BASELINE_LIMITS)
    return f, plan, output.binary, content


OUTPUT_HASHES = {
    'mainline-csv': 'c69e2a0936892291d429cc6327cee7412aa5a61248ff714b95a454a94a426a3f',
    'mainline-xlsx': '52c6d4e6f973f915663a0fd21a856eab3f1007917a5a327b1b77f01cd92ca00c',
    'legacy-csv': 'c2ece38380a706359d5345bf92b90216a458b670bda70e6118738f3344697b8d',
    'legacy-xlsx': '27406ac323f8dbd1d05662e571cf74edfbf2f0e30bb2df1b96c8f17b5837e0ee',
}


class PipelineGoldens(unittest.TestCase):
    def test_xlsx_input_plan_and_output_hashes_do_not_depend_on_save_clock(self):
        for kind in ('mainline', 'legacy'):
            observations = []
            for instant in (datetime(2001, 1, 1), datetime(2002, 2, 2)):
                with patch('openpyxl.writer.excel.datetime') as clock:
                    clock.datetime.now.return_value = instant
                    _, plan, output, content = pipeline_fixture(kind, 'xlsx')
                observations.append((hashlib.sha256(content).hexdigest(), plan.plan_hash,
                                     hashlib.sha256(output).hexdigest()))
            self.assertEqual(observations[0], observations[1])

    def test_real_csv_and_xlsx_bytes_for_both_plan_families(self):
        for kind in ('mainline', 'legacy'):
            for fmt in ('csv', 'xlsx'):
                with self.subTest(kind=kind, format=fmt):
                    f, plan, output, content = pipeline_fixture(kind, fmt)
                    expected = ([('Email', 'Notes'), ('Ａ🙂é [EMAIL]', "'=1+1"), ('[EMAIL]', 'quoted\nrecord')]
                        if kind == 'mainline' else [('Notes', 'Email'), ("'=1+1", '[EMAIL]'), ('quoted\nrecord', '[EMAIL]')])
                    if fmt == 'csv':
                        actual = [tuple(row) for row in csv.reader(io.StringIO(output.decode()))]
                        self.assertEqual(actual, expected)
                    else:
                        workbook = load_workbook(io.BytesIO(output), data_only=False)
                        self.assertEqual(workbook.sheetnames, ['明细', 'Archive'] if kind == 'mainline' else ['Archive', '明细'])
                        self.assertEqual(list(workbook.worksheets[0].values), expected)
                        if kind == 'legacy':
                            self.assertEqual(list(workbook.worksheets[1].values), expected)
                        workbook.close()
                    self.assertEqual(plan.input_hash, hashlib.sha256(content).hexdigest())
                    self.assertEqual(hashlib.sha256(output).hexdigest(), OUTPUT_HASHES[kind + '-' + fmt])
                    self.assertEqual(output, pipeline_fixture(kind, fmt)[2])
                    self.assertIsNone(plan.approval)
