"""Isolated synthetic source-plan goldens; fictitious approvals NEVER leave tests.

Approved solely for phase-five golden fixtures by the user on 2026-11-06.
Snapshots model the codec's source coordinates without importing that codec.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest

from data_security.adapters.tabular.source_plans import (
    ADAPTER_VERSION, LEGACY_HASH_VERSION, MAINLINE_HASH_VERSION, SourcePlanAdapter,
)
from data_security.contracts import (
    ActionPlan, Algorithm, AlgorithmSpec, Approval, BASELINE_LIMITS, Category,
    ContractViolation, Coverage, FrozenJSON, Location, LocationKind, MediaType,
    PolicyBinding, ProtectionError, ReasonCode, Replacement, ResolvedAction,
    SheetScope, SourceDocument, SourceFormat, SourcePlanBinding, SourceTrust,
    TableCell, TableColumn, TableScope, TableSnapshot, Unit, content_hash,
)


AT = datetime(2026, 11, 6, 4, 12, tzinfo=timezone.utc)
ASSET = '20000000-0000-4000-8000-000000000001'
PID = '20000000-0000-4000-8000-000000000002'
TRACE = '20000000-0000-4000-8000-000000000003'
FINDING = '20000000-0000-4000-8000-000000000004'
COORDINATES = 'source-codepoint-half-open.v1'


def dto(cls, **values):
    return cls(schema_version=cls.SCHEMA, **values)


def source_hash(value, *, mainline=False, plan=False):
    value = deepcopy(value)
    if plan:
        value.pop('plan_hash', None)
        value['meta'].pop('trace_id', None)
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return ('sha256:' if mainline else '') + hashlib.sha256(raw).hexdigest()


def location(sheet, column='c1', row=2, kind=LocationKind.CELL, start=None, end=None):
    return dto(Location, kind=kind, sheet_id=sheet, column_id=column, source_row=row,
               start=start, end=end, json_path=())


def action(ref, loc, index):
    algorithm = dto(AlgorithmSpec, algorithm=Algorithm.DROP if loc.kind is LocationKind.COLUMN else Algorithm.REPLACE,
        version='v1', replacement=None if loc.kind is LocationKind.COLUMN else Replacement.EMAIL,
        keep_prefix=None, keep_suffix=None, mask_symbol=None, max_length=None,
        ipv4_prefix=None, pseudonym_bits=None, key_ref=None)
    return dto(ResolvedAction, action_id='action/' + str(index), source_operation_ref=ref, location=loc,
        category=Category.EMAIL, algorithm=algorithm, finding_refs=(FINDING,), requirement_refs=('protect-email',))


def fixture(kind='mainline', fmt='csv'):
    sheets = ('csv:0',) if fmt == 'csv' else ('xlsx:0', 'xlsx:1')
    columns, cells = [], []
    labels = ('Email', 'Notes', 'Remove')
    for sheet in sheets:
        for index, label in enumerate(labels, 1):
            columns.append(dto(TableColumn, sheet_id=sheet, column_id='c' + str(index), source_index=index, label=label))
        for row, values in enumerate((labels, ('Ａ🙂é a@example.invalid', '=1+1', 'unused'),
                                      ('b@example.invalid', 'quoted\nrecord', 'unused')), 1):
            for index, text in enumerate(values, 1):
                cells.append(dto(TableCell, sheet_id=sheet, column_id='c' + str(index), source_row=row,
                    logical_record=row, original_text=text, normalized_text=text,
                    source_spans=tuple((i, i + 1) for i in range(len(text))), mapping_proven=True))
    # This digest is retained synthetic asset identity, not a claim to serialize a workbook here.
    input_hash = hashlib.sha256(('isolated-' + fmt + '-asset-v1').encode()).hexdigest()
    snapshot = dto(TableSnapshot, asset_version=ASSET, input_hash=input_hash,
        media_type=MediaType.CSV if fmt == 'csv' else MediaType.XLSX, sheet_ids=sheets,
        columns=tuple(columns), cells=tuple(cells), limits=BASELINE_LIMITS, coordinate_version=COORDINATES,
        coverage=dto(Coverage, unit=Unit.CELL, total=len(cells), eligible=len(cells), processed=len(cells),
            excluded=0, failed=0, unknown=0, unscanned=0, version='synthetic-coverage-v1'))
    selected = sheets if kind == 'mainline' else tuple(reversed(sheets))
    scope = dto(TableScope, coordinate_version=COORDINATES, sheets=tuple(
        dto(SheetScope, sheet_id=sheet, column_ids=('c1', 'c2', 'c3') if kind == 'mainline' else ('c2', 'c1', 'c3'),
            row_ranges=((1, 3),), includes_header=True) for sheet in selected))
    binding = dto(PolicyBinding, protection_version='synthetic-protection-v1',
        protection_hash=content_hash({'synthetic': 'protection'}), risk_version='synthetic-risk-v1',
        risk_hash=content_hash({'synthetic': 'risk'}), contract_version='ds.m0.v1')
    if kind == 'mainline':
        parser_config = dict(parser=dict(header_row=1))
        scope_doc = dict(asset_version_id=ASSET, include_header=True, selections=[
            dict(sheet_id=s, rows=[[1, 3]], columns=[[1, 3]]) for s in selected])
        requirements = [dict(requirement_id='protect-email', version='synthetic-v1', category_ids=['email_address'],
            allowed_operations=['drop_column', 'mask_cell', 'mask_span'], allow_drop_column=True,
            require_complete_coverage=True, allow_unresolved=False)]
        operations, actions = [], []
        for index, (op_type, target) in enumerate((
                ('mask_span', location(sheets[0], kind=LocationKind.CELL_SPAN, start=5, end=22)),
                ('mask_cell', location(sheets[0], row=3)),
                ('drop_column', location(sheets[0], column='c3', row=None, kind=LocationKind.COLUMN))), 1):
            op_id = '30000000-0000-4000-8000-' + str(index).zfill(12)
            operations.append(dict(operation_id=op_id, type=op_type,
                target=dict(kind={'mask_span': 'span', 'mask_cell': 'cell', 'drop_column': 'column'}[op_type],
                    sheet_id=target.sheet_id, column=int(target.column_id[1:]), row=target.source_row, channel='value',
                    span=dict(start=target.start, end=target.end) if op_type == 'mask_span' else None),
                replacement=None if op_type == 'drop_column' else '[REDACTED]',
                match_ref='private:plan-match:' + PID + ':' + op_id,
                finding_ids=[FINDING], requirement_ids=['protect-email']))
            actions.append(action(op_id, target, index))
        doc = dict(meta=dict(schema_version='mainline1.proposed.v1', trace_id=TRACE,
            environment='test', evaluation_run_id=None, domain_id='synthetic-test-domain', created_at='2026-11-06T04:12:00Z'),
            asset=dict(asset_id=PID, asset_version_id=ASSET, content_hash='sha256:' + input_hash),
            scan_id=TRACE, profile_id=FINDING, scope_hash=source_hash(scope_doc, mainline=True),
            parser_version='internal-table-v2', parser_config_hash=source_hash(parser_config, mainline=True),
            policy_version='synthetic-policy-v1', redaction_policy_version='synthetic-redaction-v1',
            requirements=requirements, requirements_hash=source_hash(requirements, mainline=True),
            operation_contract_version='original-snapshot-v1-proposed', plan_id=PID, operations=operations,
            operation_count=len(operations), unresolved=[], validation_errors=[], status='ready',
            checked_applicability_version=1, validation_ref='private:plan-validation:' + PID)
        doc['plan_hash'] = source_hash(doc, mainline=True, plan=True)
    else:
        scope_doc = dict(columns=['Notes', 'Email', 'Remove'])
        if fmt == 'xlsx':
            scope_doc['worksheets'] = ['Archive', '明细']
        doc = dict(version='1', format=fmt, scope=scope_doc, operations=[
            dict(type='mask_columns', columns=['Email'], strategy='fixed', value='[EMAIL]'),
            dict(type='drop_columns', columns=['Remove']), dict(type='sanitize_formulas')])
        actions = []
        for sheet in selected:
            for row in (2, 3):
                actions.append(action('operations/0', location(sheet, row=row), len(actions) + 1))
        for sheet in selected:
            actions.append(action('operations/1', location(sheet, column='c3', row=None, kind=LocationKind.COLUMN), len(actions) + 1))
    source_binding = dto(SourcePlanBinding,
        source_format=SourceFormat.MAINLINE1 if kind == 'mainline' else SourceFormat.COLUMN_V1,
        source_version='mainline1.proposed.v1' if kind == 'mainline' else '1',
        source_plan_hash=doc['plan_hash'] if kind == 'mainline' else source_hash(doc),
        source_record_ref='synthetic/source-plan', source_record_version='v1', source_trust=SourceTrust.SYNTHETIC,
        provenance_ref='synthetic/provenance', approval_basis_ref='synthetic/approval', approval_basis_version='v1',
        source_state='ready' if kind == 'mainline' else 'not-declared', source_environment='test',
        source_domain='synthetic-test-domain', evaluation_ref=None,
        scope_hash=source_hash(scope_doc, mainline=kind == 'mainline'),
        parser_version=doc.get('parser_version'), parser_config_hash=doc.get('parser_config_hash'),
        requirements_hash=doc.get('requirements_hash'), operation_contract_version=doc.get('operation_contract_version'))
    source_approval = dto(Approval, approval_ref='synthetic/approval', requested_by='synthetic/requester',
        approved_by='synthetic/reviewer', approved_at=AT, content_hash=source_binding.source_plan_hash.removeprefix('sha256:'))
    return SimpleNamespace(doc=doc, snapshot=snapshot, actions=tuple(actions), binding=binding,
        options=dict(source_binding=source_binding, source_approval=source_approval, scope=scope,
            asset_version=ASSET, input_hash=input_hash, plan_id='synthetic/action-plan', created_at=AT,
            expires_at=AT + timedelta(minutes=30), sheet_names=() if fmt == 'csv' else (('xlsx:0', '明细'), ('xlsx:1', 'Archive')),
            snapshot_source=FrozenJSON(dict(parser_version='internal-table-v2', config=parser_config,
                config_hash=doc['parser_config_hash'],
                structures=[dict(sheet_id=sheet, rows=3, columns=3) for sheet in sheets]))
                if kind == 'mainline' else None))


def rebind(f):
    """Explicitly fictitious approval for a modified negative-test source document."""
    mainline = 'meta' in f.doc
    if mainline:
        f.doc['plan_hash'] = source_hash(f.doc, mainline=True, plan=True)
    value = f.doc['plan_hash'] if mainline else source_hash(f.doc)
    f.options['source_binding'] = replace(f.options['source_binding'], source_plan_hash=value)
    f.options['source_approval'] = replace(f.options['source_approval'], content_hash=value.removeprefix('sha256:'))


def convert(f, *, doc=None, actions=None, snapshot=None, **options):
    retained = f.options['source_binding']
    source = dto(SourceDocument, source_format=retained.source_format, source_version=retained.source_version,
                 document=FrozenJSON(f.doc if doc is None else doc))
    return SourcePlanAdapter(**(f.options | options)).to_action_plan(source, snapshot or f.snapshot,
            f.binding, f.actions if actions is None else actions)


class SourcePlanGoldenTests(unittest.TestCase):
    def rejected(self, result, code=None):
        self.assertIsInstance(result, ProtectionError)
        if code is not None:
            self.assertEqual(result.code, code)
        self.assertFalse(result.retryable)
        self.assertEqual(result.trace_id, 'synthetic/action-plan')

    def test_both_source_schemas_and_formats_golden(self):
        for kind in ('mainline', 'legacy'):
            for fmt in ('csv', 'xlsx'):
                with self.subTest(kind=kind, fmt=fmt):
                    f = fixture(kind, fmt)
                    result = convert(f)
                    self.assertIsInstance(result, ActionPlan)
                    result.validate_snapshot(f.snapshot)
                    self.assertEqual(result, convert(f, actions=tuple(reversed(f.actions))))
                    self.assertEqual(result.source, f.options['source_binding'])
                    self.assertEqual(result.scope, f.options['scope'])
                    self.assertEqual(result.actions, f.actions)
                    self.assertEqual(result.policy_binding, f.binding)
                    self.assertEqual(result.input_hash, f.snapshot.input_hash)
                    self.assertEqual(result.adapter_version, ADAPTER_VERSION)
                    self.assertEqual(result.source.source_trust, SourceTrust.SYNTHETIC)
                    self.assertEqual(result.source.source_environment, 'test')
                    self.assertIsNone(result.approval)
                    self.assertEqual(result.unresolved, ())
                    self.assertEqual(result.plan_hash, content_hash(result.content()))
                    self.assertNotEqual(result.plan_hash, result.source.source_plan_hash.removeprefix('sha256:'))

    def test_frozen_source_scope_and_target_digest_goldens(self):
        goldens = {
            ('mainline', 'csv'): (
                'sha256:95fcf4c3f781471be52e9466ea90404d12d9118076e1b98d15dddfd353c947bd',
                'sha256:bfc14d85f183c1887388ab3d9e612f66942d2877b024e33f7c2be42ffa3b0d52',
                '24d54f2192bb971046a899de69e0700a81fb3a48efb68ed8d7701451a62cf854'),
            ('mainline', 'xlsx'): (
                'sha256:031df68c0641c54def6789770b56df4c06249f0f3f8cc759701ca08815bf777b',
                'sha256:be45e9ad278dbe18bf13bb9487c65c2be307224f9dea0609fcb1881fdb020775',
                '5beb4545f1f6a2bebac8629eb3dc10aba4a447b3191b1a87a7377defdeb981e3'),
            ('legacy', 'csv'): (
                'c4eb04da87514a8f365e69a1fe9e0e86eefb2b395ce3d74c289c8cf5d3734004',
                '77eb0a68b8fad6dc36bff7146492763257c99db53b2ba3ae03caab4393b8605f',
                'e27dd6fdba1fdeda11bc25ebace88cc5241c6595803e5153a9dd3d7365c484e3'),
            ('legacy', 'xlsx'): (
                '2387097144d11455bad1a1a1c239e8459b3b23bc1eced0690c4685fefd28c0ee',
                '80b079bb66d6bff0eb7991a1f6fdcd09234a9adba7fd7b4fa39518d15c55d72f',
                'f804177ca3fdc29a62b0ca72bf93abd4b07c4d662feea7fdaa5409041ee5ad1b'),
        }
        for (kind, fmt), expected in goldens.items():
            with self.subTest(kind=kind, fmt=fmt):
                result = convert(fixture(kind, fmt))
                self.assertEqual((result.source.source_plan_hash, result.source.scope_hash, result.plan_hash), expected)

    def test_synthetic_mainline_inputs_match_retained_schema(self):
        import jsonschema
        path = Path(__file__).resolve().parents[3] / 'docs/mainline1/contracts/schema.json'
        schema = json.loads(path.read_text())
        validator = jsonschema.Draft202012Validator(
            {'$ref': '#/$defs/RedactionPlan', '$defs': schema['$defs']}, format_checker=jsonschema.FormatChecker())
        for fmt in ('csv', 'xlsx'):
            validator.validate(fixture(fmt=fmt).doc)

    def test_original_codepoints_and_cell_never_widen(self):
        for fmt in ('csv', 'xlsx'):
            f = fixture(fmt=fmt)
            result = convert(f)
            span, cell, drop = result.actions
            original = next(c for c in f.snapshot.cells if (c.sheet_id, c.source_row, c.column_id) ==
                            (span.location.sheet_id, 2, 'c1')).original_text
            self.assertEqual(original[span.location.start:span.location.end], 'a@example.invalid')
            self.assertEqual((span.location.start, span.location.end), (5, 22))
            self.assertEqual((cell.location.kind, cell.location.source_row, cell.location.column_id),
                             (LocationKind.CELL, 3, 'c1'))
            self.assertEqual((drop.location.sheet_id, drop.location.column_id), (f.snapshot.sheet_ids[0], 'c3'))

    def test_legacy_scope_order_and_only_data_cells_are_masked(self):
        f = fixture('legacy', 'xlsx')
        result = convert(f)
        self.assertEqual(tuple(s.sheet_id for s in result.scope.sheets), ('xlsx:1', 'xlsx:0'))
        self.assertEqual([s.column_ids for s in result.scope.sheets], [('c2', 'c1', 'c3')] * 2)
        masks = [a for a in result.actions if a.algorithm.algorithm is Algorithm.REPLACE]
        self.assertEqual([(a.location.sheet_id, a.location.source_row, a.location.column_id) for a in masks],
                         [('xlsx:1', 2, 'c1'), ('xlsx:1', 3, 'c1'), ('xlsx:0', 2, 'c1'), ('xlsx:0', 3, 'c1')])
        self.assertTrue(all(a.algorithm.replacement is Replacement.EMAIL for a in masks))
        self.assertFalse(any(a.location.source_row == 1 for a in masks))

    def test_source_digest_algorithm_keeps_mainline_trace_exclusion(self):
        f = fixture()
        original = convert(f)
        f.doc['meta']['trace_id'] = FINDING
        self.assertEqual(convert(f), original)
        f.doc['meta']['domain_id'] = 'changed'
        self.rejected(convert(f), ReasonCode.HASH_MISMATCH)
        self.assertNotEqual(MAINLINE_HASH_VERSION, LEGACY_HASH_VERSION)
        self.assertTrue(original.source.source_plan_hash.startswith('sha256:'))
        self.assertFalse(convert(fixture('legacy')).source.source_plan_hash.startswith('sha256:'))

    def test_target_digest_changes_for_policy_algorithm_lifetime_and_identity(self):
        f = fixture()
        original = convert(f)
        alternate = replace(f.actions[0], algorithm=replace(f.actions[0].algorithm, replacement=Replacement.REDACTED))
        changed = convert(f, actions=(alternate, *f.actions[1:]))
        self.assertNotEqual(changed.plan_hash, original.plan_hash)
        self.assertEqual(changed.source, original.source)
        for options in (dict(plan_id='synthetic/another-plan'), dict(expires_at=AT + timedelta(minutes=40))):
            self.assertNotEqual(convert(f, **options).plan_hash, original.plan_hash)
        f.binding = replace(f.binding, protection_version='synthetic-protection-v2')
        self.assertNotEqual(convert(f).plan_hash, original.plan_hash)

    def test_does_not_import_framework_network_or_masking_core(self):
        script = '''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'django', 'requests', 'httpx', 'socket', 'mainline1', 'controlled_export'} or fullname.startswith('data_security.core'):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from data_security.tests.test_source_plans import fixture, convert
from data_security.contracts import ActionPlan
for kind in ('mainline', 'legacy'):
    for fmt in ('csv', 'xlsx'):
        assert isinstance(convert(fixture(kind, fmt)), ActionPlan)
'''
        # Importing this test module imports subprocess, so socket is blocked only
        # if someone actually attempts to import it, never used to open a network.
        result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[3],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_absent_mismatched_or_future_approval_fails(self):
        for kind in ('mainline', 'legacy'):
            f = fixture(kind)
            approval = f.options['source_approval']
            for bad in (None, replace(approval, approval_ref='synthetic/other'),
                        replace(approval, approved_at=AT + timedelta(seconds=1))):
                self.rejected(convert(f, source_approval=bad), ReasonCode.SOURCE_NOT_APPROVED)
            self.rejected(convert(f, source_approval=replace(approval, content_hash='0' * 64)), ReasonCode.HASH_MISMATCH)
            retained = f.options['source_binding']
            self.rejected(convert(f, source_binding=replace(retained, approval_basis_ref=None, approval_basis_version=None)),
                          ReasonCode.SOURCE_NOT_APPROVED)
            self.rejected(convert(f, source_binding=replace(retained, source_trust=SourceTrust.UNVERIFIED)),
                          ReasonCode.SOURCE_NOT_APPROVED)

    def test_snapshot_asset_version_and_input_hash_drift_fail(self):
        for kind in ('mainline', 'legacy'):
            f = fixture(kind)
            for changed in (replace(f.snapshot, asset_version='asset/changed'), replace(f.snapshot, input_hash='0' * 64)):
                self.rejected(convert(f, snapshot=changed), ReasonCode.HASH_MISMATCH)

    def test_incomplete_excluded_or_unknown_coverage_fails(self):
        f = fixture()
        cov = f.snapshot.coverage
        for changed in (replace(cov, total=cov.total + 1, eligible=cov.eligible + 1, unscanned=1),
                        replace(cov, processed=cov.processed - 1, unknown=1),
                        replace(cov, processed=cov.processed - 1, failed=1),
                        replace(cov, total=cov.total + 1, excluded=1)):
            self.rejected(convert(f, snapshot=replace(f.snapshot, coverage=changed)), ReasonCode.SCOPE_INCOMPLETE)

    def test_source_hash_drift_and_legacy_scope_hash_drift_fail(self):
        for kind in ('mainline', 'legacy'):
            f = fixture(kind)
            f.doc['operations'][0]['replacement' if kind == 'mainline' else 'value'] = '[REDACTED]'
            if kind == 'mainline':
                f.doc['policy_version'] = 'changed'
            self.rejected(convert(f), ReasonCode.HASH_MISMATCH)
        f = fixture('legacy')
        f.options['source_binding'] = replace(f.options['source_binding'], scope_hash='0' * 64)
        self.rejected(convert(f), ReasonCode.HASH_MISMATCH)

    def test_unknown_schema_is_not_downgraded(self):
        for kind, key, value in (('legacy', 'version', '2'), ('legacy', 'version', 1),
                                 ('mainline', 'meta', {'schema_version': 'mainline1.proposed.v2'})):
            f = fixture(kind)
            f.doc[key] = value
            with self.assertRaises(ContractViolation) as raised:
                convert(f)
            self.assertEqual(raised.exception.code, ReasonCode.UNKNOWN_SCHEMA)
        f = fixture()
        f.doc['operation_contract_version'] = 'unknown-v2'
        rebind(f)
        self.rejected(convert(f), ReasonCode.UNKNOWN_SCHEMA)

    def test_limits_are_explicit_snapshot_limits(self):
        f = fixture()
        limited = replace(f.snapshot, limits=replace(BASELINE_LIMITS, max_actions=2))
        self.rejected(convert(f, snapshot=limited), ReasonCode.LIMIT_EXCEEDED)

    def test_mainline_nonready_unresolved_and_validation_errors_fail(self):
        for changes, code in (({'status': 'partial'}, ReasonCode.SOURCE_NOT_APPROVED),
                              ({'status': 'invalid'}, ReasonCode.SOURCE_NOT_APPROVED),
                              ({'unresolved': ['protect-email:TARGET_UNCOVERED']}, ReasonCode.SCOPE_INCOMPLETE),
                              ({'validation_errors': ['PLAN_APPROVAL_REQUIRED']}, ReasonCode.SCOPE_INCOMPLETE)):
            f = fixture()
            f.doc.update(changes)
            rebind(f)
            self.rejected(convert(f), code)

    def test_mainline_parser_scope_requirements_and_environment_bindings_fail(self):
        for field in ('scope_hash', 'parser_config_hash', 'requirements_hash'):
            f = fixture()
            f.doc[field] = 'sha256:' + '0' * 64
            rebind(f)
            self.rejected(convert(f), ReasonCode.HASH_MISMATCH)
        f = fixture()
        f.doc['parser_version'] = 'unknown-parser-v2'
        rebind(f)
        self.rejected(convert(f), ReasonCode.UNKNOWN_SCHEMA)
        for field, value in (('environment', 'production'), ('domain_id', 'changed'), ('evaluation_run_id', PID)):
            f = fixture()
            f.doc['meta'][field] = value
            rebind(f)
            self.rejected(convert(f), ReasonCode.HASH_MISMATCH)

    def test_mainline_missing_unknown_and_malformed_source_fields_fail(self):
        for path in ((), ('meta',), ('asset',), ('operations', 0), ('operations', 0, 'target'),
                     ('operations', 0, 'target', 'span'), ('requirements', 0)):
            f = fixture()
            target = f.doc
            for part in path:
                target = target[part]
            target['unexpected'] = True
            rebind(f)
            self.rejected(convert(f), ReasonCode.UNKNOWN_FIELD)
        f = fixture()
        del f.doc['operation_count']
        rebind(f)
        self.rejected(convert(f), ReasonCode.MISSING_FIELD)
        for value in (None, [], 'bad', True):
            f = fixture()
            f.doc['operations'][0]['target'] = value
            rebind(f)
            self.rejected(convert(f), ReasonCode.INVALID_TYPE)

    def test_mainline_unknown_operations_formula_channel_and_wrong_refs_fail(self):
        for changes in ({'type': 'mask_columns'}, {'match_ref': 'private/wrong'}, {'finding_ids': []},
                        {'requirement_ids': ['unknown']}, {'replacement': 'arbitrary'}):
            f = fixture()
            f.doc['operations'][0].update(changes)
            rebind(f)
            self.rejected(convert(f))
        f = fixture()
        f.doc['operations'][0]['target']['channel'] = 'formula'
        rebind(f)
        self.rejected(convert(f), ReasonCode.UNSUPPORTED_SCOPE)

    def test_missing_extra_duplicate_or_relocated_resolved_actions_fail(self):
        for kind in ('mainline', 'legacy'):
            f = fixture(kind)
            for actions in (f.actions[:-1], (*f.actions, f.actions[0]),
                            (replace(f.actions[0], source_operation_ref='unknown'), *f.actions[1:])):
                self.rejected(convert(f, actions=actions), ReasonCode.SCOPE_INCOMPLETE)
        f = fixture()
        for target in (location('csv:0'), location('csv:0', kind=LocationKind.CELL_SPAN, start=4, end=22),
                       location('csv:0', row=3, kind=LocationKind.CELL_SPAN, start=5, end=22)):
            changed = replace(f.actions[0], location=target)
            self.rejected(convert(f, actions=(changed, *f.actions[1:])), ReasonCode.INVALID_COORDINATE)
        widened = replace(f.actions[1], location=location('csv:0', row=None, kind=LocationKind.COLUMN),
                          algorithm=f.actions[2].algorithm)
        self.rejected(convert(f, actions=(f.actions[0], widened, f.actions[2])), ReasonCode.INVALID_COORDINATE)

    def test_unproven_and_invalid_unicode_mapping_fail_without_widening(self):
        f = fixture()
        source_cell = next(c for c in f.snapshot.cells if (c.source_row, c.column_id) == (2, 'c1'))
        unmapped = replace(source_cell, mapping_proven=False, source_spans=())
        # Normalized characters sharing an original two-codepoint cluster cannot
        # authorize a boundary in the middle of that cluster.
        clustered = replace(source_cell, normalized_text='x', source_spans=((0, 22),))
        for changed in (unmapped, clustered):
            snapshot = replace(f.snapshot, cells=tuple(changed if c is source_cell else c for c in f.snapshot.cells))
            self.rejected(convert(f, snapshot=snapshot), ReasonCode.INVALID_COORDINATE)
        f.doc['operations'][0]['target']['span']['end'] = 999
        rebind(f)
        changed = replace(f.actions[0], location=replace(f.actions[0].location, end=999))
        self.rejected(convert(f, actions=(changed, *f.actions[1:])), ReasonCode.INVALID_COORDINATE)

    def test_structural_drop_requires_complete_rows_and_header_scope(self):
        for includes_header, ranges in ((False, ((1, 3),)), (True, ((2, 3),))):
            f = fixture()
            scope = replace(f.options['scope'], sheets=(replace(f.options['scope'].sheets[0],
                            includes_header=includes_header, row_ranges=ranges),))
            f.options['scope'] = scope
            scope_doc = dict(asset_version_id=ASSET, include_header=includes_header,
                selections=[dict(sheet_id='csv:0', rows=ranges, columns=[[1, 3]])])
            value = source_hash(scope_doc, mainline=True)
            f.doc['scope_hash'] = value
            f.options['source_binding'] = replace(f.options['source_binding'], scope_hash=value)
            rebind(f)
            self.rejected(convert(f), ReasonCode.UNSUPPORTED_SCOPE)

    def test_row_one_is_not_authorized_by_header_false(self):
        f = fixture()
        f.doc['operations'] = f.doc['operations'][1:2]
        f.doc['operation_count'] = 1
        f.doc['operations'][0]['target']['row'] = 1
        f.actions = (replace(f.actions[1], location=location('csv:0', row=1)),)
        scope = replace(f.options['scope'], sheets=(replace(f.options['scope'].sheets[0], includes_header=False),))
        f.options['scope'] = scope
        scope_doc = dict(asset_version_id=ASSET, include_header=False,
            selections=[dict(sheet_id='csv:0', rows=[[1, 3]], columns=[[1, 3]])])
        value = source_hash(scope_doc, mainline=True)
        f.doc['scope_hash'] = value
        f.options['source_binding'] = replace(f.options['source_binding'], scope_hash=value)
        rebind(f)
        self.rejected(convert(f), ReasonCode.AUTHORIZATION_DENIED)

    def test_mainline_duplicate_labels_use_indices_not_names(self):
        f = fixture()
        columns = tuple(replace(c, label='duplicate') for c in f.snapshot.columns)
        self.assertIsInstance(convert(f, snapshot=replace(f.snapshot, columns=columns)), ActionPlan)

    def test_legacy_duplicate_or_blank_headers_missing_names_and_ambiguous_sheet_fail(self):
        for fmt in ('csv', 'xlsx'):
            f = fixture('legacy', fmt)
            for label in ('Email', ''):
                columns = tuple(replace(c, label=label) if c.column_id == 'c2' else c for c in f.snapshot.columns)
                self.rejected(convert(f, snapshot=replace(f.snapshot, columns=columns)), ReasonCode.INVALID_COORDINATE)
        f = fixture('legacy', 'xlsx')
        self.rejected(convert(f, sheet_names=()), ReasonCode.INVALID_COORDINATE)
        self.rejected(convert(f, sheet_names=(('xlsx:0', 'Unknown'), ('xlsx:1', 'Archive'))), ReasonCode.INVALID_COORDINATE)
        with self.assertRaises(ContractViolation):
            SourcePlanAdapter(**(f.options | dict(sheet_names=(('xlsx:0', 'Same'), ('xlsx:1', 'Same')))))

    def test_legacy_strict_old_keys_and_no_new_span_fields(self):
        for path in ((), ('scope',), ('operations', 0), ('operations', 1), ('operations', 2)):
            f = fixture('legacy')
            target = f.doc
            for part in path:
                target = target[part]
            target['span'] = {'start': 0, 'end': 1}
            rebind(f)
            self.rejected(convert(f), ReasonCode.UNKNOWN_FIELD)
        for values in (['Email', 'Email'], [], ['missing']):
            f = fixture('legacy')
            f.doc['scope']['columns'] = values
            f.options['source_binding'] = replace(f.options['source_binding'], scope_hash=source_hash(f.doc['scope']))
            rebind(f)
            self.rejected(convert(f))

    def test_legacy_custom_default_fixed_values_and_new_algorithms_fail(self):
        for value in ('***', '=1+1', '', 'arbitrary'):
            f = fixture('legacy')
            f.doc['operations'][0]['value'] = value
            rebind(f)
            self.rejected(convert(f), ReasonCode.UNSUPPORTED_SCOPE)
        f = fixture('legacy')
        del f.doc['operations'][0]['value']
        rebind(f)
        self.rejected(convert(f), ReasonCode.UNSUPPORTED_SCOPE)
        f = fixture('legacy')
        f.doc['operations'][0]['strategy'] = 'hmac'
        rebind(f)
        self.rejected(convert(f), ReasonCode.UNSUPPORTED_SCOPE)
        f = fixture('legacy')
        changed = replace(f.actions[0], algorithm=replace(f.actions[0].algorithm, replacement=Replacement.REDACTED))
        self.rejected(convert(f, actions=(changed, *f.actions[1:])), ReasonCode.UNSUPPORTED_SCOPE)

    def test_legacy_format_operation_scope_and_header_mask_fail(self):
        f = fixture('legacy')
        f.doc['format'] = 'xlsx'
        rebind(f)
        self.rejected(convert(f), ReasonCode.UNSUPPORTED_FORMAT)
        f = fixture('legacy')
        f.doc['operations'][0]['type'] = 'mask_span'
        rebind(f)
        self.rejected(convert(f), ReasonCode.UNSUPPORTED_SCOPE)
        f = fixture('legacy')
        f.doc['operations'][0]['columns'] = ['outside']
        rebind(f)
        self.rejected(convert(f), ReasonCode.AUTHORIZATION_DENIED)
        f = fixture('legacy')
        changed = replace(f.actions[0], location=location('csv:0', row=1))
        self.rejected(convert(f, actions=(changed, *f.actions[1:])), ReasonCode.SCOPE_INCOMPLETE)

    def test_legacy_reordered_widened_and_partial_scope_are_rejected(self):
        f = fixture('legacy', 'xlsx')
        scope = f.options['scope']
        self.rejected(convert(f, scope=replace(scope, sheets=tuple(reversed(scope.sheets)))), ReasonCode.AUTHORIZATION_DENIED)
        for selection in (replace(scope.sheets[0], column_ids=('c1', 'c2', 'c3')),
                          replace(scope.sheets[0], row_ranges=((2, 3),)),
                          replace(scope.sheets[0], includes_header=False)):
            self.rejected(convert(f, scope=replace(scope, sheets=(selection, scope.sheets[1]))), ReasonCode.AUTHORIZATION_DENIED)

    def test_zero_columns_and_conflicting_actions_are_rejected(self):
        f = fixture('legacy')
        f.doc['operations'] = [dict(type='drop_columns', columns=['Notes', 'Email', 'Remove'])]
        f.actions = tuple(action('operations/0', location('csv:0', column=col, row=None, kind=LocationKind.COLUMN), i)
                          for i, col in enumerate(('c2', 'c1', 'c3')))
        rebind(f)
        self.rejected(convert(f), ReasonCode.UNSUPPORTED_SCOPE)
        f = fixture('legacy')
        f.doc['operations'][1]['columns'] = ['Email']
        f.actions = (*f.actions[:-1], replace(f.actions[-1], location=location('csv:0', row=None, kind=LocationKind.COLUMN)))
        rebind(f)
        self.rejected(convert(f), ReasonCode.INVALID_COORDINATE)
        f = fixture()
        f.doc['operations'][1]['target']['row'] = 2
        f.actions = (f.actions[0], replace(f.actions[1], location=location('csv:0')), f.actions[2])
        rebind(f)
        self.rejected(convert(f), ReasonCode.INVALID_COORDINATE)

    def test_csv_and_xlsx_mapped_unicode_and_rejected_cross_coordinates(self):
        for fmt in ('csv', 'xlsx'):
            with self.subTest(fmt=fmt):
                f = fixture(fmt=fmt)
                source = next(c for c in f.snapshot.cells if (c.sheet_id, c.source_row, c.column_id) ==
                              (f.snapshot.sheet_ids[0], 2, 'c1'))
                mapped = replace(source, normalized_text='A🙂é a@example.invalid',
                    source_spans=((0, 1), (1, 2), (2, 4), *tuple((i, i + 1) for i in range(4, 22))))
                snapshot = replace(f.snapshot, cells=tuple(mapped if c is source else c for c in f.snapshot.cells))
                result = convert(f, snapshot=snapshot)
                self.assertIsInstance(result, ActionPlan)
                self.assertEqual((result.actions[0].location.start, result.actions[0].location.end), (5, 22))
                shifted = replace(f.actions[0], location=replace(f.actions[0].location,
                                  sheet_id='xlsx:1' if fmt == 'xlsx' else 'csv:1'))
                self.rejected(convert(f, actions=(shifted, *f.actions[1:])), ReasonCode.INVALID_COORDINATE)

    def test_adjacent_source_spans_are_not_mistaken_for_overlap(self):
        f = fixture()
        f.doc['operations'][0]['target']['span']['end'] = 10
        f.doc['operations'][1].update(type='mask_span', target=dict(kind='span', sheet_id='csv:0',
            row=2, column=1, channel='value', span=dict(start=10, end=22)))
        f.actions = (replace(f.actions[0], location=replace(f.actions[0].location, end=10)),
                     replace(f.actions[1], location=location('csv:0', kind=LocationKind.CELL_SPAN, start=10, end=22)),
                     f.actions[2])
        rebind(f)
        self.assertIsInstance(convert(f), ActionPlan)

    def test_mainline_data_only_scope_preserves_excluded_header(self):
        f = fixture()
        f.doc['operations'] = f.doc['operations'][:2]
        f.doc['operation_count'] = 2
        f.actions = f.actions[:2]
        f.options['scope'] = replace(f.options['scope'], sheets=(replace(f.options['scope'].sheets[0], includes_header=False),))
        scope_doc = dict(asset_version_id=ASSET, include_header=False,
            selections=[dict(sheet_id='csv:0', rows=[[1, 3]], columns=[[1, 3]])])
        value = source_hash(scope_doc, mainline=True)
        f.doc['scope_hash'] = value
        f.options['source_binding'] = replace(f.options['source_binding'], scope_hash=value)
        rebind(f)
        result = convert(f)
        self.assertIsInstance(result, ActionPlan)
        self.assertFalse(result.scope.sheets[0].includes_header)
        self.assertTrue(all(a.location.source_row > 1 for a in result.actions))

    def test_legacy_omitted_strategy_and_formula_step_preserve_fixed_mapping(self):
        f = fixture('legacy')
        del f.doc['operations'][0]['strategy']
        f.doc['operations'].pop()
        rebind(f)
        result = convert(f)
        self.assertIsInstance(result, ActionPlan)
        self.assertEqual(result.actions, f.actions)

    def test_invalid_source_datetime_returns_contract_error(self):
        for value in ('not-a-date', '2026-11-06', '2026-11-06T04:12:00'):
            f = fixture()
            f.doc['meta']['created_at'] = value
            rebind(f)
            self.rejected(convert(f), ReasonCode.INVALID_VALUE)

    def test_mainline_whole_cell_rejects_fragment_algorithms(self):
        f = fixture()
        base = f.actions[1].algorithm
        algorithms = (
            replace(base, algorithm=Algorithm.MASK, replacement=None, keep_prefix=1, keep_suffix=1, mask_symbol='*'),
            replace(base, algorithm=Algorithm.HMAC, replacement=None, key_ref='mask-link/v1'),
            replace(base, algorithm=Algorithm.PSEUDONYM, replacement=None, key_ref='mask-pseudonym/v1', pseudonym_bits=128),
        )
        for algorithm in algorithms:
            with self.subTest(algorithm=algorithm.algorithm):
                changed = replace(f.actions[1], algorithm=algorithm)
                self.rejected(convert(f, actions=(f.actions[0], changed, f.actions[2])), ReasonCode.UNSUPPORTED_SCOPE)
        dropped = replace(f.actions[1], algorithm=replace(base, algorithm=Algorithm.DROP, replacement=None))
        self.assertIsInstance(convert(f, actions=(f.actions[0], dropped, f.actions[2])), ActionPlan)

    def test_mainline_requires_independent_snapshot_source_evidence(self):
        f = fixture()
        self.rejected(convert(f, snapshot_source=None), ReasonCode.MISSING_FIELD)
        metadata = f.options['snapshot_source'].to_value()
        for key, value in (('parser_version', 'internal-table-v3'), ('config_hash', 'sha256:' + '0' * 64)):
            self.rejected(convert(f, snapshot_source=FrozenJSON(metadata | {key: value})), ReasonCode.HASH_MISMATCH)
        for key in ('config', 'structures'):
            incomplete = {name: value for name, value in metadata.items() if name != key}
            self.rejected(convert(f, snapshot_source=FrozenJSON(incomplete)), ReasonCode.MISSING_FIELD)
        # Header policy cannot drift while retaining a matching config-hash string.
        changed = deepcopy(metadata)
        changed['config']['parser']['header_row'] = None
        self.rejected(convert(f, snapshot_source=FrozenJSON(changed)), ReasonCode.HASH_MISMATCH)
        # Two matching copies in the approved plan/binding cannot attest how the
        # independently supplied snapshot was parsed.
        f.doc['parser_config_hash'] = 'sha256:' + '0' * 64
        f.options['source_binding'] = replace(f.options['source_binding'], parser_config_hash=f.doc['parser_config_hash'])
        rebind(f)
        self.rejected(convert(f), ReasonCode.HASH_MISMATCH)
        self.assertIsInstance(convert(fixture('legacy')), ActionPlan)

    def test_governed_partial_rows_cannot_authorize_whole_column(self):
        from data_security.adapters.tabular.parsed_artifacts import govern_parse_result
        from mainline1.parsing import AssetRef, ParserConfig, Scope, Selection, parse_table

        f = fixture()
        content = ('Email,Notes,Remove\nＡ🙂é a@example.invalid,=1+1,unused\n'
                   'b@example.invalid,quoted,unused\nlast,last,last\n').encode()
        input_hash = hashlib.sha256(content).hexdigest()
        asset = AssetRef(ASSET, 'synthetic-test-domain', 'sha256:' + input_hash,
                         'csv', len(content), 'private:synthetic')
        parsed = parse_table(content, asset, config=ParserConfig(include_header=True),
            scope=Scope(ASSET, (Selection('csv:0', ((1, 3),), ((1, 3),)),), True))
        governed = govern_parse_result(parsed, limits=BASELINE_LIMITS).tree.to_value()
        f.snapshot = TableSnapshot.from_wire(governed['snapshot'])
        self.assertEqual(governed['source']['structures'][0]['rows'], 4)
        self.assertEqual(max(cell.source_row for cell in f.snapshot.cells), 3)
        f.options.update(input_hash=input_hash, snapshot_source=FrozenJSON(governed['source']))
        f.doc['asset']['content_hash'] = 'sha256:' + input_hash
        f.doc['parser_config_hash'] = governed['source']['config_hash']
        f.options['source_binding'] = replace(f.options['source_binding'],
            parser_config_hash=f.doc['parser_config_hash'])
        rebind(f)
        self.rejected(convert(f), ReasonCode.UNSUPPORTED_SCOPE)
        # The same selected data remains valid for cell/span operations; do not widen it.
        f.doc['operations'] = f.doc['operations'][:2]
        f.doc['operation_count'] = 2
        f.actions = f.actions[:2]
        rebind(f)
        plan = convert(f)
        self.assertIsInstance(plan, ActionPlan)
        self.assertEqual(plan.scope.sheets[0].row_ranges, ((1, 3),))
        self.assertIsNone(plan.approval)

    def test_governed_headerless_row_one_mask_is_data_not_header(self):
        from data_security.adapters.tabular.parsed_artifacts import govern_parse_result
        from mainline1.parsing import AssetRef, ParserConfig, parse_table

        f = fixture()
        content = b'a,b,c\nx,y,z\nu,v,w\n'
        input_hash = hashlib.sha256(content).hexdigest()
        asset = AssetRef(ASSET, 'synthetic-test-domain', 'sha256:' + input_hash,
                         'csv', len(content), 'private:synthetic')
        parsed = parse_table(content, asset, config=ParserConfig(header_row=None, include_header=False))
        governed = govern_parse_result(parsed, limits=BASELINE_LIMITS).tree.to_value()
        f.snapshot = TableSnapshot.from_wire(governed['snapshot'])
        self.assertEqual(f.snapshot.coverage.excluded, 0)
        f.options.update(input_hash=input_hash, snapshot_source=FrozenJSON(governed['source']))
        f.options['scope'] = replace(f.options['scope'], sheets=(
            replace(f.options['scope'].sheets[0], includes_header=False),))
        f.doc['asset']['content_hash'] = 'sha256:' + input_hash
        f.doc['parser_config_hash'] = governed['source']['config_hash']
        f.doc['scope_hash'] = governed['source']['scope_hash']
        f.options['source_binding'] = replace(f.options['source_binding'],
            parser_config_hash=f.doc['parser_config_hash'], scope_hash=f.doc['scope_hash'])
        f.doc['operations'] = f.doc['operations'][1:2]
        f.doc['operations'][0]['target']['row'] = 1
        f.doc['operation_count'] = 1
        f.actions = (replace(f.actions[1], location=location('csv:0', row=1)),)
        rebind(f)
        plan = convert(f)
        self.assertIsInstance(plan, ActionPlan)
        self.assertEqual(plan.actions, f.actions)
        self.assertFalse(plan.scope.sheets[0].includes_header)
        self.assertEqual(plan.actions[0].location.source_row, 1)
        self.assertIsNone(plan.approval)

    def test_no_operations_is_not_invented_protection(self):
        f = fixture('legacy')
        del f.doc['operations']
        f.actions = ()
        rebind(f)
        result = convert(f)
        self.assertIsInstance(result, ActionPlan)
        self.assertEqual(result.actions, ())
        self.assertIsNone(result.approval)


if __name__ == '__main__':
    unittest.main()
