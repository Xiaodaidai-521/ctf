"""Synthetic execution candidates; no client report, publication, or quota effects."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import os
import unittest
from unittest.mock import patch

from data_security.adapters.tabular.codec import TableCodec
from data_security.application.crypto_service import CryptoService
from data_security.application.reports import ReportAuthenticator
from data_security.application.table_reports import ReportCandidate, TableReportExecutor
from data_security.contracts import (
    BASELINE_LIMITS, Environment, ExecutionBinding, KeyPurpose, MaskReport, MediaType,
    ObjectContext, ProtectionError, ReasonCode, SourceTrust, StoredObject, Unit, Unresolved,
    canonical_bytes, content_hash,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key
from data_security.tests.test_phase5_codec import binary, rewrite, xlsx
from data_security.tests.test_phase5_pipeline import OUTPUT_HASHES, pipeline_fixture
from data_security.tests.test_phase6_reports import plan_with
from data_security.tests.test_source_plans import AT


class CandidateStore:
    def __init__(self, crypto):
        self.crypto = crypto
        self.envelopes = {}
        self.failure = None
        self.calls = []

    def write_candidate(self, envelope, context):
        self.calls.append('write')
        if self.failure == 'write':
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
                                   retryable=False, trace_id='synthetic/store')
        self.envelopes['private/test'] = envelope
        return StoredObject(schema_version=StoredObject.SCHEMA, object_ref='private/test',
            version=context.object_version, ciphertext_hash=hashlib.sha256(canonical_bytes(envelope)).hexdigest(),
            size_bytes=len(canonical_bytes(envelope)), state='candidate')

    def verify(self, candidate, context):
        self.calls.append('verify')
        envelope = self.envelopes[candidate.object_ref]
        if self.failure == 'verify':
            envelope = replace(envelope, ciphertext_and_tag=envelope.ciphertext_and_tag[:-1] +
                               bytes([envelope.ciphertext_and_tag[-1] ^ 1]))
        opened = self.crypto.open(envelope, context, envelope.key)
        if isinstance(opened, ProtectionError):
            return opened
        return replace(candidate, state='verified')


class TableReportTests(unittest.TestCase):
    def setUp(self):
        self.now = AT + timedelta(seconds=1)
        self.keys = FakeKeys()
        self.crypto = CryptoService(keys=self.keys, service_identity='reports/test', random_bytes=os.urandom,
            environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.auth = ReportAuthenticator(crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
            executor_ref='executor/test', environment=Environment.TEST, clock=lambda: self.now)
        self.store = CandidateStore(self.crypto)
        self.executor = TableReportExecutor(codec_factory=TableCodec, crypto=self.crypto,
            data_key=reference_key(KeyPurpose.DATA), store=self.store, authenticator=self.auth,
            limits=BASELINE_LIMITS, clock=lambda: self.now)
        self.load()

    def load(self, kind='mainline', fmt='csv'):
        fixture, self.plan, self.expected, content = pipeline_fixture(kind, fmt)
        values = examples()
        self.execution = replace(values[ExecutionBinding], asset_version=self.plan.asset_version,
            policy_binding=self.plan.policy_binding, scope=self.plan.scope,
            environment='test', domain_ref=self.plan.source.source_domain, expires_at=self.plan.expires_at)
        self.context = replace(values[ObjectContext], object_version=self.plan.asset_version,
                               authorization_ref=self.execution.authorization_id)
        self.payload = binary(content, MediaType.CSV if fmt == 'csv' else MediaType.XLSX)

    def prepare(self):
        return self.executor.prepare(self.payload, self.plan, self.execution, self.context)

    def denied(self, result, code=None):
        self.assertIsInstance(result, ProtectionError)
        if code is not None:
            self.assertEqual(result.code, code)

    def change_plan(self, **values):
        self.plan = plan_with(self.plan, **values)
        self.execution = replace(self.execution, scope=self.plan.scope)

    def test_real_m1_codec_crypto_and_report_proof_roundtrip(self):
        for kind, fmt in [('mainline', 'csv'), ('legacy', 'csv'), ('legacy', 'xlsx')]:
            with self.subTest(kind=kind, fmt=fmt):
                self.load(kind, fmt)
                result = self.prepare()
                self.assertIsInstance(result, ReportCandidate)
                envelope = self.store.envelopes[result.stored.object_ref]
                output = self.crypto.open(envelope, self.context, envelope.key)
                self.assertEqual(output.binary, self.expected)
                self.assertEqual(result.report.output_hash, OUTPUT_HASHES[kind + '-' + fmt])
                self.assertEqual(result.report.input_hash, hashlib.sha256(self.payload.binary).hexdigest())
                self.assertEqual(result.report.ciphertext_hash, hashlib.sha256(canonical_bytes(envelope)).hexdigest())
                self.assertEqual(result.stored.state, 'verified')
                self.assertEqual(result.report.hit_count, 4 if fmt == 'xlsx' else 2)
                self.assertEqual(result.report.coverage.processed, 18 if fmt == 'xlsx' else 9)
                self.assertEqual(result.report.rescan_coverage.unit, Unit.FIELD)
                self.assertEqual(result.report.rescan_coverage.processed, 14 if fmt == 'xlsx' else 6)
                self.assertIs(self.auth.verify(result.report, result.proof, self.execution, self.plan, self.context,
                    input_hash=result.report.input_hash, output_hash=result.report.output_hash,
                    ciphertext_hash=result.report.ciphertext_hash), True)
                self.assertNotIn('MaskReport', repr(result))
        self.assertEqual(self.store.calls, ['write', 'verify'] * 3)

    def test_old_mainline_xlsx_golden_has_unprocessed_second_sheet_and_is_not_deliverable(self):
        self.load('mainline', 'xlsx')
        self.denied(self.prepare(), ReasonCode.SCOPE_INCOMPLETE)
        self.assertEqual(self.store.calls, [])

    def test_missing_action_cannot_turn_client_success_into_report(self):
        self.change_plan(actions=self.plan.actions[1:])
        self.denied(self.prepare(), ReasonCode.SCOPE_INCOMPLETE)
        self.assertEqual(self.store.calls, [])
        with self.assertRaises(TypeError):
            self.executor.prepare(self.payload, self.plan, self.execution, self.context, report={'success': True})

    def test_input_drift_unresolved_and_expiry_are_rejected_before_storage(self):
        original = self.payload
        self.payload = replace(original, binary=original.binary.replace(b'unused', b'edited'))
        self.denied(self.prepare(), ReasonCode.HASH_MISMATCH)
        self.payload = original
        old = self.plan
        self.change_plan(unresolved=(Unresolved(schema_version=Unresolved.SCHEMA, location=None,
            reason=ReasonCode.UNSUPPORTED_SCOPE, source_ref='synthetic/unresolved'),))
        self.denied(self.prepare(), ReasonCode.SCOPE_INCOMPLETE)
        self.plan = old
        self.now = self.plan.expires_at
        self.denied(self.prepare(), ReasonCode.AUTHORIZATION_EXPIRED)
        self.assertEqual(self.store.calls, [])

    def test_scope_projection_counts_exclusions_and_preserves_rows_and_headers(self):
        scope = replace(self.plan.scope, sheets=(replace(self.plan.scope.sheets[0], row_ranges=((1, 2),)),))
        actions = tuple(a for a in self.plan.actions if a.location.source_row != 3)
        self.change_plan(scope=scope, actions=actions)
        result = self.prepare()
        self.assertIsInstance(result, ReportCandidate)
        self.assertEqual((result.report.coverage.total, result.report.coverage.processed,
                          result.report.coverage.excluded), (9, 6, 3))
        self.assertEqual(len(result.report.excluded), 1)
        self.assertEqual(result.report.rescan_coverage.processed, 4)
        for sheet in (replace(scope.sheets[0], includes_header=False),
                      replace(scope.sheets[0], row_ranges=((1, 1), (3, 3))),
                      replace(scope.sheets[0], row_ranges=((1, 4),))):
            self.change_plan(scope=replace(scope, sheets=(sheet,)), actions=())
            self.denied(self.prepare())

    def test_serialized_bytes_are_rescanned_not_just_the_transformed_grid(self):
        real = TableCodec.serialize
        def inject(codec, snapshot, limits):
            output = real(codec, snapshot, limits)
            return replace(output, binary=output.binary.replace(b'[EMAIL]', b'new@example.invalid', 1))
        with patch.object(TableCodec, 'serialize', inject):
            self.denied(self.prepare(), ReasonCode.SCOPE_INCOMPLETE)
        self.assertEqual(self.store.calls, [])

    def test_preserved_xlsx_title_is_checked_even_when_grid_is_clean(self):
        self.load('legacy', 'xlsx')
        changed = rewrite(self.payload.binary, 'xl/workbook.xml',
                          lambda value: value.replace('明细'.encode(), b'name@example.invalid'))
        self.payload = replace(self.payload, binary=changed)
        self.change_plan(input_hash=hashlib.sha256(changed).hexdigest())
        self.denied(self.prepare(), ReasonCode.SCOPE_INCOMPLETE)
        self.assertEqual(self.store.calls, [])

    def test_unrepresented_output_metadata_fails_canonical_roundtrip(self):
        self.load('legacy', 'xlsx')
        real = TableCodec.serialize
        calls = []
        def inject(codec, snapshot, limits):
            output = real(codec, snapshot, limits)
            calls.append(1)
            if len(calls) == 1:
                changed = rewrite(output.binary, 'docProps/core.xml', lambda value: value.replace(
                    b'<dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">openpyxl</dc:creator>',
                    b'<dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">name@example.invalid</dc:creator>'))
                self.assertNotEqual(changed, output.binary)
                return replace(output, binary=changed)
            return output
        with patch.object(TableCodec, 'serialize', inject):
            self.denied(self.prepare(), ReasonCode.SCOPE_INCOMPLETE)
        self.assertEqual(self.store.calls, [])

    def test_storage_authentication_or_report_key_failure_never_issues_candidate(self):
        for failure in ('write', 'verify'):
            self.store.failure = failure
            with patch.object(self.auth, 'issue', wraps=self.auth.issue) as issue:
                self.denied(self.prepare())
                issue.assert_not_called()
        self.store.failure = None
        with patch.object(self.crypto, 'authenticate', return_value=ProtectionError(
                schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                retryable=False, trace_id='synthetic/key')):
            self.denied(self.prepare(), ReasonCode.KEY_UNAVAILABLE)

    def test_unverified_source_or_wrong_binding_cannot_produce_authenticated_candidate(self):
        self.change_plan(source=replace(self.plan.source, source_trust=SourceTrust.UNVERIFIED))
        self.denied(self.prepare(), ReasonCode.SOURCE_NOT_APPROVED)
        self.load()
        self.execution = replace(self.execution, quantity=self.execution.quantity + 1)
        result = self.prepare()
        self.assertIsInstance(result, ReportCandidate)
        self.assertEqual(result.proof.execution_hash, content_hash(self.execution))
        self.execution = replace(self.execution, authorization_id='other/authorization')
        self.denied(self.prepare(), ReasonCode.REPORT_MISMATCH)

    def test_expiry_during_file_verification_cannot_issue_success(self):
        real = self.store.verify
        def expire(*args):
            value = real(*args)
            self.now = self.plan.expires_at
            return value
        with patch.object(self.store, 'verify', expire):
            self.denied(self.prepare(), ReasonCode.AUTHORIZATION_EXPIRED)

    def test_metadata_reader_is_bound_and_does_not_mutate_frozen_codec_output(self):
        for fmt in ('csv', 'xlsx'):
            self.load('legacy', fmt)
            codec = TableCodec(asset_version=self.plan.asset_version)
            snapshot = codec.parse(self.payload, BASELINE_LIMITS)
            before = codec.serialize(snapshot, BASELINE_LIMITS)
            metadata = codec.delivery_metadata(snapshot, BASELINE_LIMITS)
            self.assertEqual(metadata.tree.to_value(), [] if fmt == 'csv' else ['明细', 'Archive'])
            self.assertEqual(codec.serialize(snapshot, BASELINE_LIMITS), before)
            self.denied(codec.delivery_metadata(replace(snapshot, input_hash='0' * 64), BASELINE_LIMITS),
                        ReasonCode.HASH_MISMATCH)
            self.denied(codec.delivery_metadata(replace(snapshot, asset_version='other/asset'), BASELINE_LIMITS),
                        ReasonCode.HASH_MISMATCH)
