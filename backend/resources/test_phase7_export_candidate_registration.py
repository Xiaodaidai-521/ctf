"""New export intentions through real owners; no orphan scan, cleanup or restore."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import os
from unittest.mock import Mock, patch
from uuid import uuid4

from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.django import export_delivery
from data_security.adapters.persistence.models import ExportReport, PrivateObject
from data_security.adapters.persistence.private_store import DjangoPrivateStore
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.application.reports import ReportAuthenticator
from data_security.contracts import (
    AuditReceipt, BASELINE_LIMITS, BoundedPayload, ContractViolation, Durability, Environment, EventKind,
    FrozenJSON, MediaType, ObjectContext, Outcome, PayloadKind, ProtectionContext, ProtectionError,
    Purpose, ReasonCode, ReportRecord, Role, SecurityEventV2, StoredObject, canonical_bytes, content_hash,
)
from data_security.tests.fixtures import examples
from export_quota.models import QuotaBucket

from .test_phase6_formal_fixtures import CONTENT, FormalResourceFixture


class ExportCandidateRegistrationTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def setUp(self):
        super().setUp()
        self.scope = 'retention/phase7-candidate-synthetic'
        self.config['export_retention'] = {'scope_ref': self.scope}
        self.write_config()
        self.components = assemble(config_path=self.config_path)
        self.entry = self.components['export_delivery']
        self.sources, self.risks = self.entry.sources, self.entry.risks
        self.lifecycle = self.components['export_lifecycle']
        self.sink = self.components['audit'].sink
        for setting in (patch.object(export_delivery, '_entry', self.entry),
                        patch.dict(os.environ, DATA_SECURITY_CONFIG=str(self.config_path)),
                        override_settings(ALLOWED_HOSTS=['testserver'], MIDDLEWARE=[])):
            self.enterContext(setting)
        self.client = APIClient()
        self.client.force_authenticate(self.teacher)

    def ready_http(self):
        source_ref, permission_ref, _, binding = self.ready()
        return {'source_ref': source_ref, 'permission_ref': permission_ref}, binding

    def execute(self, body):
        return self.client.post('/api/data-security/exports/resources/execute/', body, format='json')

    def assert_candidate(self, row):
        item = row.retention_candidate
        self.assertEqual(set(item), {'schema_version', 'intent_hash', 'context', 'stored',
                                     'generated_at', 'registration'})
        self.assertEqual(item['schema_version'], 'ds.export-candidate.v1')
        self.assertEqual(item['intent_hash'], row.intent_hash)
        context = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})
        stored = StoredObject.from_wire(item['stored'])
        self.assertEqual(stored.state, 'candidate')
        binding = self.lifecycle.reports.load_binding(row.execution_id)
        generated_at = datetime.fromisoformat(item['generated_at'])
        digest = content_hash({'domain': 'ds.export-candidate.v1', 'scope': self.scope,
            'binding': binding, 'intent_hash': row.intent_hash, 'context': context,
            'stored': stored, 'generated_at': generated_at})
        receipt = AuditReceipt.from_wire(item['registration'])
        self.assertEqual((receipt.event_id, receipt.durability, receipt.chain_version),
                         (digest, Durability.LEDGER_CONFIRMED, 'ds.audit.v2'))
        event = self.sink.read_authenticated(receipt.event_id)
        self.assertIsInstance(event, SecurityEventV2)
        self.assertEqual((event.event_id, event.kind, event.actor_ref, event.object_ref, event.object_version,
                          event.outcome, event.occurred_at, event.counts, event.policy_binding,
                          event.algorithm_versions, event.key_versions, event.correlation_ref, event.reason,
                          event.evidence_hashes),
            (digest, EventKind.AUTHORIZATION, 'service/security', stored.object_ref, stored.version,
             Outcome.SUCCEEDED, generated_at, (('processed', 1), ('bytes', stored.size_bytes)), binding.policy_binding,
             ('ds.export-candidate.v1', 'stage'), (self.components['data_ref'].key_ref,), self.scope, None,
             (('ciphertext', stored.ciphertext_hash), ('report', digest))))
        wire = json.dumps({'candidate': item, 'event': event.to_wire()})
        self.assertNotIn('first@example.invalid', wire)
        self.assertNotIn('second@example.invalid', wire)
        self.assertNotIn(CONTENT.decode(), wire)
        return context, stored

    def path(self, stored):
        return self.root / (stored.object_ref.removeprefix('private/') + '.sealed')

    def assert_file(self, stored):
        encoded = self.path(stored).read_bytes()
        self.assertEqual((len(encoded), hashlib.sha256(encoded).hexdigest()),
                         (stored.size_bytes, stored.ciphertext_hash))

    def test_http_candidate_intention_is_committed_before_file_creation_and_kept_after_delivery(self):
        body, binding = self.ready_http()
        write = DjangoPrivateStore.write_candidate
        observed = []

        def observe(store, envelope, context):
            self.assertFalse(connection.in_atomic_block)
            row = ExportReport.objects.get(execution_id=binding.execution_id)
            self.assertIsNone(row.document)
            self.assertIsNone(row.private_object_id)
            registered_context, stored = self.assert_candidate(row)
            self.assertEqual(registered_context, context)
            self.assertEqual(hashlib.sha256(canonical_bytes(envelope)).hexdigest(), stored.ciphertext_hash)
            self.assertFalse(self.path(stored).exists())
            self.assertFalse(PrivateObject.objects.filter(object_ref=stored.object_ref).exists())
            observed.append(row.retention_candidate)
            return write(store, envelope, context)

        with patch.object(DjangoPrivateStore, 'write_candidate', new=observe):
            response = self.execute(body)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['network_delivery_confirmed'])
        self.assertEqual(len(observed), 1)
        row = ExportReport.objects.get(execution_id=binding.execution_id)
        self.assertEqual(row.retention_candidate, observed[0])
        context, stored = self.assert_candidate(row)
        record = self.lifecycle.reports.read(binding)
        self.assertIsInstance(record, ReportRecord)
        self.assertEqual((record.context, replace(record.stored, state='candidate')), (context, stored))
        self.assertGreaterEqual(record.report.created_at, datetime.fromisoformat(observed[0]['generated_at']))
        self.assertEqual(PrivateObject.objects.get(object_ref=stored.object_ref).state, 'published')
        self.assert_file(stored)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)

    def test_file_survives_failed_private_registration_with_its_exact_prewrite_identity(self):
        body, binding = self.ready_http()
        with patch.object(PrivateObject.objects, 'get_or_create', side_effect=DatabaseError('synthetic insert failure')):
            response = self.execute(body)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data['code'], 'DELIVERY_UNKNOWN')
        row = ExportReport.objects.get(execution_id=binding.execution_id)
        self.assertEqual(row.state, 'aborted')
        self.assertIsNone(row.document)
        self.assertIsNone(row.private_object_id)
        _, stored = self.assert_candidate(row)
        self.assertFalse(PrivateObject.objects.filter(object_ref=stored.object_ref).exists())
        self.assert_file(stored)
        self.assertEqual(QuotaBucket.objects.get().settled, 0)
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())

    def test_failed_verification_keeps_an_enrolled_unpublished_candidate_without_a_report(self):
        body, binding = self.ready_http()
        error = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.REPORT_MISMATCH,
                                retryable=False, trace_id='candidate/synthetic-verify')
        with patch.object(DjangoPrivateStore, 'verify', return_value=error):
            response = self.execute(body)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data['code'], 'REPORT_MISMATCH')
        row = ExportReport.objects.get(execution_id=binding.execution_id)
        _, stored = self.assert_candidate(row)
        self.assertEqual(PrivateObject.objects.get(object_ref=stored.object_ref).state, 'candidate')
        self.assertIsNone(row.document)
        self.assertIsNone(row.private_object_id)
        self.assert_file(stored)
        self.assertEqual(QuotaBucket.objects.get().settled, 0)

    def test_failed_report_proof_keeps_the_verified_candidate_without_claiming_delivery(self):
        body, binding = self.ready_http()
        error = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.REPORT_MISMATCH,
                                retryable=False, trace_id='candidate/synthetic-proof')
        with patch.object(ReportAuthenticator, 'issue', return_value=error):
            response = self.execute(body)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data['code'], 'REPORT_MISMATCH')
        row = ExportReport.objects.get(execution_id=binding.execution_id)
        _, stored = self.assert_candidate(row)
        self.assertEqual(PrivateObject.objects.get(object_ref=stored.object_ref).state, 'verified')
        self.assertIsNone(row.document)
        self.assertIsNone(row.delivery_receipt)
        self.assert_file(stored)
        self.assertEqual(QuotaBucket.objects.get().settled, 0)

    def test_bad_authenticated_receipt_rolls_back_intention_before_any_output_file(self):
        body, binding = self.ready_http()
        inputs = {path.name: path.read_bytes() for path in self.root.glob('*.sealed')}
        record, attempted = self.lifecycle.audit.record, []

        def bad_receipt(event, durability):
            receipt = record(event, durability)
            if event.algorithm_versions == ('ds.export-candidate.v1', 'stage'):
                self.assertTrue(AuthenticatedAuditEntry.objects.filter(record__event_id=event.event_id).exists())
                attempted.append(event.event_id)
                return replace(receipt, event_id='f' * 64)
            return receipt

        with patch.object(self.lifecycle.audit, 'record', side_effect=bad_receipt):
            response = self.execute(body)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data['code'], 'AUDIT_UNAVAILABLE')
        self.assertEqual(len(attempted), 1)
        row = ExportReport.objects.get(execution_id=binding.execution_id)
        self.assertEqual(row.retention_scope, self.scope)
        self.assertIsNone(row.retention_candidate)
        self.assertIsNone(row.document)
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id=attempted[0]).exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.filter(record__event_id=attempted[0]).exists())
        self.assertEqual({path.name: path.read_bytes() for path in self.root.glob('*.sealed')}, inputs)
        self.assertEqual(QuotaBucket.objects.get().settled, 0)

    def test_report_attachment_rejects_different_intent_context_or_ciphertext_identity(self):
        body, binding = self.ready_http()
        put, observed = DjangoReportRepository.put, []

        def check(repository, record):
            row = ExportReport.objects.get(execution_id=binding.execution_id)
            original = row.retention_candidate
            for field in ('intent_hash', 'context', 'stored'):
                with self.subTest(field=field):
                    changed = deepcopy(original)
                    if field == 'intent_hash':
                        changed[field] = 'f' * 64
                    elif field == 'context':
                        changed[field]['object_uuid'] = str(uuid4())
                    else:
                        changed[field]['object_ref'] = 'private/' + 'f' * 64
                    ExportReport.objects.filter(pk=row.pk).update(retention_candidate=changed)
                    refused = put(repository, record)
                    self.assertIsInstance(refused, ProtectionError)
                    self.assertEqual(refused.code, ReasonCode.REPORT_MISMATCH)
                    row.refresh_from_db()
                    self.assertIsNone(row.document)
                    self.assertIsNone(row.private_object_id)
                    observed.append(field)
            ExportReport.objects.filter(pk=row.pk).update(retention_candidate=original)
            return put(repository, record)

        with patch.object(DjangoReportRepository, 'put', new=check):
            response = self.execute(body)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(observed, ['intent_hash', 'context', 'stored'])
        row = ExportReport.objects.get(execution_id=binding.execution_id)
        self.assert_candidate(row)
        self.assertIsNotNone(row.document)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)

    def test_disabled_configuration_and_later_enablement_do_not_adopt_prior_outputs(self):
        del self.config['export_retention']
        self.write_config()
        disabled = assemble(config_path=self.config_path)
        self.entry = disabled['export_delivery']
        self.sources, self.risks = self.entry.sources, self.entry.risks
        body, binding = self.ready_http()
        with patch.object(export_delivery, '_entry', self.entry):
            response = self.execute(body)
        self.assertEqual(response.status_code, 200, response.data)
        row = ExportReport.objects.get(execution_id=binding.execution_id)
        self.assertIsNone(row.retention_scope)
        self.assertIsNone(row.retention_candidate)
        original = row.document
        inputs = {path.name: path.read_bytes() for path in self.root.glob('*.sealed')}
        self.config['export_retention'] = {'scope_ref': self.scope}
        self.write_config()
        enabled = assemble(config_path=self.config_path)['export_lifecycle']
        context = replace(examples()[ProtectionContext], actor_ref='service/security', role=Role.SERVICE,
            environment=Environment.EVALUATION, domain='ctf', purpose=Purpose.STORAGE)
        preview = enabled.preview(context)
        self.assertIsInstance(preview, FrozenJSON)
        self.assertEqual(preview.to_value()['exports'], [])
        row.refresh_from_db()
        self.assertIsNone(row.retention_scope)
        self.assertIsNone(row.retention_candidate)
        self.assertEqual(row.document, original)
        self.assertEqual({path.name: path.read_bytes() for path in self.root.glob('*.sealed')}, inputs)

    def test_stage_rejects_outer_transactions_other_fields_and_unenrolled_fences(self):
        body, _ = self.ready_http()
        owned = self.ok(self.entry._bound(user=self.teacher, **body))
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
            media_type=MediaType.CSV, binary=b'Email\n[EMAIL]\n', text=None, tree=None, limits=BASELINE_LIMITS)
        envelope = self.ok(self.components['crypto'].seal(payload, owned.context, self.components['data_ref']))
        with transaction.atomic():
            with self.assertRaises(ContractViolation) as error:
                self.lifecycle.stage_candidate(owned.plan, owned.binding, owned.context, envelope)
        self.assertEqual(error.exception.code, ReasonCode.SOURCE_NOT_APPROVED)
        with self.assertRaises(ContractViolation) as error:
            self.lifecycle.stage_candidate(owned.plan, owned.binding,
                replace(owned.context, field_ref='resources/file'), envelope)
        self.assertEqual(error.exception.code, ReasonCode.SOURCE_NOT_APPROVED)
        repository = DjangoReportRepository(environment=Environment.EVALUATION)
        with transaction.atomic():
            self.assertIs(repository.begin(owned.plan, owned.binding, owned.context), True)
        with self.assertRaises(ContractViolation) as error:
            self.lifecycle.stage_candidate(owned.plan, owned.binding, owned.context, envelope)
        self.assertEqual(error.exception.code, ReasonCode.SOURCE_NOT_APPROVED)
        repository.lifecycle = self.lifecycle
        with transaction.atomic():
            self.assertIs(repository.begin(owned.plan, owned.binding, owned.context), False)
        row = ExportReport.objects.get(execution_id=owned.binding.execution_id)
        self.assertIsNone(row.retention_scope)
        self.assertIsNone(row.retention_candidate)
        self.assertFalse(SecurityAuditRecord.objects.filter(event__algorithm_versions=['ds.export-candidate.v1', 'stage']).exists())

    def test_new_fence_accepts_only_one_exact_in_time_candidate_intention(self):
        body, _ = self.ready_http()
        owned = self.ok(self.entry._bound(user=self.teacher, **body))
        repository = DjangoReportRepository(environment=Environment.EVALUATION, lifecycle=self.lifecycle)
        with transaction.atomic():
            self.assertIs(repository.begin(owned.plan, owned.binding, owned.context), True)
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
            media_type=MediaType.CSV, binary=b'Email\n[EMAIL]\n', text=None, tree=None, limits=BASELINE_LIMITS)
        envelope = self.ok(self.components['crypto'].seal(payload, owned.context, self.components['data_ref']))
        with self.assertRaises(ContractViolation) as error:
            self.lifecycle.stage_candidate(owned.plan, owned.binding,
                replace(owned.context, object_uuid=str(uuid4())), envelope)
        self.assertEqual(error.exception.code, ReasonCode.IDEMPOTENCY_CONFLICT)
        with patch.object(self.lifecycle, 'clock', return_value=owned.binding.expires_at):
            with self.assertRaises(ContractViolation) as error:
                self.lifecycle.stage_candidate(owned.plan, owned.binding, owned.context, envelope)
        self.assertEqual(error.exception.code, ReasonCode.AUTHORIZATION_EXPIRED)
        stored = self.lifecycle.stage_candidate(owned.plan, owned.binding, owned.context, envelope)
        self.assertIsInstance(stored, StoredObject)
        row = ExportReport.objects.get(execution_id=owned.binding.execution_id)
        self.assertEqual(self.assert_candidate(row)[1], stored)
        original = row.retention_candidate
        self.assertFalse(self.path(stored).exists())
        self.assertFalse(PrivateObject.objects.filter(object_ref=stored.object_ref).exists())
        for candidate in (envelope, self.ok(self.components['crypto'].seal(
                payload, owned.context, self.components['data_ref']))):
            with self.assertRaises(ContractViolation) as error:
                self.lifecycle.stage_candidate(owned.plan, owned.binding, owned.context, candidate)
            self.assertEqual(error.exception.code, ReasonCode.IDEMPOTENCY_CONFLICT)
        row.refresh_from_db()
        self.assertEqual(row.retention_candidate, original)
        self.assertEqual(SecurityAuditRecord.objects.filter(event__algorithm_versions=['ds.export-candidate.v1', 'stage']).count(), 1)

    def test_canary_executor_branch_keeps_the_same_stage_callback(self):
        body, binding = self.ready_http()
        checker = Mock()
        checker.check.return_value = ()
        self.components['canary'] = {'owner': Mock(), 'seeds': Mock()}
        with patch('data_security.application.canary.CanaryTools', return_value=checker):
            response = self.execute(body)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(checker.check.call_count, 2)
        row = ExportReport.objects.get(execution_id=binding.execution_id)
        self.assert_candidate(row)
        self.assertIsNotNone(row.document)


class ExportCandidateRegistrationMigrationTests(TransactionTestCase):
    def test_additive_migration_leaves_existing_fences_and_reports_unenrolled(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
        old = [('security_policies', '0017_reveal_retention_registration')]
        new = [('security_policies', '0018_export_candidate_registration')]
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(targets))
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        model = apps.get_model('security_policies', 'ExportReport')
        values = dict(execution_id='candidate/migration', idempotency_key='candidate/migration-idempotency',
            binding_hash='a' * 64, binding_document={'synthetic': 'retained-binding'}, intent_hash='b' * 64,
            state='preparing', retention_scope='retention/previous-synthetic',
            retention_registration={'synthetic': 'retained-receipt'})
        row = model.objects.create(**values)
        for cycle in range(2):
            with self.subTest(cycle=cycle):
                executor = MigrationExecutor(connection)
                executor.migrate(new)
                model = executor.loader.project_state(new).apps.get_model('security_policies', 'ExportReport')
                restored = model.objects.get(pk=row.pk)
                self.assertIsNone(restored.retention_candidate)
                for name, value in values.items():
                    self.assertEqual(getattr(restored, name), value)
                self.assertIsNone(restored.document)
                self.assertIsNone(restored.private_object_id)
                if cycle == 0:
                    MigrationExecutor(connection).migrate(old)
