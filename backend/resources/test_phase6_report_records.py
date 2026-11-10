"""Owner report records on isolated PostgreSQL; no client delivery endpoint."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from threading import Barrier
from unittest.mock import patch

from django.db import DatabaseError, close_old_connections, connection
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase

from data_security.adapters.persistence.models import ExportReport, PrivateObject
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.adapters.tabular.codec import TableCodec
from data_security.application.reports import ReportAuthenticator
from data_security.application.table_reports import ReportCandidate, TableReportExecutor
from data_security.contracts import (
    BASELINE_LIMITS, ContractViolation, Environment, ExecutionBinding, KeyPurpose, KeyStatus, MaskReport,
    MediaType, ProtectionError, ReasonCode, ReportRecord, canonical_bytes, content_hash,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import reference_key
from data_security.tests.test_phase5_codec import binary
from data_security.tests.test_phase5_pipeline import pipeline_fixture
from data_security.tests.test_source_plans import AT
from resources.test_phase6_private_store import PrivateStoreFixture


def document_hash(document):
    encoded = json.dumps(document, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


class ReportRecordFixture(PrivateStoreFixture):
    def setUp(self):
        super().setUp()
        _, plan, self.expected, content = pipeline_fixture('legacy', 'xlsx')
        binding = replace(examples()[ExecutionBinding], asset_version=plan.asset_version,
            policy_binding=plan.policy_binding, scope=plan.scope, environment='test',
            domain_ref=plan.source.source_domain, expires_at=plan.expires_at)
        context = replace(self.context, object_version=plan.asset_version,
                          authorization_ref=binding.authorization_id)
        self.auth = ReportAuthenticator(crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
            executor_ref='executor/test', environment=Environment.TEST, clock=lambda: AT + timedelta(seconds=1))
        executor = TableReportExecutor(codec_factory=TableCodec, crypto=self.crypto, data_key=self.key,
            store=self.store, authenticator=self.auth, limits=BASELINE_LIMITS,
            clock=lambda: AT + timedelta(seconds=1))
        candidate = executor.prepare(binary(content, MediaType.XLSX), plan, binding, context)
        self.assertIsInstance(candidate, ReportCandidate)
        self.record = ReportRecord(schema_version=ReportRecord.SCHEMA, binding=binding, plan=plan,
            context=context, stored=candidate.stored, report=candidate.report, proof=candidate.proof)
        self.repository = DjangoReportRepository(environment=Environment.TEST)

    def verify(self, record):
        expected = self.record
        return self.auth.verify(record.report, record.proof, expected.binding, expected.plan, expected.context,
            input_hash=expected.report.input_hash, output_hash=expected.report.output_hash,
            ciphertext_hash=expected.report.ciphertext_hash)


class ReportRecordTests(ReportRecordFixture, TestCase):
    def test_real_candidate_persist_reload_and_proof_without_file_io(self):
        with patch.object(self.crypto, 'open') as opened, patch.object(self.crypto, 'seal') as sealed, \
                patch.object(self.crypto, 'authenticate') as authenticated:
            self.assertEqual(self.repository.put(self.record), self.record)
            self.assertEqual(self.repository.put(self.record), self.record)
            loaded = DjangoReportRepository(environment=Environment.TEST).read(self.record.binding)
            opened.assert_not_called()
            sealed.assert_not_called()
            authenticated.assert_not_called()
        self.assertEqual(loaded, self.record)
        self.assertIs(self.verify(loaded), True)
        self.assertEqual(ExportReport.objects.count(), 1)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.denied(self.store.read(loaded.stored, loaded.context), ReasonCode.AUTHORIZATION_DENIED)
        row = ExportReport.objects.get()
        self.assertEqual(row.document_hash, hashlib.sha256(canonical_bytes(self.record, include_payload=True)).hexdigest())
        self.assertNotIn('a@example.invalid', json.dumps(row.document))
        self.assertEqual(repr(loaded), 'ReportRecord(<redacted>)')
        for cls, value in ((ReportRecord, loaded), (MaskReport, loaded.report)):
            with self.assertRaises(ContractViolation):
                cls.from_wire(value.to_wire(include_payload=True))
        with self.assertRaises(ContractViolation):
            loaded.to_wire()

    def test_retained_readonly_key_verifies_stored_proof_without_new_report(self):
        self.repository.put(self.record)
        original = ExportReport.objects.get().document
        self.auth.key = replace(self.auth.key, status=KeyStatus.READ_ONLY)
        loaded = self.repository.read(self.record.binding)
        with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('readonly signing')):
            self.assertIs(self.verify(loaded), True)
        self.assertIs(self.keys.calls[-1][0].status, KeyStatus.READ_ONLY)
        self.assertEqual(ExportReport.objects.get().document, original)
        self.assertIs(loaded.proof.key.status, KeyStatus.ACTIVE)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.auth.clock = lambda: self.record.binding.expires_at
        self.denied(self.verify(loaded), ReasonCode.AUTHORIZATION_EXPIRED)

    def test_absence_is_distinct_from_error_and_complete_binding_must_match(self):
        self.assertIsNone(self.repository.read(self.record.binding))
        self.assertEqual(self.repository.put(self.record), self.record)
        for changes in ({'quantity': self.record.binding.quantity + 1}, {'subject_ref': 'other/subject'},
                        {'authorization_id': 'authorization/other'}, {'request_fingerprint': '0' * 64},
                        {'execution_id': 'execution/other'}, {'domain_ref': 'domain/other'},
                        {'expires_at': self.record.binding.expires_at + timedelta(seconds=1)}):
            with self.subTest(changes=tuple(changes)):
                binding = replace(self.record.binding, **changes)
                self.denied(self.repository.read(binding), ReasonCode.IDEMPOTENCY_CONFLICT)
                self.denied(self.repository.put(replace(self.record, binding=binding)),
                            ReasonCode.IDEMPOTENCY_CONFLICT)
        other_key = replace(self.record.binding, idempotency_key='idempotency/other')
        self.denied(self.repository.put(replace(self.record, binding=other_key)), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(ExportReport.objects.count(), 1)
        self.assertEqual(self.repository.read(self.record.binding), self.record)

    def test_replayed_record_cannot_replace_report_proof_plan_context_or_file(self):
        self.repository.put(self.record)
        original = ExportReport.objects.get().document
        report_values = dict(self.record.report.content(), hit_count=self.record.report.hit_count + 1)
        changed_report = MaskReport(**report_values, report_hash=content_hash(report_values))
        plan_values = dict(self.record.plan.content(), plan_id='plan/other')
        changed_plan = replace(self.record.plan, plan_id='plan/other', approval=None,
                               plan_hash=content_hash(plan_values))
        for changes in (
            {'proof': replace(self.record.proof, authentication=b'X' * 32)},
            {'context': replace(self.record.context, field_ref='other/field')},
            {'stored': replace(self.record.stored, state='published')},
            {'report': changed_report},
            {'plan': changed_plan},
        ):
            altered = replace(self.record, **changes)
            self.assertNotEqual(altered, self.record)
            self.denied(self.repository.put(altered), ReasonCode.IDEMPOTENCY_CONFLICT)
            self.assertEqual(ExportReport.objects.get().document, original)

    def test_malformed_database_documents_fail_closed_without_public_decoder_bypass(self):
        self.repository.put(self.record)
        original = self.record.to_wire(include_payload=True)
        mutations = []
        for field in ('proof', 'report', 'plan', 'stored', 'context', 'binding'):
            value = deepcopy(original)
            value[field] = None
            mutations.append(value)
        value = deepcopy(original)
        del value['report']['coverage']
        mutations.append(value)
        for field, replacement in (('created_at', 'not-a-time'), ('outcome', 'client-success'),
                                   ('algorithm_versions', 'replace/v1'), ('hit_count', True)):
            value = deepcopy(original)
            value['report'][field] = replacement
            mutations.append(value)
        for target in ('report', None):
            value = deepcopy(original)
            (value[target] if target else value)['extra'] = 'unexpected'
            mutations.append(value)
        for document in mutations:
            ExportReport.objects.update(document=document, document_hash=document_hash(document))
            self.denied(self.repository.read(self.record.binding))
        ExportReport.objects.update(document=original, document_hash=document_hash(original))
        self.assertEqual(self.repository.read(self.record.binding), self.record)

    def test_recomputed_database_hash_does_not_make_forged_mac_trusted(self):
        self.repository.put(self.record)
        forged = replace(self.record, proof=replace(self.record.proof, authentication=b'X' * 32))
        document = forged.to_wire(include_payload=True)
        ExportReport.objects.update(document=document)
        self.denied(self.repository.read(self.record.binding), ReasonCode.REPORT_MISMATCH)
        ExportReport.objects.update(document_hash=document_hash(document))
        loaded = self.repository.read(self.record.binding)
        self.assertEqual(loaded, forged)
        self.denied(self.verify(loaded), ReasonCode.REPORT_MISMATCH)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_expired_records_remain_recoverable_but_do_not_authorize_delivery(self):
        self.repository.put(self.record)
        self.auth.clock = lambda: self.record.binding.expires_at
        loaded = self.repository.read(self.record.binding)
        self.assertEqual(loaded, self.record)
        self.denied(self.verify(loaded), ReasonCode.AUTHORIZATION_EXPIRED)
        with self.assertRaises(ContractViolation):
            DjangoReportRepository(environment=Environment.PRODUCTION)
        production = replace(self.record.binding, environment='production')
        self.denied(self.repository.read(production), ReasonCode.SOURCE_NOT_APPROVED)
        self.denied(self.repository.put(replace(self.record, binding=production)), ReasonCode.SOURCE_NOT_APPROVED)

    def test_database_failure_is_unknown_not_absence_or_success(self):
        with patch.object(ExportReport.objects, 'get_or_create', side_effect=DatabaseError('injected')):
            self.denied(self.repository.put(self.record), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(ExportReport.objects.count(), 0)
        with patch.object(ExportReport.objects, 'filter', side_effect=DatabaseError('injected')):
            self.denied(self.repository.read(self.record.binding), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertTrue(self.path(self.record.stored).exists())


class ReportRecordTransactionTests(ReportRecordFixture, TransactionTestCase):
    def test_record_requires_existing_private_object_and_protects_its_reference(self):
        absent = replace(self.record.stored, object_ref='private/' + '0' * 64)
        self.denied(self.repository.put(replace(self.record, stored=absent)), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(ExportReport.objects.count(), 0)
        self.assertEqual(self.repository.put(self.record), self.record)
        with self.assertRaises(ProtectedError):
            PrivateObject.objects.get().delete()
        self.assertTrue(self.path(self.record.stored).exists())

    def test_short_uow_can_rollback_report_without_removing_ciphertext(self):
        self.assertFalse(connection.in_atomic_block)
        with DjangoUnitOfWork():
            self.assertEqual(self.repository.put(self.record), self.record)
        self.assertEqual(ExportReport.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertTrue(self.path(self.record.stored).exists())
        with self.assertRaisesMessage(RuntimeError, 'audit failed'):
            with DjangoUnitOfWork() as uow:
                self.repository.put(self.record)
                uow.commit()
                raise RuntimeError('audit failed')
        self.assertIsNone(self.repository.read(self.record.binding))
        with DjangoUnitOfWork() as uow:
            self.repository.put(self.record)
            uow.commit()
        self.assertEqual(self.repository.read(self.record.binding), self.record)

    def test_concurrent_same_record_is_idempotent_and_conflicting_record_cannot_overwrite(self):
        self.assertEqual(connection.vendor, 'postgresql')
        def race(records):
            barrier = Barrier(2)
            def write(record):
                close_old_connections()
                try:
                    barrier.wait(timeout=10)
                    return DjangoReportRepository(environment=Environment.TEST).put(record)
                finally:
                    close_old_connections()
            with ThreadPoolExecutor(max_workers=2) as workers:
                return list(workers.map(write, records))
        self.assertEqual(race([self.record, self.record]), [self.record, self.record])
        self.assertEqual(ExportReport.objects.count(), 1)
        # A new execution starts absent, so neither conflicting contender has priority.
        binding = replace(self.record.binding, execution_id='execution/next', idempotency_key='idempotency/next')
        first = replace(self.record, binding=binding)
        second = replace(first, context=replace(first.context, field_ref='other/field'))
        results = race([first, second])
        self.assertEqual(sum(isinstance(r, ReportRecord) for r in results), 1)
        self.assertEqual(sum(isinstance(r, ProtectionError) and r.code is ReasonCode.IDEMPOTENCY_CONFLICT
                             for r in results), 1)
        stored = self.repository.read(binding)
        self.assertEqual(stored, next(r for r in results if isinstance(r, ReportRecord)))
        self.assertEqual(ExportReport.objects.count(), 2)
