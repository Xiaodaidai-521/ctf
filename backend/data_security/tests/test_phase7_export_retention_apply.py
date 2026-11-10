"""Synthetic PG/file retention and staged recovery; not a full resource export or pg_restore."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from audit.models import AuditEvent, AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend import security_bootstrap as bootstrap
from data_security.adapters.persistence.models import ExportReport, PrivateObject
from data_security.adapters.persistence.recovery_state import RecoveryJournal, recovery_admission
from data_security.adapters.persistence.recovery_verifier import DjangoRecoveryVerifier
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.application.reports import ReportAuthenticator
from data_security.contracts import (
    ActionPlan, AuditReceipt, BASELINE_LIMITS, BoundedPayload, ContractViolation, DeliveryReceipt, Durability,
    Environment, EventKind, ExecutionBinding, FrozenJSON, KeyPurpose, KeyReference, KeyStatus, MaskReport,
    MediaType, ObjectContext, Outcome, PayloadKind, ProtectionContext, ProtectionError, Purpose, ReasonCode,
    ReportProof, ReportRecord, Role, SecurityEventV2, StoredObject, content_hash,
)
from data_security.tests.fixtures import AT, examples
from data_security.tests.phase3_fixtures import configuration


class ExportRetentionApplyTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.config_path, self.config, _, _, _ = self.enterContext(configuration(providers=()))
        roots = [self.config_path.parent / name for name in ('retention-checkpoints', 'retention-private', 'retention-facts')]
        for root in roots:
            root.mkdir(mode=0o700)
            root.chmod(0o700)
        checkpoints, private, facts = roots
        self.config.update(schema_version='ds.bootstrap.v2', policy_repository={'kind': 'file', 'writable': False},
            private_files={'private_root': str(private), 'project_ref': 'ctf'},
            export_retention={'scope_ref': 'retention/phase7-apply-fixture', 'journal_root': str(facts)},
            audit_chain={'chain_version': 'ds.audit.v2', 'project_ref': 'ctf',
                'object_uuid': '00000000-0000-4000-8000-000000000073', 'object_version': 'v1',
                'authorization_ref': 'authorization/export-retention-fixture', 'retained_keys': [],
                'checkpoint_root': str(checkpoints), 'checkpoint_ref': None})
        self.config_path.write_text(json.dumps(self.config))
        self.components = bootstrap.assemble(config_path=self.config_path)
        self.lifecycle = self.components['export_lifecycle']
        self.store, self.journal, self.sink = self.lifecycle.store, self.lifecycle.journal, self.components['audit'].sink
        self.now = AT
        self.lifecycle.clock = self.sink.clock = lambda: self.now
        self.reports = DjangoReportRepository(environment=Environment.EVALUATION, lifecycle=self.lifecycle)
        self.signer = ReportAuthenticator(crypto=self.components['crypto'], key=self.sink.key,
            executor_ref='service/resource-column-export', environment=Environment.EVALUATION, clock=lambda: self.now)
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', role=Role.SERVICE,
            environment=Environment.EVALUATION, domain='ctf', purpose=Purpose.STORAGE)

    def prepare(self, *, repository=None, field='resources/export', delivered=True):
        repository = repository or self.reports
        values, suffix = examples(), uuid4().hex
        binding = replace(values[ExecutionBinding], execution_id='retention/' + suffix,
            idempotency_key='retention/idempotency/' + suffix, environment='evaluation', domain_ref='ctf',
            policy_binding=self.components['binding'])
        source = replace(values[ActionPlan].source, source_environment='evaluation', source_domain='ctf',
            approval_basis_ref='approval/retention-synthetic', approval_basis_version='v1')
        content = dict(values[ActionPlan].content(), source=source, policy_binding=binding.policy_binding)
        plan = ActionPlan(**content, plan_hash=content_hash(content), approval=None)
        context = replace(values[ObjectContext], environment=Environment.EVALUATION, project_ref='ctf',
            object_uuid=str(uuid4()), object_version=binding.asset_version, field_ref=field,
            authorization_ref=binding.authorization_id)
        with transaction.atomic():
            self.assertIs(repository.begin(plan, binding, context), True)
        self.now += timedelta(seconds=1)
        raw = b'contact\nredacted\n'
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
            media_type=MediaType.CSV, text=None, tree=None, binary=raw, limits=BASELINE_LIMITS)
        envelope = self.components['crypto'].seal(payload, context, self.components['data_ref'])
        candidate = self.store.write_candidate(envelope, context)
        self.assertIsInstance(candidate, StoredObject)
        stored = self.store.verify(candidate, context)
        self.assertIsInstance(stored, StoredObject)
        content = dict(values[MaskReport].content(), execution_id=binding.execution_id,
            executor_ref=self.signer.executor_ref, asset_version=binding.asset_version, source=plan.source,
            action_plan_hash=plan.plan_hash, policy_binding=binding.policy_binding,
            algorithm_versions=tuple(sorted({action.algorithm.algorithm.value + '/' + action.algorithm.version
                                             for action in plan.actions})),
            output_hash=hashlib.sha256(raw).hexdigest(), ciphertext_hash=stored.ciphertext_hash, created_at=self.now)
        report = MaskReport(**content, report_hash=content_hash(content))
        proof = self.signer.issue(report, binding, plan, context, input_hash=plan.input_hash,
                                 output_hash=report.output_hash, ciphertext_hash=stored.ciphertext_hash)
        self.assertIsInstance(proof, ReportProof)
        record = ReportRecord(schema_version=ReportRecord.SCHEMA, binding=binding, plan=plan,
                              context=context, stored=stored, report=report, proof=proof)
        self.assertEqual(repository.put(record), record)
        if delivered:
            event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                event_id=content_hash({'domain': 'ds.logical-delivery.v1', 'binding': binding}), kind=EventKind.DELIVERY,
                actor_ref=binding.subject_ref, object_ref=stored.object_ref, object_version=stored.version,
                outcome=Outcome.SUCCEEDED, occurred_at=self.now, counts=(('records', 1),),
                policy_binding=binding.policy_binding, algorithm_versions=report.algorithm_versions,
                key_versions=(proof.key.key_ref,), correlation_ref=binding.execution_id, reason=None,
                evidence_hashes=(('ciphertext', stored.ciphertext_hash), ('report', content_hash(report))))
            with transaction.atomic():
                self.assertIsInstance(self.store.publish(stored, context), StoredObject)
                audit = self.components['audit'].record(event, Durability.LEDGER_CONFIRMED)
                self.assertIsInstance(audit, AuditReceipt)
                receipt = DeliveryReceipt(schema_version=DeliveryReceipt.SCHEMA, binding=binding,
                    outcome=Outcome.SUCCEEDED, delivered_records=1, evidence_ref='retention/synthetic-delivery', audit=audit)
                self.assertEqual(repository.record_delivery(receipt), receipt)
        return ExportReport.objects.get(execution_id=binding.execution_id), record

    def expire(self, record):
        self.now = record.report.created_at + timedelta(hours=24)
        approved = self.lifecycle.preview(self.context)
        self.assertIsInstance(approved, FrozenJSON)
        return approved

    def initialize(self):
        self.assertIsInstance(self.lifecycle.initialize(self.context), FrozenJSON)

    def file(self, record):
        return self.store.root / (record.stored.object_ref.removeprefix('private/') + '.sealed')

    def recovery(self):
        journal = RecoveryJournal(root=self.store.root, target_identity=content_hash({'fixture': 'export-retention'}),
            code_version='export-retention-fixture-v1', environment=Environment.EVALUATION, domain='ctf',
            service_identity='service/security', clock=lambda: self.now, limits=BASELINE_LIMITS)
        journal.start(self.context)
        return journal

    def stage_restored(self, journal):
        state = journal.read(self.context)
        state['state'] = 'restored'
        journal.save(state, self.context)

    def rewind(self, sequence):
        rows = list(AuthenticatedAuditEntry.objects.filter(chain_identity=self.sink.chain_identity,
            sequence__gt=sequence).values_list('pk', 'record_id', 'record__audit_event_id'))
        AuthenticatedAuditEntry.objects.filter(pk__in=[row[0] for row in rows]).delete()
        SecurityAuditRecord.objects.filter(pk__in=[row[1] for row in rows]).delete()
        AuditEvent.objects.filter(pk__in=[row[2] for row in rows]).delete()

    def verifier(self, *, lifecycle=True):
        configured = connection.settings_dict
        return DjangoRecoveryVerifier(store=self.store, owners={}, audit=self.sink, reports=self.reports,
            verify_report=self.lifecycle.verify_report, field_storage=None, field_models=(), inspect_share=Mock(),
            limits=BASELINE_LIMITS, clock=lambda: self.now,
            database={'dbname': configured['NAME'], 'host': configured['HOST'], 'port': configured['PORT'] or 5432},
            export_lifecycle=self.lifecycle if lifecycle else None)

    def test_published_apply_removes_bytes_and_preserves_original_delivery_evidence(self):
        row, record = self.prepare()
        original_document, original_delivery = row.document, row.delivery_receipt
        self.initialize()
        approved = self.expire(record)
        with patch.object(self.components['crypto'], 'open', side_effect=AssertionError('retention must not decrypt')):
            receipts = self.lifecycle.apply(approved, self.context)
        self.assertIsInstance(receipts, tuple)
        self.assertEqual(len(receipts), 1)
        row.refresh_from_db()
        self.assertEqual((row.state, PrivateObject.objects.get(object_ref=record.stored.object_ref).state), ('retired', 'retired'))
        self.assertFalse(self.file(record).exists())
        self.assertEqual((row.document, row.delivery_receipt), (original_document, original_delivery))
        self.assertEqual(self.journal.read()['facts'], [row.retention_retirement])
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
        self.assertEqual(self.reports.read(record.binding), record)
        self.assertIsInstance(self.reports.delivery(record.binding), ProtectionError)
        self.assertIsInstance(self.store.read(record.stored, record.context), ProtectionError)
        with transaction.atomic():
            self.assertIsInstance(self.reports.begin(record.plan, record.binding, record.context), ProtectionError)
        self.assertIsInstance(self.reports.put(record), ProtectionError)
        self.assertEqual(self.lifecycle.preview(self.context).to_value()['exports'], [])
        self.assertEqual(self.lifecycle.apply(self.lifecycle.preview(self.context), self.context), ())

    def test_external_persistence_failure_fences_without_deleting_and_resumes_same_intent(self):
        row, record = self.prepare()
        self.initialize()
        approved = self.expire(record)
        with patch.object(self.journal, 'save', side_effect=OSError('synthetic persistence failure')):
            self.assertIsInstance(self.lifecycle.apply(approved, self.context), ProtectionError)
        row.refresh_from_db()
        intent = row.retention_retirement
        self.assertEqual(row.state, 'retiring')
        self.assertEqual(PrivateObject.objects.get(object_ref=record.stored.object_ref).state, 'published')
        self.assertTrue(self.file(record).exists())
        self.assertEqual(self.journal.read()['facts'], [])
        self.assertIsInstance(self.reports.delivery(record.binding), ProtectionError)
        self.assertEqual(self.lifecycle.preview(self.context), approved)
        self.assertIsInstance(self.lifecycle.apply(approved, self.context), tuple)
        row.refresh_from_db()
        self.assertEqual(row.retention_retirement, intent)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
        self.assertFalse(self.file(record).exists())

    def test_unlink_failure_keeps_durable_intent_and_retries_without_republication(self):
        row, record = self.prepare()
        self.initialize()
        approved = self.expire(record)
        with patch.object(Path, 'unlink', side_effect=OSError('synthetic unlink failure')):
            self.assertIsInstance(self.lifecycle.apply(approved, self.context), ProtectionError)
        row.refresh_from_db()
        self.assertEqual(row.state, 'retiring')
        self.assertEqual(PrivateObject.objects.get(object_ref=record.stored.object_ref).state, 'retired')
        self.assertEqual(self.journal.read()['facts'], [row.retention_retirement])
        self.assertTrue(self.file(record).exists())
        self.assertIsInstance(self.lifecycle.apply(approved, self.context), tuple)
        self.assertFalse(self.file(record).exists())
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)

    def test_stale_approval_and_wrong_actor_leave_owner_file_and_journal_unchanged(self):
        row, record = self.prepare()
        self.initialize()
        approved = self.expire(record)
        original = (self.journal.root / self.journal.FILE).read_bytes()
        changed = approved.to_value()
        changed['exports'][0]['size_bytes'] += 1
        self.assertEqual(self.lifecycle.apply(FrozenJSON(changed), self.context).code, ReasonCode.REPORT_MISMATCH)
        wrong = replace(self.context, actor_ref='actor/not-security', role=Role.ADMIN)
        self.assertEqual(self.lifecycle.apply(approved, wrong).code, ReasonCode.AUTHORIZATION_DENIED)
        row.refresh_from_db()
        self.assertEqual(row.state, 'prepared')
        self.assertIsNone(row.retention_retirement)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual((self.journal.root / self.journal.FILE).read_bytes(), original)
        self.assertTrue(self.file(record).exists())

    def test_missing_or_modified_journal_never_becomes_an_empty_deletion_list(self):
        row, record = self.prepare()
        approved = self.expire(record)
        self.assertIsInstance(self.lifecycle.apply(approved, self.context), ProtectionError)
        self.initialize()
        target = self.journal.root / self.journal.FILE
        original = target.read_bytes()
        self.assertIsInstance(self.lifecycle.initialize(self.context), ProtectionError)
        changed = json.loads(original)
        changed['scope_ref'] = 'retention/other-fixture'
        target.write_text(json.dumps(changed))
        self.assertIsInstance(self.lifecycle.apply(approved, self.context), ProtectionError)
        target.write_bytes(original)
        target.unlink()
        self.assertIsInstance(self.lifecycle.apply(approved, self.context), ProtectionError)
        row.refresh_from_db()
        self.assertEqual(row.state, 'prepared')
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertTrue(self.file(record).exists())

    def test_direct_shared_output_reference_is_not_deleted_and_legacy_input_is_not_adopted(self):
        legacy, original = self.prepare(repository=DjangoReportRepository(environment=Environment.EVALUATION),
                                        field='resources/file', delivered=False)
        row, record = self.prepare()
        self.initialize()
        approved = self.expire(record)
        self.assertEqual([item['execution_id'] for item in approved.to_value()['exports']], [row.execution_id])
        other = ExportReport.objects.create(execution_id='retention/shared-owner', idempotency_key='retention/shared-key',
            binding_hash='1' * 64, private_object_id=record.stored.object_ref, state='prepared')
        self.assertEqual(self.lifecycle.apply(approved, self.context).code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertTrue(self.file(record).exists())
        other.delete()
        self.assertIsInstance(self.lifecycle.apply(approved, self.context), tuple)
        legacy.refresh_from_db()
        self.assertIsNone(legacy.retention_scope)
        self.assertEqual(legacy.state, 'prepared')
        self.assertTrue(self.file(original).exists())
        self.assertEqual(PrivateObject.objects.get(object_ref=original.stored.object_ref).state, 'verified')

    def test_an_enrolled_non_export_context_cannot_use_the_retention_delete_capability(self):
        row, record = self.prepare(field='resources/file')
        self.initialize()
        approved = self.expire(record)
        self.assertEqual(self.lifecycle.apply(approved, self.context).code, ReasonCode.SOURCE_NOT_APPROVED)
        row.refresh_from_db()
        self.assertIsNone(row.retention_retirement)
        self.assertTrue(self.file(record).exists())

    def test_changed_ciphertext_is_not_unlinked_or_reported_as_retired(self):
        row, record = self.prepare()
        self.initialize()
        approved = self.expire(record)
        target = self.file(record)
        raw = target.read_bytes()
        target.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        self.assertEqual(self.lifecycle.apply(approved, self.context).code, ReasonCode.HASH_MISMATCH)
        row.refresh_from_db()
        self.assertEqual(row.state, 'retiring')
        self.assertEqual(PrivateObject.objects.get(object_ref=record.stored.object_ref).state, 'published')
        self.assertTrue(target.exists())

    def test_apply_bounds_and_outer_transaction_fail_before_intent(self):
        row, record = self.prepare()
        self.initialize()
        approved = self.expire(record)
        with transaction.atomic():
            self.assertEqual(self.lifecycle.apply(approved, self.context).code, ReasonCode.SOURCE_NOT_APPROVED)
        self.now = AT + timedelta(seconds=5)
        self.prepare()
        self.now = AT + timedelta(days=2)
        self.lifecycle.limits = replace(BASELINE_LIMITS, max_actions=1)
        self.assertEqual(self.lifecycle.apply(approved, self.context).code, ReasonCode.LIMIT_EXCEEDED)
        self.assertFalse(ExportReport.objects.filter(retention_retirement__isnull=False).exists())
        self.assertTrue(self.file(record).exists())

    def test_replay_restores_original_audit_ids_and_latest_delivery_then_removes_restored_bytes(self):
        recovery = self.recovery()
        row, record = self.prepare()
        original = self.file(record).read_bytes()
        original_delivery = row.delivery_receipt
        registration = AuditReceipt.from_wire(row.retention_registration)
        self.initialize()
        self.assertIsInstance(self.lifecycle.apply(self.expire(record), self.context), tuple)
        row.refresh_from_db()
        intent = AuditReceipt.from_wire(row.retention_retirement['intent'])
        self.rewind(registration.sequence)
        ExportReport.objects.filter(pk=row.pk).update(state='prepared', retention_retirement=None, delivery_receipt=None)
        PrivateObject.objects.filter(object_ref=record.stored.object_ref).update(state='verified')
        self.file(record).write_bytes(original)
        self.file(record).chmod(0o600)
        self.stage_restored(recovery)
        result = self.lifecycle.replay(self.context, recovery_journal=recovery)
        self.assertIsInstance(result, AuditReceipt)
        self.assertEqual(result.event_id, intent.event_id)
        self.assertEqual(self.sink._receipt_v2(AuthenticatedAuditEntry.objects.select_related('record').get(
            pk=int(intent.entry_ref.rsplit('/', 1)[1]))), intent)
        row.refresh_from_db()
        self.assertEqual((row.state, row.delivery_receipt), ('retired', original_delivery))
        self.assertFalse(self.file(record).exists())
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
        self.assertEqual(self.lifecycle.replay(self.context, recovery_journal=recovery), result)
        self.assertIsInstance(recovery_admission(recovery.root, recovery.target_identity, limits=BASELINE_LIMITS), ProtectionError)
        self.assertEqual(recovery.read(self.context)['state'], 'restored')

    def test_replay_does_not_open_other_recovery_stages(self):
        recovery = self.recovery()
        row, record = self.prepare()
        self.initialize()
        self.assertIsInstance(self.lifecycle.apply(self.expire(record), self.context), tuple)
        for stage in ('closed', 'restoring', 'verified', 'opened'):
            with self.subTest(stage=stage):
                state = recovery.read(self.context)
                state['state'] = stage
                recovery.save(state, self.context)
                self.assertEqual(self.lifecycle.replay(self.context, recovery_journal=recovery).code,
                                 ReasonCode.SOURCE_NOT_APPROVED)
                self.assertEqual(recovery.read(self.context)['state'], stage)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)

    def test_original_read_only_owner_verifier_accepts_retired_bytes_and_keeps_delivery_proof(self):
        row, record = self.prepare()
        self.initialize()
        self.assertIsInstance(self.lifecycle.apply(self.expire(record), self.context), tuple)
        self.sink.checkpoint_ref = self.journal.read()['audit']['checkpoint_ref']
        with patch.object(self.components['crypto'], 'open', side_effect=AssertionError('no retired plaintext')):
            result = self.verifier()(self.context)
        self.assertIsInstance(result, dict)
        self.assertTrue(result['complete'])
        self.assertEqual((result['reports_authenticated'], result['logical_delivery_receipts'], result['retired_objects']),
                         (1, 1, 1))
        self.assertEqual(result['private_objects_opened'], 0)
        self.assertEqual(result['pending_records'], 0)

    def test_owner_verifier_rejects_missing_fact_changed_bytes_and_capability_downgrade(self):
        row, record = self.prepare()
        original = self.file(record).read_bytes()
        self.initialize()
        self.assertIsInstance(self.lifecycle.apply(self.expire(record), self.context), tuple)
        row.refresh_from_db()
        fact = row.retention_retirement
        self.sink.checkpoint_ref = self.journal.read()['audit']['checkpoint_ref']
        ExportReport.objects.filter(pk=row.pk).update(retention_retirement=None)
        self.assertIsInstance(self.verifier()(self.context), ProtectionError)
        ExportReport.objects.filter(pk=row.pk).update(retention_retirement=fact)
        self.file(record).write_bytes(original)
        self.file(record).chmod(0o600)
        self.assertIsInstance(self.verifier()(self.context), ProtectionError)
        self.file(record).unlink()
        self.assertIsInstance(self.verifier(lifecycle=False)(self.context), ProtectionError)
        ExportReport.objects.filter(pk=row.pk).update(retention_scope=None)
        self.assertIsInstance(self.verifier(lifecycle=False)(self.context), ProtectionError)

    def test_verified_prefix_allows_newer_authentic_target_but_restore_still_refuses_it(self):
        recovery = self.recovery()
        row, record = self.prepare()
        self.initialize()
        mirror = FrozenJSON(self.journal.read()['audit'])
        self.now += timedelta(seconds=1)
        event = replace(examples()[SecurityEventV2], event_id='retention/later-authentic-event', occurred_at=self.now,
            policy_binding=self.components['binding'])
        later = self.components['audit'].record(event, Durability.LEDGER_CONFIRMED)
        self.assertIsInstance(later, AuditReceipt)
        selected = self.sink.checkpoint('ds.audit.v2')
        self.assertIsInstance(selected, AuditReceipt)
        self.sink.checkpoint_ref = selected.checkpoint_ref
        result = self.sink.verify_recovery(mirror, BASELINE_LIMITS)
        self.assertEqual(result, replace(later, checkpoint_ref=mirror.to_value()['checkpoint_ref']))
        self.stage_restored(recovery)
        self.assertIsInstance(self.sink.restore_recovery(mirror, BASELINE_LIMITS, self.context, journal=recovery), ProtectionError)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
        changed = mirror.to_value()
        changed['entries'][0]['entry_id'] += 100
        self.assertIsInstance(self.sink.verify_recovery(FrozenJSON(changed), BASELINE_LIMITS), ProtectionError)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)

    def test_verified_prefix_never_appends_a_missing_suffix(self):
        row, record = self.prepare()
        self.initialize()
        mirror = FrozenJSON(self.journal.read()['audit'])
        self.rewind(AuditReceipt.from_wire(row.retention_registration).sequence)
        self.assertIsInstance(self.sink.verify_recovery(mirror, BASELINE_LIMITS), ProtectionError)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_bootstrap_keeps_journal_outside_restore_and_public_roots_and_requires_explicit_binding(self):
        for root in (self.store.root, self.sink.checkpoint_root, self.store.root.parent):
            with self.subTest(root=root.name):
                self.config['export_retention']['journal_root'] = str(root)
                self.config_path.write_text(json.dumps(self.config))
                with self.assertRaises(ContractViolation):
                    bootstrap.assemble_export_retention(config_path=self.config_path)
        self.config['export_retention'].pop('journal_root')
        self.config_path.write_text(json.dumps(self.config))
        owner = bootstrap.assemble_export_retention(config_path=self.config_path)
        self.assertIsNone(owner.journal)
        self.assertEqual(owner.apply(FrozenJSON({'scope_ref': owner.scope_ref, 'exports': []}), self.context).code,
                         ReasonCode.SOURCE_NOT_APPROVED)

    def test_offline_recovery_factory_binds_the_real_lifecycle_callback_without_early_assembly(self):
        identity = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='backup-identity/v1',
            purpose=KeyPurpose.BACKUP_PRIVATE, version='v1', status=KeyStatus.READ_ONLY)
        backup = Mock(full_inventory=True, private_root=self.store.root,
                      source_identity=content_hash({'fixture': 'retention-bootstrap'}), code_version='retention-fixture-v1')
        with patch.object(bootstrap, '_configuration', return_value=(self.config, object())), \
             patch.object(bootstrap, '_backup_adapter', return_value=backup), \
             patch.object(bootstrap, 'assemble', side_effect=AssertionError('assembly before restore')):
            flow = bootstrap.assemble_recovery(config_path=self.config_path, identity=identity)
        self.assertIsNotNone(flow.replay_governance)
        self.assertEqual(list(self.store.root.iterdir()), [])
        with patch.object(bootstrap, 'assemble', return_value={'backup': backup, 'export_lifecycle': self.lifecycle}), \
             patch.object(self.lifecycle, 'replay', return_value='callback-fixture-result') as replay:
            self.assertEqual(flow.replay_governance(self.context), 'callback-fixture-result')
        replay.assert_called_once_with(self.context, recovery_journal=flow.journal)

    def test_directory_sync_failure_keeps_a_retiring_owner_after_unlink(self):
        row, record = self.prepare()
        self.initialize()
        approved = self.expire(record)
        retire = self.lifecycle._retire

        def fail_directory_sync(fact, retained):
            with patch('data_security.adapters.persistence.export_lifecycle.os.fsync',
                       side_effect=OSError('synthetic directory sync failure')):
                return retire(fact, retained)

        with patch.object(self.lifecycle, '_retire', side_effect=fail_directory_sync):
            self.assertIsInstance(self.lifecycle.apply(approved, self.context), ProtectionError)
        row.refresh_from_db()
        self.assertEqual(row.state, 'retiring')
        self.assertEqual(PrivateObject.objects.get(object_ref=record.stored.object_ref).state, 'retired')
        self.assertFalse(self.file(record).exists())
        self.assertEqual(self.journal.read()['facts'], [row.retention_retirement])
        self.assertIsInstance(self.lifecycle.apply(approved, self.context), tuple)
        row.refresh_from_db()
        self.assertEqual(row.state, 'retired')
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)

    def test_external_journal_mac_tampering_refuses_without_creating_an_intent(self):
        row, record = self.prepare()
        self.initialize()
        approved = self.expire(record)
        target = self.journal.root / self.journal.FILE
        changed = json.loads(target.read_bytes())
        changed['authentication'] = '00' * 32
        target.write_text(json.dumps(changed))
        self.assertEqual(self.lifecycle.apply(approved, self.context).code, ReasonCode.AUDIT_UNAVAILABLE)
        row.refresh_from_db()
        self.assertEqual(row.state, 'prepared')
        self.assertIsNone(row.retention_retirement)
        self.assertTrue(self.file(record).exists())
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_missing_restored_owner_is_allowed_only_when_both_registration_and_bytes_are_absent(self):
        recovery = self.recovery()
        row, record = self.prepare()
        raw = self.file(record).read_bytes()
        self.initialize()
        self.assertIsInstance(self.lifecycle.apply(self.expire(record), self.context), tuple)
        self.stage_restored(recovery)
        row.delete()
        self.assertEqual(self.lifecycle.replay(self.context, recovery_journal=recovery).code,
                         ReasonCode.SOURCE_NOT_APPROVED)
        PrivateObject.objects.filter(object_ref=record.stored.object_ref).delete()
        self.file(record).write_bytes(raw)
        self.file(record).chmod(0o600)
        self.assertEqual(self.lifecycle.replay(self.context, recovery_journal=recovery).code,
                         ReasonCode.SOURCE_NOT_APPROVED)
        self.file(record).unlink()
        self.assertIsInstance(self.lifecycle.replay(self.context, recovery_journal=recovery), AuditReceipt)
        self.sink.checkpoint_ref = self.journal.read()['audit']['checkpoint_ref']
        result = self.verifier()(self.context)
        self.assertIsInstance(result, dict)
        self.assertTrue(result['complete'])
        self.assertEqual(result['reports_authenticated'], 0)
        self.assertEqual(recovery.read(self.context)['state'], 'restored')


class ExportRetentionIntentMigrationTests(TransactionTestCase):
    def test_additive_intent_migration_round_trip_preserves_the_enrollment(self):
        self.assertEqual(connection.vendor, 'postgresql')
        old = [('security_policies', '0015_export_retention_registration')]
        new = [('security_policies', '0016_export_retention_intent')]
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(targets))
        executor.migrate(old)
        model = executor.loader.project_state(old).apps.get_model('security_policies', 'ExportReport')
        original = {'execution_id': 'retention/migration-fixture', 'idempotency_key': 'retention/migration-key',
                    'binding_hash': '1' * 64, 'state': 'preparing', 'retention_scope': 'retention/existing-cohort',
                    'retention_registration': {'fixture': 'unchanged'}}
        row = model.objects.create(**original)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        added = executor.loader.project_state(new).apps.get_model('security_policies', 'ExportReport').objects.get(pk=row.pk)
        self.assertIsNone(added.retention_retirement)
        for name, value in original.items():
            self.assertEqual(getattr(added, name), value)
        MigrationExecutor(connection).migrate(old)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        final = executor.loader.project_state(new).apps.get_model('security_policies', 'ExportReport').objects.get(pk=row.pk)
        self.assertIsNone(final.retention_retirement)
        for name, value in original.items():
            self.assertEqual(getattr(final, name), value)
