"""Synthetic PG enrollment, MACs and private files; not full exports or expiry deletion."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from audit.models import AuthenticatedAuditEntry
from ctf_backend import security_bootstrap as bootstrap
from data_security.adapters.persistence.models import ExportReport, PrivateObject
from data_security.adapters.persistence.private_store import DjangoPrivateStore
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.application.reports import ReportAuthenticator
from data_security.contracts import (
    ActionPlan, AuditReceipt, BASELINE_LIMITS, BoundedPayload, ContractViolation, Environment,
    ExecutionBinding, FrozenJSON, MaskReport, MediaType, ObjectContext, PayloadKind, ProtectionContext,
    ProtectionError, Purpose, ReasonCode, ReportProof, ReportRecord, Role, StoredObject, content_hash,
)
from data_security.tests.fixtures import AT, examples
from data_security.tests.phase3_fixtures import configuration


class ExportLifecyclePostgresTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.path, self.config, _, _, _ = self.enterContext(configuration(providers=()))
        checkpoints = self.path.parent / 'export-lifecycle-checkpoints'
        checkpoints.mkdir(mode=0o700)
        self.config.update(schema_version='ds.bootstrap.v2', policy_repository={'kind': 'file', 'writable': False},
            export_retention={'scope_ref': 'retention/phase7-export-fixture'},
            audit_chain={'chain_version': 'ds.audit.v2', 'project_ref': 'ctf',
                'object_uuid': '00000000-0000-4000-8000-000000000072', 'object_version': 'v1',
                'authorization_ref': 'authorization/export-lifecycle-fixture', 'retained_keys': [],
                'checkpoint_root': str(checkpoints), 'checkpoint_ref': None})
        self.path.write_text(json.dumps(self.config))
        self.components = bootstrap.assemble(config_path=self.path)
        self.now = AT
        self.lifecycle = self.components['export_lifecycle']
        self.lifecycle.clock = lambda: self.now
        self.components['audit'].sink.clock = lambda: self.now
        self.reports = DjangoReportRepository(environment=Environment.EVALUATION, lifecycle=self.lifecycle)
        root = self.path.parent / 'export-lifecycle-private'
        root.mkdir(mode=0o700)
        self.store = DjangoPrivateStore(root=root, crypto=self.components['crypto'], environment=Environment.EVALUATION)
        self.signer = ReportAuthenticator(crypto=self.components['crypto'], key=self.components['audit'].sink.key,
            executor_ref='service/resource-column-export', environment=Environment.EVALUATION,
            clock=lambda: self.now)
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', role=Role.SERVICE,
            environment=Environment.EVALUATION, domain='ctf', purpose=Purpose.STORAGE)

    def fence(self, repository=None):
        values, suffix = examples(), uuid4().hex
        binding = replace(values[ExecutionBinding], execution_id='lifecycle/' + suffix,
            idempotency_key='lifecycle/idempotency/' + suffix, environment='evaluation', domain_ref='ctf',
            policy_binding=self.components['binding'])
        source = replace(values[ActionPlan].source, source_environment='evaluation', source_domain='ctf',
            approval_basis_ref='approval/lifecycle-synthetic', approval_basis_version='v1')
        content = dict(values[ActionPlan].content(), source=source, policy_binding=binding.policy_binding)
        plan = ActionPlan(**content, plan_hash=content_hash(content), approval=None)
        context = replace(values[ObjectContext], environment=Environment.EVALUATION, object_uuid=str(uuid4()),
            object_version=binding.asset_version, authorization_ref=binding.authorization_id)
        self.assertIs((repository or self.reports).begin(plan, binding, context), True)
        return plan, binding, context

    def prepare(self, *, repository=None, delay=timedelta(seconds=1)):
        repository = repository or self.reports
        plan, binding, context = self.fence(repository)
        self.now += delay
        raw = b'contact\nredacted\n'
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
            media_type=MediaType.CSV, text=None, tree=None, binary=raw, limits=BASELINE_LIMITS)
        envelope = self.components['crypto'].seal(payload, context, self.components['data_ref'])
        candidate = self.store.write_candidate(envelope, context)
        self.assertIsInstance(candidate, StoredObject)
        stored = self.store.verify(candidate, context)
        self.assertIsInstance(stored, StoredObject)
        content = dict(examples()[MaskReport].content(), execution_id=binding.execution_id,
            executor_ref=self.signer.executor_ref, asset_version=binding.asset_version, source=plan.source,
            action_plan_hash=plan.plan_hash, policy_binding=binding.policy_binding,
            algorithm_versions=tuple(sorted({action.algorithm.algorithm.value + '/' + action.algorithm.version
                                             for action in plan.actions})),
            output_hash=hashlib.sha256(raw).hexdigest(), ciphertext_hash=stored.ciphertext_hash,
            created_at=self.now)
        report = MaskReport(**content, report_hash=content_hash(content))
        proof = self.signer.issue(report, binding, plan, context, input_hash=plan.input_hash,
                                 output_hash=report.output_hash, ciphertext_hash=stored.ciphertext_hash)
        self.assertIsInstance(proof, ReportProof)
        record = ReportRecord(schema_version=ReportRecord.SCHEMA, binding=binding, plan=plan,
                              context=context, stored=stored, report=report, proof=proof)
        self.assertEqual(repository.put(record), record)
        return ExportReport.objects.get(execution_id=binding.execution_id), record

    def test_only_new_fences_register_once_in_the_original_audit(self):
        row, record = self.prepare()
        receipt = AuditReceipt.from_wire(row.retention_registration)
        self.assertEqual(row.retention_scope, self.lifecycle.scope_ref)
        self.assertEqual(receipt.chain_version, 'ds.audit.v2')
        event = self.components['audit'].sink.read_authenticated(receipt.event_id)
        self.assertEqual(event.object_ref, record.binding.execution_id)
        self.assertEqual(event.correlation_ref, self.lifecycle.scope_ref)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.now += timedelta(seconds=1)
        self.assertIs(self.reports.begin(record.plan, record.binding, record.context), False)
        self.assertEqual(self.reports.put(record), record)
        row.refresh_from_db()
        self.assertEqual(row.retention_registration, receipt.to_wire())
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_deadline_uses_generation_not_registration_or_access_expiry(self):
        row, record = self.prepare(delay=timedelta(minutes=2))
        for at in (record.binding.expires_at, AT + timedelta(hours=24)):
            self.now = at
            result = self.lifecycle.preview(self.context)
            self.assertIsInstance(result, FrozenJSON)
            self.assertEqual(result.to_value()['exports'], [])
        self.now = record.report.created_at + timedelta(hours=24)
        result = self.lifecycle.preview(self.context)
        self.assertIsInstance(result, FrozenJSON)
        item, = result.to_value()['exports']
        self.assertEqual(item['created_at'], record.report.created_at.isoformat())
        self.assertEqual(item['expires_at'], self.now.isoformat())
        self.assertEqual(item['object_ref'], record.stored.object_ref)
        self.assertEqual(item['report_hash'], row.document_hash)

    def test_preexisting_owner_cannot_be_enrolled_by_replaying_begin_or_put(self):
        unbound = DjangoReportRepository(environment=Environment.EVALUATION)
        row, record = self.prepare(repository=unbound)
        self.assertIs(self.reports.begin(record.plan, record.binding, record.context), False)
        self.assertEqual(self.reports.put(record), record)
        self.now += timedelta(days=2)
        self.assertEqual(self.lifecycle.preview(self.context).to_value()['exports'], [])
        row.refresh_from_db()
        self.assertIsNone(row.retention_scope)
        self.assertIsNone(row.retention_registration)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)

    def test_registration_failure_rolls_back_the_original_owner_uow(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                  retryable=False, trace_id='lifecycle/registration')
        values = examples()
        binding = replace(values[ExecutionBinding], environment='evaluation', domain_ref='ctf')
        context = replace(values[ObjectContext], environment=Environment.EVALUATION,
                          object_version=binding.asset_version, authorization_ref=binding.authorization_id)
        with patch.object(self.lifecycle.audit, 'record', return_value=failure), DjangoUnitOfWork():
            result = self.reports.begin(values[ActionPlan], binding, context)
            self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertFalse(ExportReport.objects.exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.exists())

    def test_preview_rejects_a_registration_copied_from_another_owner(self):
        first, _ = self.prepare()
        second, _ = self.prepare()
        ExportReport.objects.filter(pk=first.pk).update(retention_registration=second.retention_registration)
        self.now += timedelta(days=2)
        self.assertEqual(self.lifecycle.preview(self.context).code, ReasonCode.AUDIT_UNAVAILABLE)

    def test_preview_rejects_resigned_document_hash_without_original_report_mac(self):
        row, record = self.prepare()
        content = dict(record.report.content(), created_at=record.report.created_at + timedelta(seconds=1))
        report = MaskReport(**content, report_hash=content_hash(content))
        document = replace(record, report=report).to_wire(include_payload=True)
        encoded = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                             allow_nan=False).encode('utf-8')
        ExportReport.objects.filter(pk=row.pk).update(document=document,
                                                     document_hash=hashlib.sha256(encoded).hexdigest())
        self.now += timedelta(days=2)
        self.assertIsInstance(self.lifecycle.preview(self.context), ProtectionError)

    def test_preview_is_metadata_only_and_does_not_retire_published_bytes(self):
        row, record = self.prepare()
        self.assertIsInstance(self.store.publish(record.stored, record.context), StoredObject)
        self.now += timedelta(days=2)
        files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.store.root.iterdir()}
        events = AuthenticatedAuditEntry.objects.count()
        with patch.object(self.components['crypto'], 'open', side_effect=AssertionError('unexpected plaintext read')):
            result = self.lifecycle.preview(self.context)
        self.assertIsInstance(result, FrozenJSON)
        self.assertNotIn('ciphertext_and_tag', json.dumps(result.to_value()))
        self.assertEqual(PrivateObject.objects.get(object_ref=record.stored.object_ref).state, 'published')
        self.assertEqual(files, {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in self.store.root.iterdir()})
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), events)
        row.refresh_from_db()
        self.assertEqual(row.state, 'prepared')

    def test_service_scope_and_bounded_inventory_are_enforced(self):
        for values in ({'actor_ref': 'user/unapproved'}, {'role': Role.ADMIN},
                       {'purpose': Purpose.DELIVERY}, {'environment': Environment.PRODUCTION}):
            self.assertEqual(self.lifecycle.preview(replace(self.context, **values)).code,
                             ReasonCode.AUTHORIZATION_DENIED)
        self.fence()
        self.assertEqual(self.lifecycle.preview(self.context).to_value()['exports'], [])
        self.fence()
        self.lifecycle.limits = replace(BASELINE_LIMITS, max_actions=1)
        self.assertEqual(self.lifecycle.preview(self.context).code, ReasonCode.LIMIT_EXCEEDED)

    def test_other_cohorts_and_unbound_configuration_are_not_adopted(self):
        row, record = self.prepare()
        self.config['export_retention'] = {'scope_ref': 'retention/another-synthetic-cohort'}
        self.path.write_text(json.dumps(self.config))
        other = bootstrap.assemble_export_retention(config_path=self.path)
        self.assertEqual(other.preview(self.context).to_value()['exports'], [])
        self.config.pop('export_retention')
        self.path.write_text(json.dumps(self.config))
        self.assertIsNone(bootstrap.assemble(config_path=self.path)['export_lifecycle'])
        with self.assertRaises(ContractViolation):
            bootstrap.assemble_export_retention(config_path=self.path)
        row.refresh_from_db()
        self.assertEqual(self.reports.read(record.binding), record)
        self.assertEqual(row.retention_scope, self.lifecycle.scope_ref)

    def test_configuration_does_not_accept_a_caller_selected_ttl_or_missing_audit(self):
        self.config['export_retention']['hours'] = 1
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            bootstrap.assemble_export_retention(config_path=self.path)
        self.config['export_retention'].pop('hours')
        self.config.pop('audit_chain')
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            bootstrap.assemble_export_retention(config_path=self.path)


class ExportLifecycleMigrationTests(TransactionTestCase):
    def test_additive_migration_preserves_legacy_rows_without_enrollment(self):
        self.assertEqual(connection.vendor, 'postgresql')
        old = [('security_policies', '0014_reveal_request_metadata')]
        new = [('security_policies', '0015_export_retention_registration')]
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(targets))
        executor.migrate(old)
        historical = executor.loader.project_state(old).apps.get_model('security_policies', 'ExportReport')
        values = {'execution_id': 'lifecycle/migration-old', 'idempotency_key': 'lifecycle/migration-old',
                  'binding_hash': '0' * 64, 'intent_hash': '1' * 64, 'state': 'preparing'}
        row = historical.objects.create(**values)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        current = executor.loader.project_state(new).apps.get_model('security_policies', 'ExportReport')
        restored = current.objects.get(pk=row.pk)
        self.assertIsNone(restored.retention_scope)
        self.assertIsNone(restored.retention_registration)
        for name, value in values.items():
            self.assertEqual(getattr(restored, name), value)
        MigrationExecutor(connection).migrate(old)
        self.assertEqual(historical.objects.get(pk=row.pk).binding_hash, values['binding_hash'])
        MigrationExecutor(connection).migrate(new)
        self.assertIsNone(current.objects.get(pk=row.pk).retention_scope)
