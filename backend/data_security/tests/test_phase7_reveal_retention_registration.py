"""New-only reveal enrollment on the original synthetic PG and authenticated audit."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from challenges.models import Category, Challenge
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence import fields as field_module
from data_security.adapters.persistence.models import RevealFieldRetention, RevealRequest
from data_security.contracts import (
    BASELINE_LIMITS, AuditReceipt, BoundedPayload, CipherEnvelope, ContractViolation, Durability,
    Environment, MediaType, Outcome, Outlet, PayloadKind, PolicySnapshot,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, RevealField, RevealRequestRecord,
    Role, SecurityEventV2, canonical_bytes, content_hash,
)
from data_security.tests.phase4_fixtures import field_configuration
from learning_paths.models import LearningPath
from legal.models import LegalAnalysisTask
from legal.services.report_generator import ReportGenerator
from users.models import CTFUser, CourseDataGrant


EXISTING = 'cohort-existing@example.invalid'
MARKER = 'cohort-new@example.invalid'
SCOPE = 'retention/phase7-reveal-synthetic'


class RevealRetentionRegistrationTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
        self.path, self.config, _, binding = self.enterContext(field_configuration(dual_index=True))
        policy_path = Path(self.config['policy_file'])
        policy = PolicySnapshot.from_json(policy_path.read_bytes())
        rules = policy.rules + tuple(replace(rule, role=role, purpose=Purpose.INVESTIGATION)
            for rule in policy.rules if rule.outlet is Outlet.API for role in (Role.STUDENT, Role.TEACHER))
        values = dict(policy.content(), version='phase7-enrollment-synthetic.v1', rules=rules)
        digest = content_hash(values)
        policy = PolicySnapshot(**values, status=policy.status, content_hash=digest,
            approval=replace(policy.approval, approval_ref='approval/phase7-enrollment-synthetic', content_hash=digest))
        policy_path.write_text(json.dumps(policy.to_wire()))
        self.config['policy_binding'] = replace(binding, protection_version=policy.version,
                                                protection_hash=digest).to_wire()
        checkpoints = self.path.parent / 'enrollment-checkpoints'
        checkpoints.mkdir(mode=0o700)
        checkpoints.chmod(0o700)
        self.config['audit_chain'] = {
            'chain_version': 'ds.audit.v2', 'project_ref': 'phase7/enrollment-synthetic',
            'object_uuid': '00000000-0000-4000-8000-000000000037', 'object_version': 'v1',
            'authorization_ref': 'authorization/phase7-enrollment-synthetic', 'retained_keys': [],
            'checkpoint_root': str(checkpoints), 'checkpoint_ref': None,
        }
        self.config['reveal_requests'] = {'enabled': True}
        self.path.write_text(json.dumps(self.config))
        self.components = assemble(config_path=self.path)
        self.enterContext(patch.object(field_module, '_adapter', self.components['fields']))
        self.requester = CTFUser.objects.create_user(username='enrollment-owner', email=EXISTING, role='student')
        self.reviewer = CTFUser.objects.create_user(username='enrollment-reviewer', role='teacher', is_staff=True)
        self.course = LearningPath.objects.create(title='合成登记课程', slug='enrollment-synthetic',
                                                   description='隔离合成课程', difficulty='AP')
        CourseDataGrant.objects.create(actor=self.reviewer, student=self.requester, course=self.course,
            granted_by=self.reviewer, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        self.assertFalse(RevealFieldRetention.objects.exists())

    def enable(self):
        self.config['reveal_retention'] = {'scope_ref': SCOPE}
        self.path.write_text(json.dumps(self.config))
        self.components = assemble(config_path=self.path)
        self.retention = self.components['reveal_retention']
        self.enterContext(patch.object(field_module, '_adapter', self.components['fields']))
        self.assertIs(self.components['fields'].register_retention.__self__, self.retention)
        self.assertIs(self.components['reveal_requests']().repository.retention, self.retention)

    def context(self, actor):
        return ProtectionContext(schema_version=ProtectionContext.SCHEMA,
            actor_ref='user/' + str(actor.pk), role=Role(actor.role),
            authorization_ref='authorization/reveal-request-' + uuid4().hex,
            scope_refs=('users.ctfuser/email',), environment=Environment.EVALUATION, domain='ctf',
            outlet=Outlet.API, purpose=Purpose.INVESTIGATION, object_ref=str(self.requester.security_uuid),
            object_version='v' + str(self.requester.security_revision), source_ref=None,
            source_version=None, source_hash=None, trace_id='trace/' + uuid4().hex)

    def record(self):
        context = self.context(self.requester)
        return RevealRequestRecord(schema_version=RevealRequestRecord.SCHEMA,
            request_ref='request/' + uuid4().hex, subject_ref=context.actor_ref, course_id=self.course.pk,
            object_ref=context.object_ref, object_version=context.object_version,
            fields=((RevealField.EMAIL, 'users.ctfuser/email'),), purpose_ref='purpose/investigation',
            reason=BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
                media_type=MediaType.TEXT, text='核对合成资料 ' + MARKER, tree=None, binary=None, limits=BASELINE_LIMITS),
            requested_at=self.components['clock'](), state='pending', grant=None,
            decided_by=None, decided_at=None, decision_event_ref=None)

    def assert_field_registration(self, owner, name):
        entry = owner.security_envelopes[name]
        row = RevealFieldRetention.objects.get(object_ref=str(owner.security_uuid),
            field_ref=owner._meta.label_lower + '/' + name,
            context_document__object_version='v' + str(entry['revision']))
        context = self.components['fields'].context(owner, name, entry['revision'])
        self.assertEqual(row.context_document, context.to_wire())
        self.assertEqual(row.scope_ref, SCOPE)
        envelope = CipherEnvelope.from_wire(entry['envelope'])
        digest = hashlib.sha256(canonical_bytes(envelope, include_payload=True)).hexdigest()
        self.assertEqual(row.ciphertext_hash, digest)
        identity = {'domain': 'ds.reveal-retention.v1', 'scope': SCOPE,
                    'context': context, 'generated_at': row.generated_at, 'ciphertext_hash': digest}
        receipt = AuditReceipt.from_wire(row.registration)
        self.assertEqual(receipt.durability, Durability.LEDGER_CONFIRMED)
        self.assertEqual(receipt.chain_version, 'ds.audit.v2')
        event = self.components['audit'].sink.read_authenticated(receipt.event_id)
        self.assertIsInstance(event, SecurityEventV2)
        self.assertEqual(event.event_id, content_hash(identity))
        self.assertEqual(event.evidence_hashes, (('report', content_hash(identity)),))
        self.assertEqual(event.algorithm_versions, ('ds.reveal-retention.v1', 'register-field'))
        self.assertEqual(event.key_versions, (envelope.key.key_ref,))
        self.assertEqual(event.object_ref, str(owner.security_uuid))
        self.assertEqual(event.object_version, context.object_version)
        self.assertEqual(event.occurred_at, row.generated_at)
        self.assertNotIn(MARKER, json.dumps(RevealFieldRetention.objects.filter(pk=row.pk).values().get(), default=str))
        self.assertNotIn(MARKER, json.dumps(event.to_wire()))
        return row

    def test_new_user_task_and_generated_report_have_separate_authenticated_generations(self):
        self.enable()
        started = self.components['clock']()
        owner = CTFUser.objects.create_user(username='enrollment-new', email=MARKER)
        task = LegalAnalysisTask.objects.create(title='合成分析', input_text='原文样本 ' + MARKER,
                                               created_by=self.reviewer)
        report = ReportGenerator().generate_analysis_report(task=task, findings=[], evidence_items=[], actor=self.reviewer)
        self.assertEqual(report.task_id, task.pk)
        self.assertIn(MARKER, task.read_protected('input_text'))
        self.assertIn(MARKER, report.read_protected('content'))
        self.assertTrue(owner.email_index)
        self.assertTrue(owner.email_index_previous)
        self.assertEqual(owner.email, '')
        self.assertEqual(task.input_text, '')
        self.assertEqual(report.content, '')
        self.assertEqual(RevealFieldRetention.objects.count(), 3)
        for item, name in ((owner, 'email'), (task, 'input_text'), (report, 'content')):
            with self.subTest(field=name):
                row = self.assert_field_registration(item, name)
                self.assertLessEqual(started, row.generated_at)
                self.assertLessEqual(row.generated_at, self.components['clock']())
        self.assertGreater(report.security_revision, report.security_envelopes['content']['revision'])

    def test_enabling_reading_and_unrelated_save_leave_old_fields_and_requests_unenrolled(self):
        pending = self.components['reveal_requests']().request(self.record(), self.context(self.requester))
        self.assertIsInstance(pending, RevealRequestRecord)
        before = CTFUser.objects.filter(pk=self.requester.pk).values('security_envelopes',
            'email_index', 'email_index_previous').get()
        self.enable()
        self.assertFalse(RevealFieldRetention.objects.exists())
        row = RevealRequest.objects.get(request_ref=pending.request_ref)
        self.assertIsNone(row.retention_scope)
        self.assertIsNone(row.retention_registration)
        approved = self.components['reveal_requests']().decide(pending.request_ref, self.context(self.reviewer), approved=True)
        self.assertIsInstance(approved, RevealRequestRecord)
        row.refresh_from_db()
        self.assertIsNone(row.retention_scope)
        self.assertIsNone(row.retention_registration)
        self.assertEqual(self.requester.read_protected('email'), EXISTING)
        self.requester.nickname = '更新合成显示名'
        self.requester.save(update_fields=['nickname'])
        self.assertEqual(CTFUser.objects.filter(pk=self.requester.pk).values('security_envelopes',
            'email_index', 'email_index_previous').get(), before)
        self.assertFalse(RevealFieldRetention.objects.exists())

    def test_replacing_old_original_registers_only_its_new_field_revision(self):
        old = dict(self.requester.security_envelopes['email'])
        self.enable()
        self.requester.email = MARKER
        self.requester.save(update_fields=['email'])
        self.assertEqual(RevealFieldRetention.objects.count(), 1)
        row = self.assert_field_registration(self.requester, 'email')
        self.assertNotEqual(self.requester.security_envelopes['email'], old)
        self.assertEqual(row.context_document['object_version'], 'v2')
        self.requester.nickname = '只改合成显示名'
        self.requester.save(update_fields=['nickname'])
        self.assertEqual(self.requester.security_revision, 3)
        self.assertEqual(self.assert_field_registration(self.requester, 'email').pk, row.pk)
        self.assertEqual(RevealFieldRetention.objects.count(), 1)

    def test_new_request_enrollment_survives_approval_and_consumption_without_adopting_old_original(self):
        self.enable()
        factory = self.components['reveal_requests']
        pending = factory().request(self.record(), self.context(self.requester))
        self.assertIsInstance(pending, RevealRequestRecord)
        row = RevealRequest.objects.get(request_ref=pending.request_ref)
        self.assertEqual(row.retention_scope, SCOPE)
        registration = row.retention_registration
        receipt = AuditReceipt.from_wire(registration)
        event = self.components['audit'].sink.read_authenticated(receipt.event_id)
        self.assertIsInstance(event, SecurityEventV2)
        identity = {'domain': 'ds.reveal-retention.v1', 'scope': SCOPE, 'request': pending.authorization_content()}
        self.assertEqual(event.event_id, content_hash(identity))
        self.assertEqual(event.evidence_hashes, (('report', content_hash(identity)),))
        self.assertEqual(event.algorithm_versions, ('ds.reveal-retention.v1', 'register-request'))
        self.assertNotIn(MARKER, row.reason)
        self.assertNotIn(MARKER, json.dumps(event.to_wire()))
        approved = factory().decide(pending.request_ref, self.context(self.reviewer), approved=True)
        self.assertIsInstance(approved, RevealRequestRecord)
        self.assertEqual(approved.grant.expires_at - approved.grant.issued_at, timedelta(seconds=900))
        result = factory().reveal_request(pending.request_ref, self.context(self.requester))
        self.assertIsInstance(result, BoundedPayload)
        self.assertEqual(result.tree.to_value(), {'users.ctfuser/email': EXISTING})
        row.refresh_from_db()
        self.assertEqual(row.state, 'consumed')
        self.assertIsNotNone(row.consumed_at)
        self.assertEqual(row.retention_registration, registration)
        self.assertEqual(row.retention_scope, SCOPE)
        self.assertFalse(RevealFieldRetention.objects.exists())
        success = SecurityAuditRecord.objects.get(event__kind='reveal', event__outcome='succeeded')
        self.assertEqual(SecurityEventV2.from_wire(success.event).algorithm_versions, ('ds.reveal.v2',))

    def test_bad_registration_receipt_rolls_back_ciphertext_indexes_and_authenticated_entry(self):
        self.enable()
        before = CTFUser.objects.filter(pk=self.requester.pk).values('security_envelopes', 'security_revision',
            'email', 'email_index', 'email_index_previous').get()
        record = self.components['audit'].record
        attempted = []

        def unconfirmed(event, durability):
            receipt = record(event, durability)
            if event.algorithm_versions == ('ds.reveal-retention.v1', 'register-field'):
                self.assertTrue(AuthenticatedAuditEntry.objects.filter(record__event_id=event.event_id).exists())
                attempted.append(event.event_id)
                return replace(receipt, event_id='f' * 64)
            return receipt

        with patch.object(self.components['audit'], 'record', side_effect=unconfirmed):
            self.requester.email = MARKER
            with self.assertRaises(ContractViolation) as error:
                self.requester.save(update_fields=['email'])
        self.assertEqual(error.exception.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(len(attempted), 1)
        self.assertFalse(RevealFieldRetention.objects.exists())
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id=attempted[0]).exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.filter(record__event_id=attempted[0]).exists())
        self.assertEqual(CTFUser.objects.filter(pk=self.requester.pk).values('security_envelopes', 'security_revision',
            'email', 'email_index', 'email_index_previous').get(), before)

    def test_request_audit_failure_rolls_back_the_new_row_and_its_registration(self):
        self.enable()
        requested = self.record()
        record = self.components['audit'].record
        attempted = []

        def unconfirmed(event, durability):
            receipt = record(event, durability)
            if event.algorithm_versions == ('ds.reveal-request.v1', 'request') and event.outcome is Outcome.SUCCEEDED:
                row = RevealRequest.objects.get(request_ref=requested.request_ref)
                self.assertEqual(row.retention_scope, SCOPE)
                registration = AuditReceipt.from_wire(row.retention_registration)
                self.assertIsInstance(self.components['audit'].sink.read_authenticated(registration.event_id), SecurityEventV2)
                attempted.extend((event.event_id, registration.event_id))
                return replace(receipt, event_id='f' * 64)
            return receipt

        with patch.object(self.components['audit'], 'record', side_effect=unconfirmed):
            result = self.components['reveal_requests']().request(requested, self.context(self.requester))
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(len(attempted), 2)
        self.assertFalse(RevealRequest.objects.filter(request_ref=requested.request_ref).exists())
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id__in=attempted).exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.filter(record__event_id__in=attempted).exists())
        failure = SecurityAuditRecord.objects.get(event__algorithm_versions=['ds.reveal-request.v1', 'request'],
                                                  event__outcome='failed')
        self.assertIsInstance(self.components['audit'].sink.read_authenticated(failure.event_id), SecurityEventV2)

    def test_legacy_migration_and_empty_clears_are_not_new_original_generations(self):
        with patch.object(field_module, '_adapter', None):
            legacy = CTFUser.objects.create_user(username='enrollment-legacy', email=EXISTING)
        self.enable()
        self.assertEqual(legacy.security_state, 'legacy-v0')
        # Synthetic maintenance write only; not a backup/maintenance-command verification.
        field_module.ProtectedModel.save(legacy, _legacy_migration=True)
        self.assertEqual(legacy.security_state, 'sealed-v1')
        self.assertEqual(legacy.read_protected('email'), EXISTING)
        self.requester.email = ''
        self.requester.save(update_fields=['email'])
        self.assertEqual(self.requester.read_protected('email'), '')
        self.assertEqual((self.requester.email_index, self.requester.email_index_previous), ('', ''))
        self.assertFalse(RevealFieldRetention.objects.exists())

    def test_non_disclosure_encrypted_field_is_not_enrolled(self):
        self.enable()
        category = Category.objects.create(name='合成登记题目')
        challenge = Challenge.objects.create(title='合成登记范围', description='隔离样本', category=category,
            difficulty='easy', score=1, flag='flag{synthetic-retention-scope}')
        self.assertEqual(challenge.security_state, 'sealed-v1')
        self.assertEqual(challenge.read_protected('flag'), 'flag{synthetic-retention-scope}')
        self.assertFalse(RevealFieldRetention.objects.exists())

    def test_option_rejects_unknown_fields_and_unauthenticated_audit(self):
        self.enable()
        cases = [dict(self.config, reveal_retention={'scope_ref': SCOPE, 'ttl_seconds': 900}),
                 {key: value for key, value in self.config.items() if key != 'audit_chain'}]
        for config, code in zip(cases, (ReasonCode.UNKNOWN_FIELD, ReasonCode.SOURCE_NOT_APPROVED)):
            with self.subTest(code=code):
                self.path.write_text(json.dumps(config))
                with self.assertRaises(ContractViolation) as error:
                    assemble(config_path=self.path)
                self.assertEqual(error.exception.code, code)
        self.assertFalse(RevealFieldRetention.objects.exists())


class RevealRetentionRegistrationMigrationTests(TransactionTestCase):
    def test_additive_migration_does_not_enroll_legacy_requests_or_owner_fields(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
        old = [('security_policies', '0016_export_retention_intent')]
        new = [('security_policies', '0017_reveal_retention_registration')]
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(targets))
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        with patch.object(field_module, '_adapter', None):
            owner = CTFUser.objects.create_user(username='enrollment-migration', email=EXISTING)
        model = apps.get_model('security_policies', 'RevealRequest')
        values = dict(request_ref='request/enrollment-migration', requested_by_id=owner.pk,
            object_ref=str(owner.security_uuid), object_version='v1', fields=[['email', 'users.ctfuser/email']],
            purpose_ref='purpose/investigation', reason='合成迁移样本', requested_at=datetime.now(timezone.utc))
        row = model.objects.create(**values)
        for cycle in range(2):
            with self.subTest(cycle=cycle):
                executor = MigrationExecutor(connection)
                executor.migrate(new)
                apps = executor.loader.project_state(new).apps
                restored = apps.get_model('security_policies', 'RevealRequest').objects.get(pk=row.pk)
                self.assertIsNone(restored.retention_scope)
                self.assertIsNone(restored.retention_registration)
                for name, value in values.items():
                    self.assertEqual(getattr(restored, name), value)
                self.assertFalse(apps.get_model('security_policies', 'RevealFieldRetention').objects.exists())
                original = CTFUser.objects.get(pk=owner.pk)
                self.assertEqual(original.email, EXISTING)
                self.assertEqual(original.security_state, 'legacy-v0')
                if cycle == 0:
                    MigrationExecutor(connection).migrate(old)
