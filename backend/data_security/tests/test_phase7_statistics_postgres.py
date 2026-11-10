"""New statistics checks on synthetic PostgreSQL, not a cumulative test run.

Reports are server-signed metadata fixtures, not fresh exports or deliveries.
No previous TestCase class is imported or re-run.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from unittest.mock import Mock, patch
from uuid import uuid4

from django.db import DatabaseError, connection
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent, AuthenticatedAuditEntry
from ctf_backend import security_bootstrap as bootstrap
from data_security.adapters.django import statistics_api
from data_security.adapters.persistence import fields as field_module
from data_security.adapters.persistence.models import ExportReport, PrivateObject
from data_security.application.reports import ReportAuthenticator
from data_security.contracts import (
    ActionPlan, Coverage, Environment, ExecutionBinding, MaskReport, ObjectContext, ProtectionError,
    ReasonCode, ReportProof, ReportRecord, StoredObject, Unit, canonical_bytes, content_hash,
)
from data_security.tests.fixtures import AT, examples
from data_security.tests.phase4_fixtures import field_configuration
from users.models import CTFUser

BASE = '/api/data-security/stats/'
MARKER = 'statistics-private@example.invalid'


class StatisticsPostgresTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL, never SQLite')
        files = field_configuration()
        self.path, self.config, _, _ = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        checkpoints = self.path.parent / 'statistics-checkpoints'
        checkpoints.mkdir(mode=0o700)
        self.config['audit_chain'] = {
            'chain_version': 'ds.audit.v2', 'project_ref': 'phase7/statistics-synthetic',
            'object_uuid': '00000000-0000-4000-8000-000000000017', 'object_version': 'v1',
            'authorization_ref': 'authorization/phase7-statistics', 'retained_keys': [],
            'checkpoint_root': str(checkpoints), 'checkpoint_ref': None,
        }
        self.path.write_text(json.dumps(self.config))
        self.components = bootstrap.assemble(config_path=self.path)
        self.reader = self.components['statistics']
        self.reports = self.reader.keywords['reports']
        self.crypto = self.components['crypto']
        self.signer = ReportAuthenticator(crypto=self.crypto, key=self.components['audit'].sink.key,
            executor_ref='service/resource-column-export', environment=Environment.EVALUATION,
            clock=lambda: AT + timedelta(seconds=1))
        for module, name, value in ((statistics_api, '_reader', self.reader), (field_module, '_adapter', None)):
            replacement = patch.object(module, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.client = APIClient()
        self.admin = CTFUser.objects.create_user(username='statistics-admin', role='admin', email=MARKER)
        self.client.force_authenticate(user=self.admin)

    def retain(self, *, eligible=3, excluded=1, rescan_eligible=2, coverage_version='statistics-coverage.v1',
               asset_version='asset/statistics-v1'):
        values = examples()
        suffix = uuid4().hex
        execution = replace(values[ExecutionBinding], execution_id='statistics/' + suffix,
            idempotency_key='statistics/idempotency/' + suffix, environment='evaluation', domain_ref='ctf',
            asset_version=asset_version, policy_binding=self.components['binding'])
        source = replace(values[ActionPlan].source, source_environment='evaluation', source_domain='ctf',
            approval_basis_ref='approval/statistics-synthetic', approval_basis_version='v1')
        plan_values = dict(values[ActionPlan].content(), source=source, asset_version=asset_version,
                           policy_binding=execution.policy_binding)
        plan = ActionPlan(**plan_values, plan_hash=content_hash(plan_values), approval=None)
        context = replace(values[ObjectContext], environment=Environment.EVALUATION, object_uuid=str(uuid4()),
            object_version=asset_version, authorization_ref=execution.authorization_id)
        stored = replace(values[StoredObject], object_ref='private/statistics-' + suffix,
                         version=asset_version, state='verified', ciphertext_hash='2' * 64)
        coverage = Coverage(schema_version=Coverage.SCHEMA, unit=Unit.CELL, total=eligible + excluded,
            eligible=eligible, processed=eligible, excluded=excluded, failed=0, unknown=0, unscanned=0,
            version=coverage_version)
        rescan = replace(coverage, unit=Unit.FIELD, total=rescan_eligible, eligible=rescan_eligible,
                         processed=rescan_eligible, excluded=0, version='statistics-rescan.v1')
        report_values = dict(values[MaskReport].content(), execution_id=execution.execution_id,
            executor_ref=self.signer.executor_ref, asset_version=asset_version, source=source,
            action_plan_hash=plan.plan_hash, policy_binding=execution.policy_binding,
            algorithm_versions=tuple(sorted({a.algorithm.algorithm.value + '/' + a.algorithm.version
                                             for a in plan.actions})),
            coverage=coverage, rescan_coverage=rescan, hit_count=0 if eligible == 0 else 1,
            ciphertext_hash=stored.ciphertext_hash)
        report = MaskReport(**report_values, report_hash=content_hash(report_values))
        proof = self.signer.issue(report, execution, plan, context, input_hash=plan.input_hash,
                                 output_hash=report.output_hash, ciphertext_hash=stored.ciphertext_hash)
        self.assertIsInstance(proof, ReportProof)
        record = ReportRecord(schema_version=ReportRecord.SCHEMA, binding=execution, plan=plan,
                              context=context, stored=stored, report=report, proof=proof)
        PrivateObject.objects.create(object_ref=stored.object_ref, version=stored.version,
            context_hash=content_hash(context), ciphertext_hash=stored.ciphertext_hash,
            size_bytes=stored.size_bytes, state=stored.state)
        self.assertEqual(self.reports.put(record), record)
        return ExportReport.objects.get(execution_id=execution.execution_id), record

    def get(self, query=''):
        response = self.client.get(BASE + query)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        self.assertEqual(response['Pragma'], 'no-cache')
        return response

    def test_only_active_admins_can_read_metadata(self):
        blocked = [None]
        for role in ('student', 'teacher', 'admin'):
            blocked.append(CTFUser.objects.create_user(username='statistics-denied-' + role, role=role,
                is_active=role != 'admin', is_staff=True, is_superuser=True))
        with patch.object(statistics_api, '_reader', Mock()) as reader:
            for user in blocked:
                with self.subTest(role=None if user is None else user.role):
                    self.client.force_authenticate(user=user)
                    self.assertEqual(self.get().status_code, 403)
            reader.assert_not_called()
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.get().status_code, 200)

    def test_unbound_and_reader_failure_are_not_empty_success(self):
        with patch.object(statistics_api, '_reader', None):
            response = self.get()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.data, {'code': 'POLICY_NOT_APPROVED', 'state': 'disabled'})
        with patch.object(ExportReport.objects, 'order_by', side_effect=DatabaseError(MARKER)):
            response = self.get()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.data, {'code': 'AUDIT_UNAVAILABLE', 'state': 'unknown'})
            self.assertNotIn(MARKER, json.dumps(response.data))

    def test_http_accepts_only_bounded_offset_and_no_writes(self):
        with patch.object(statistics_api, '_reader', Mock()) as reader:
            for query in ('?role=admin', '?accepted=true', '?offset=-1', '?offset=100001',
                          '?offset=x', '?offset=1&offset=2', '?limit=100'):
                with self.subTest(query=query):
                    self.assertEqual(self.get(query).status_code, 400)
            response = self.client.post(BASE, {'original': MARKER}, format='json')
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response['Cache-Control'], 'no-store, private')
            self.assertNotIn(MARKER, json.dumps(response.data))
            reader.assert_not_called()

    def test_empty_source_is_unknown_not_measured_zero(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['unknown_records'], 0)
        self.assertIsNone(response.data['next_offset'])
        self.assertEqual(response.data['state'], 'enabled-unverified')
        self.assertEqual({item['unit'] for item in response.data['unknown_sources']}, {'field', 'text', 'outlet'})
        for item in response.data['unknown_sources']:
            self.assertIsNone(item['numerator'])
            self.assertIsNone(item['denominator'])
            self.assertIsNone(item['ratio'])
            self.assertIsNone(item['zero_reason'])
            self.assertTrue(item['reason'])
        states = {item['capability']: item['state'] for item in response.data['capabilities']}
        self.assertEqual(states, {'field-protection': 'enabled-unverified', 'text-rag': 'enabled-unverified',
            'reveal-requests': 'disabled', 'resource-export': 'disabled', 'private-files': 'disabled'})
        self.assertNotIn('accepted', states.values())

    def test_authenticated_coverage_keeps_stages_units_and_versions_separate(self):
        row1, first = self.retain()
        row2, second = self.retain(eligible=7, excluded=2, coverage_version='statistics-coverage.v2',
                                   asset_version='asset/statistics-v2')
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['items']), 2)
        by_id = {item['id']: item for item in response.data['items']}
        for row, record in ((row1, first), (row2, second)):
            with self.subTest(record=row.pk):
                item = by_id[row.pk]
                self.assertEqual(item['integrity'], 'verified')
                self.assertIsNone(item['reason'])
                self.assertEqual(item['environment'], 'evaluation')
                self.assertEqual(item['source_trust'], 'synthetic')
                self.assertEqual(item['rescan_state'], 'complete')
                self.assertEqual(item['versions']['policy_binding'], record.report.policy_binding.to_wire())
                self.assertEqual(item['versions']['adapter'], record.plan.adapter_version)
                self.assertEqual(item['versions']['asset'], record.report.asset_version)
                self.assertEqual(item['versions']['audit_key'], record.proof.key.to_wire())
                self.assertEqual([m['stage'] for m in item['measurements']], ['processing', 'rescan'])
                for actual, expected in zip(item['measurements'], (record.report.coverage, record.report.rescan_coverage)):
                    for key, value in expected.to_wire().items():
                        self.assertEqual(actual[key], value)
                    self.assertEqual(actual['numerator'], expected.processed)
                    self.assertEqual(actual['denominator'], expected.eligible)
                    self.assertLessEqual(actual['numerator'], actual['denominator'])
                    self.assertEqual(actual['ratio'], expected.ratio)
                    self.assertIsNone(actual['zero_reason'])
                self.assertEqual([m['unit'] for m in item['measurements']], ['cell', 'field'])
        self.assertNotEqual(by_id[row1.pk]['measurements'][0]['version'], by_id[row2.pk]['measurements'][0]['version'])
        self.assertEqual(response.data['unknown_records'], 0)
        self.assertNotIn('ratio', response.data)

    def test_zero_eligible_has_null_ratio_with_a_distinct_reason(self):
        self.retain(eligible=0, excluded=4, rescan_eligible=0)
        item, = self.get().data['items']
        self.assertEqual(item['integrity'], 'verified')
        for measurement in item['measurements']:
            self.assertEqual(measurement['numerator'], 0)
            self.assertEqual(measurement['denominator'], 0)
            self.assertIsNone(measurement['ratio'])
            self.assertEqual(measurement['zero_reason'], 'NO_ELIGIBLE_UNITS')
        self.assertEqual(item['measurements'][0]['excluded'], 4)
        self.assertEqual(item['measurements'][0]['total'], 4)

    def test_historical_mac_does_not_assert_current_authorization_or_delivery(self):
        row, record = self.retain()
        current = ReportAuthenticator(crypto=self.crypto, key=self.components['audit'].sink.key,
            executor_ref=self.signer.executor_ref, environment=Environment.EVALUATION,
            clock=lambda: AT + timedelta(days=1))
        result = current.verify(record.report, record.proof, record.binding, record.plan, record.context,
            input_hash=record.plan.input_hash, output_hash=record.report.output_hash,
            ciphertext_hash=record.stored.ciphertext_hash)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_EXPIRED)
        response = self.get()
        self.assertEqual(response.data['state'], 'enabled-unverified')
        self.assertEqual(response.data['scope'], 'retained-report-page')
        self.assertEqual(response.data['items'][0]['integrity'], 'verified')
        row.refresh_from_db()
        self.assertIsNone(row.delivery_receipt)
        self.assertNotIn('delivered', json.dumps(response.data))
        self.assertNotIn('accepted', json.dumps(response.data))

    def test_read_never_opens_payload_signs_writes_or_returns_private_documents(self):
        row, record = self.retain()
        before = (list(ExportReport.objects.values()), list(PrivateObject.objects.values()),
                  AuditEvent.objects.count(), AuthenticatedAuditEntry.objects.count())
        with patch.object(self.crypto, 'open') as opened, patch.object(self.crypto, 'authenticate') as signed, \
                patch.object(self.reports, 'put') as written, \
                patch.object(self.crypto, 'verify_authentication', wraps=self.crypto.verify_authentication) as verified:
            response = self.get()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['items'][0]['integrity'], 'verified')
            opened.assert_not_called()
            signed.assert_not_called()
            written.assert_not_called()
            verified.assert_called_once()
        after = (list(ExportReport.objects.values()), list(PrivateObject.objects.values()),
                 AuditEvent.objects.count(), AuthenticatedAuditEntry.objects.count())
        self.assertEqual(after, before)
        rendered = json.dumps(response.data)
        for private in (MARKER, record.stored.object_ref, record.context.object_uuid,
                        record.binding.execution_id, record.proof.to_wire()['authentication']):
            self.assertNotIn(private, rendered)
        for field in ('document', 'proof', 'authentication', 'ciphertext_hash', 'output_hash', 'originals'):
            self.assertNotIn('"' + field + '"', rendered)

    def test_preparing_missing_or_aborted_records_never_become_scan_success(self):
        row, _ = self.retain()
        row.state, row.document, row.document_hash, row.private_object = 'preparing', None, '', None
        row.save(update_fields=['state', 'document', 'document_hash', 'private_object'])
        for state in ('preparing', 'aborted'):
            with self.subTest(state=state):
                ExportReport.objects.filter(pk=row.pk).update(state=state)
                with patch.object(self.crypto, 'verify_authentication') as verified:
                    data = self.get().data
                    verified.assert_not_called()
                item, = data['items']
                self.assertEqual(item['integrity'], 'unknown')
                self.assertEqual(item['reason'], 'REPORT_NOT_AVAILABLE')
                self.assertEqual(item['measurements'], [])
                self.assertIsNone(item['versions'])
                self.assertEqual(data['unknown_records'], 1)

    def test_recomputed_public_hashes_cannot_forge_coverage_statistics(self):
        row, record = self.retain()
        changed_coverage = replace(record.report.coverage, total=100, eligible=100, processed=100, excluded=0)
        values = dict(record.report.content(), coverage=changed_coverage)
        changed_report = MaskReport(**values, report_hash=content_hash(values))
        changed_proof = replace(record.proof, report_hash=changed_report.report_hash)
        forged = replace(record, report=changed_report, proof=changed_proof)
        row.document = forged.to_wire(include_payload=True)
        row.document_hash = hashlib.sha256(canonical_bytes(forged, include_payload=True)).hexdigest()
        row.save(update_fields=['document', 'document_hash'])
        self.assertEqual(self.reports.read(record.binding), forged)
        data = self.get().data
        item, = data['items']
        self.assertEqual(item['integrity'], 'unknown')
        self.assertEqual(item['reason'], 'REPORT_MISMATCH')
        self.assertEqual(item['measurements'], [])
        self.assertEqual(data['unknown_records'], 1)

    def test_invalid_coverage_at_database_boundary_stays_unknown(self):
        row, _ = self.retain()
        document = deepcopy(row.document)
        document['report']['coverage']['processed'] = document['report']['coverage']['eligible'] + 1
        row.document = document
        encoded = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        row.document_hash = hashlib.sha256(encoded).hexdigest()
        row.save(update_fields=['document', 'document_hash'])
        with patch.object(self.crypto, 'verify_authentication') as verified:
            data = self.get().data
            verified.assert_not_called()
        self.assertEqual(data['items'][0]['integrity'], 'unknown')
        self.assertEqual(data['items'][0]['measurements'], [])
        self.assertEqual(data['unknown_records'], 1)

    def test_missing_current_key_never_falls_back_to_a_self_asserted_report(self):
        _, record = self.retain()
        with patch.dict(self.components['audit'].sink.keys, {}, clear=True), \
                patch.object(self.crypto, 'verify_authentication') as verified:
            data = self.get().data
            verified.assert_not_called()
        item, = data['items']
        self.assertEqual(item['integrity'], 'unknown')
        self.assertEqual(item['reason'], 'KEY_UNAVAILABLE')
        self.assertEqual(item['measurements'], [])
        self.assertEqual(data['unknown_records'], 1)

    def test_fixed_page_limit_does_not_silently_hide_unknown_records(self):
        for index in range(21):
            ExportReport.objects.create(execution_id='statistics/pending-' + str(index),
                idempotency_key='statistics/pending-' + str(index), binding_hash='0' * 64, state='preparing')
        first = self.get().data
        self.assertEqual(first['limit'], 20)
        self.assertEqual(len(first['items']), 20)
        self.assertEqual(first['unknown_records'], 20)
        self.assertEqual(first['next_offset'], 20)
        second = self.get('?offset=20').data
        self.assertEqual(len(second['items']), 1)
        self.assertEqual(second['unknown_records'], 1)
        self.assertIsNone(second['next_offset'])
        self.assertFalse({item['id'] for item in first['items']} & {item['id'] for item in second['items']})
        self.assertEqual(ExportReport.objects.count(), 21)
