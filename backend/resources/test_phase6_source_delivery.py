"""Real private upload -> source read -> delivery; source/request authority is test-only.

TXT remains BINARY in the product. Only this synthetic fixture declares its CSV
interpretation, asset mapping, source approval, request and risk authorization.
No production source provider or HTTP entry is installed by these tests.
"""
from dataclasses import replace
from datetime import timedelta
import hashlib
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble_export_plan_approvals, assemble_resource_uploads
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PolicyVersion, PrivateObject
from data_security.adapters.persistence.orm_policies import ORMPolicyRepository
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.adapters.persistence.risk import DjangoRiskPort
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.adapters.tabular.codec import TableCodec
from data_security.application.export_flow import ExportFlow
from data_security.application.policy_catalog import PolicyCatalog
from data_security.application.reports import ReportAuthenticator
from data_security.application.table_reports import TableReportExecutor
from data_security.contracts import (
    ActionPlan, BASELINE_LIMITS, BoundedPayload, DeliveryReceipt, Environment, EventKind,
    ExecutionBinding, MediaType, ObjectContext, Outlet, PolicyRule, PolicySnapshot, PolicyStatus,
    ProtectionError, Purpose, ReasonCode, Role, canonical_bytes, content_hash,
)
from data_security.tests.fixtures import approval, examples
from data_security.tests.test_phase5_pipeline import OUTPUT_HASHES, pipeline_fixture
from data_security.tests.test_source_plans import convert, rebind, source_hash
from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService
from export_risk.contracts import RecommendedAction
from export_risk.models import ExecutionAuthorizationRecord, RiskDecision
from export_risk.tests.test_decisions import make_assessment, make_auth_snapshot, make_request
from users.models import CTFUser
from .models import Resource
from .test_phase6_private_uploads import PrivateResourceUploadFixture


class PrivateSourceDeliveryFixture(PrivateResourceUploadFixture):
    def setUp(self):
        super().setUp()
        fixture, _, self.expected, self.content = pipeline_fixture('legacy', 'csv')
        self.assertEqual(self.post(data=self.data(cover=True)).status_code, 201)
        self.resource = Resource.objects.get()
        self.original, source_context = self.stored_context(self.resource, 'file')
        self.source_context = source_context
        self.reader = assemble_resource_uploads(config_path=self.config_path,
            private_root=self.root, project_ref='resource-upload/synthetic', source_reads=True)
        self.approvals = assemble_export_plan_approvals(config_path=self.config_path)
        self.approver = CTFUser.objects.create_user(username='source-delivery-reviewer', role='teacher')
        self.approver.user_permissions.add(*Permission.objects.filter(content_type__app_label='security_policies',
            codename__in=('add_exportplanapproval', 'change_exportplanapproval')))

        # A test-only asset identity includes the original object, not just version "1".
        asset = f'resource/{source_context.object_uuid}/{source_context.object_version}'
        fixture.snapshot = replace(fixture.snapshot, asset_version=asset)
        fixture.options.update(asset_version=asset, created_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=10))
        fixture.doc['scope']['columns'] = ['Notes', 'Email']
        fixture.options['source_binding'] = replace(fixture.options['source_binding'],
            source_environment='evaluation', scope_hash=source_hash(fixture.doc['scope']))
        fixture.doc['operations'] = [fixture.doc['operations'][0], fixture.doc['operations'][2]]
        fixture.actions = fixture.actions[:-1]
        fixture.options['scope'] = replace(fixture.options['scope'], sheets=(
            replace(fixture.options['scope'].sheets[0], column_ids=('c2', 'c1')),))
        rebind(fixture)
        now = fixture.options['created_at']
        rule = PolicyRule(schema_version=PolicyRule.SCHEMA, category=fixture.actions[0].category,
            outlet=Outlet.EXPORT, role=Role.TEACHER, purpose=Purpose.DELIVERY, action=fixture.actions[0].algorithm)
        values = dict(schema_version=PolicySnapshot.SCHEMA, version='test-only/resource-source-policy',
            rules=(rule,), teaching_exceptions=(), effective_at=now, expires_at=fixture.options['expires_at'])
        policy_hash = content_hash(values)
        policy = PolicySnapshot(**values, status=PolicyStatus.APPROVED, content_hash=policy_hash,
            approval=approval(policy_hash, at=now))
        PolicyVersion.objects.create(version=policy.version, document=policy.to_wire())
        fixture.binding = replace(fixture.binding, protection_version=policy.version, protection_hash=policy_hash)
        self.plan = convert(fixture)
        self.assertIs(type(self.plan), ActionPlan)

        quantity = sum(end - start + 1 for sheet in self.plan.scope.sheets
                       for start, end in sheet.row_ranges) - len(self.plan.scope.sheets)
        self.request = replace(make_request(records=quantity, env='evaluation'),
            request_id='synthetic-source-' + uuid4().hex, subject_id='user/' + str(self.teacher.pk),
            asset_version=asset, scope=('resource/' + str(self.resource.pk),),
            recipient_id='synthetic/recipient', purpose='synthetic-delivery', request_fingerprint='')
        fingerprint = content_hash({'request': vars(self.request), 'scope': self.plan.scope,
            'source': self.plan.source, 'input_hash': self.plan.input_hash,
            'original': self.original, 'context': source_context})
        self.request = replace(self.request, request_fingerprint=fingerprint)
        self.binding = replace(examples()[ExecutionBinding], request_id=self.request.request_id,
            request_fingerprint=fingerprint, subject_ref=self.request.subject_id, quantity=quantity,
            asset_version=asset, scope=self.plan.scope, policy_binding=self.plan.policy_binding,
            domain_ref=self.plan.source.source_domain, environment='evaluation', expires_at=self.plan.expires_at)
        self.output_context = ObjectContext(schema_version=ObjectContext.SCHEMA,
            project_ref=source_context.project_ref, environment=Environment.EVALUATION, object_uuid=str(uuid4()),
            object_version=asset, field_ref='resources/export', authorization_ref=self.binding.authorization_id)
        self.assessment = replace(make_assessment(RecommendedAction.ALLOW), request_id=self.request.request_id,
            request_fingerprint=fingerprint, policy_version=self.plan.policy_binding.risk_version)
        self.risk_authorization = replace(make_auth_snapshot(env='evaluation'),
            subject_id=self.request.subject_id, data_domain=self.binding.domain_ref,
            allowed_scope=self.request.scope, allowed_recipients=(self.request.recipient_id,))
        self.flow = self.new_flow()
        decision = self.flow.risk.decide(self.request, self.plan.policy_binding)
        self.assertIs(type(decision), str)
        self.binding = replace(self.binding, decision_id=decision)
        approved = self.approvals.manage(user=self.approver, operation='approve', plan=self.plan,
            binding=self.binding, context=self.output_context, requester=self.teacher)
        self.assertIs(type(approved), tuple)
        self.plan, _ = approved
        self.owner = self.approvals.authorize(user=self.teacher, plan=self.plan,
            binding=self.binding, context=self.output_context)
        self.assertNotIsInstance(self.owner, ProtectionError)
        self.assertEqual(RiskDecision.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(ExportReport.objects.exists())
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())

    def new_flow(self):
        store = self.reader.read_source.__self__
        quota = DjangoQuotaPort(environment='evaluation', window_key='synthetic-source-delivery',
            limit=10, ttl_seconds=120)
        risk = DjangoRiskPort(request=self.request, scope=self.plan.scope, domain_ref=self.plan.source.source_domain,
            policy_binding=self.plan.policy_binding, environment='evaluation',
            assess=lambda request, policy: self.assessment, authorize=lambda request: self.risk_authorization,
            active_until=quota.active_until)
        authenticator = ReportAuthenticator(crypto=store.crypto, key=self.reader.audit.sink.key,
            executor_ref='test-only/resource-source-executor', environment=Environment.EVALUATION, clock=timezone.now)
        executor = TableReportExecutor(codec_factory=TableCodec, crypto=store.crypto,
            data_key=self.preparation.data_key, store=store, authenticator=authenticator,
            limits=BASELINE_LIMITS, clock=timezone.now)
        return ExportFlow(reports=DjangoReportRepository(environment=Environment.EVALUATION),
            authenticator=authenticator, store=store, risk=risk, quota=quota,
            policies=PolicyCatalog(repository=ORMPolicyRepository(), clock=timezone.now),
            authorize=lambda plan, binding, context: self.approvals.authorize(user=self.teacher,
                plan=plan, binding=binding, context=context), audit=self.reader.audit,
            uow_factory=DjangoUnitOfWork, clock=timezone.now, request=self.request,
            object_context=self.output_context, load_input=self.load_input, executor=executor)

    def load_input(self, plan, binding, owner):
        self.assertFalse(connection.in_atomic_block)
        self.assertTrue(connection.get_autocommit())
        self.assertEqual((plan, binding, owner), (self.plan, self.binding, self.owner))
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        opened = self.reader.read_original(user=self.teacher, resource_id=self.resource.pk)
        if isinstance(opened, ProtectionError):
            return opened
        self.assertIs(type(opened), BoundedPayload)
        self.assertIs(opened.media_type, MediaType.BINARY)
        # This interpretation is a synthetic source declaration, not a product fallback.
        return replace(opened, media_type=MediaType.CSV)

    def assert_held_without_delivery(self, *, state='preparing', objects=2):
        report = ExportReport.objects.get()
        self.assertEqual(report.state, state)
        self.assertIsNone(report.delivery_receipt)
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (2, 0, 0))
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(PrivateObject.objects.count(), objects)
        self.assertEqual(set(PrivateObject.objects.values_list('state', flat=True)), {'verified'})
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())
        self.assertEqual(list(self.media.iterdir()), [])


class PrivateSourceDeliveryTests(PrivateSourceDeliveryFixture, TransactionTestCase):
    def test_original_to_private_delivery_and_reassembled_status_replay(self):
        originals = {path.name: path.read_bytes() for path in self.root.iterdir()}
        resource = Resource.objects.values().get()
        reads = []
        read_file = self.flow.store._read_file

        def read_outside_transactions(reference, *args):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(connection.get_autocommit())
            reads.append(reference)
            return read_file(reference, *args)

        with patch.object(self.reader, 'read_original', wraps=self.reader.read_original) as source, \
                patch.object(self.flow.store, '_read_file', side_effect=read_outside_transactions), \
                patch.object(QuotaService, 'reserve', wraps=QuotaService.reserve) as reserve:
            receipt = self.flow.execute(self.plan, self.binding, self.owner)
        self.assertIs(type(receipt), DeliveryReceipt)
        self.assertEqual(receipt.delivered_records, 2)
        source.assert_called_once_with(user=self.teacher, resource_id=self.resource.pk)
        reserve.assert_called_once()
        cover, _ = self.stored_context(self.resource, 'cover_image')
        self.assertEqual(reads.count(self.original.object_ref), 1)
        self.assertNotIn(cover.object_ref, reads)
        record = self.flow.reports.read(self.binding)
        self.assertEqual(reads.count(record.stored.object_ref), 2)
        self.assertEqual(record.report.input_hash, hashlib.sha256(self.content).hexdigest())
        self.assertEqual(record.report.output_hash, OUTPUT_HASHES['legacy-csv'])
        self.assertEqual((record.report.coverage.total, record.report.coverage.processed,
                          record.report.coverage.excluded, record.report.hit_count), (9, 6, 3, 2))
        self.assertEqual(record.report.unresolved, ())
        self.assertIs(self.flow.authenticator.verify(record.report, record.proof, self.binding,
            self.plan, self.output_context, input_hash=self.plan.input_hash,
            output_hash=record.report.output_hash, ciphertext_hash=record.stored.ciphertext_hash), True)
        envelope = self.flow.store.read(record.stored, self.output_context)
        output = self.flow.store.crypto.open(envelope, self.output_context, envelope.key)
        self.assertIs(type(output), BoundedPayload)
        self.assertIs(output.media_type, MediaType.CSV)
        self.assertEqual(output.binary, self.expected)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 0)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
        self.assertEqual(PrivateObject.objects.filter(state='published').count(), 1)
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)
        self.assertEqual(self.reader.audit.sink.verify('ds.audit.v2'), receipt.audit)
        event = self.reader.audit.sink.read_authenticated(receipt.audit.event_id)
        self.assertIs(event.kind, EventKind.DELIVERY)
        self.assertEqual(dict(event.evidence_hashes),
            {'ciphertext': record.stored.ciphertext_hash, 'report': content_hash(record.report)})
        self.assertEqual(Resource.objects.values().get(), resource)
        for name, encoded in originals.items():
            self.assertEqual((self.root / name).read_bytes(), encoded)
        for path in self.root.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for marker in (b'a@example.invalid', b'b@example.invalid'):
                self.assertNotIn(marker, path.read_bytes())
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertEqual(self.flow.store.read(self.original, self.source_context).code, ReasonCode.AUTHORIZATION_DENIED)

        self.reader = assemble_resource_uploads(config_path=self.config_path,
            private_root=self.root, project_ref='resource-upload/synthetic', source_reads=True)
        self.approvals = assemble_export_plan_approvals(config_path=self.config_path)
        replay = self.new_flow()
        with patch.object(self.reader, 'read_original', side_effect=AssertionError('replay read original')), \
                patch.object(replay.quota, 'reserve', side_effect=AssertionError('replay reserved')), \
                patch.object(replay.store, 'publish', side_effect=AssertionError('replay published')):
            self.assertEqual(replay.execute(ActionPlan.from_wire(self.plan.to_wire()),
                ExecutionBinding.from_wire(self.binding.to_wire()), self.owner), receipt)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(ExportPlanApproval.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)
        self.assertEqual(canonical_bytes(replay.reports.read(self.binding), include_payload=True),
                         canonical_bytes(record, include_payload=True))

    def test_target_approval_does_not_grant_current_access_to_original(self):
        other = CTFUser.objects.create_user(username='different-source-owner', role='teacher')
        Resource.objects.filter(pk=self.resource.pk).update(uploader=other)
        with patch.object(self.reader, 'read_event', side_effect=AssertionError('source event read after denied ACL')), \
                patch.object(self.flow.executor, 'prepare', wraps=self.flow.executor.prepare) as prepare:
            result = self.flow.execute(self.plan, self.binding, self.owner)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        prepare.assert_not_called()
        self.assert_held_without_delivery()
        self.assertEqual(ExportPlanApproval.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)

    def test_raw_upload_event_and_target_approval_cannot_replace_source_authentication(self):
        event_id = f'resource-upload/{self.source_context.object_uuid}/file'
        AuthenticatedAuditEntry.objects.filter(record__event_id=event_id).delete()
        self.assertTrue(SecurityAuditRecord.objects.filter(event_id=event_id).exists())
        with patch.object(self.flow.store, '_read_file', side_effect=AssertionError('unauthenticated source file read')), \
                patch.object(self.flow.executor, 'prepare', wraps=self.flow.executor.prepare) as prepare:
            result = self.flow.execute(self.plan, self.binding, self.owner)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        prepare.assert_not_called()
        self.assert_held_without_delivery()
        self.assertEqual(ExportPlanApproval.objects.count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.count(), 3)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_bad_original_never_reaches_transform_or_repairs_its_ciphertext(self):
        path = self.root / (self.original.object_ref.removeprefix('private/') + '.sealed')
        encoded = path.read_bytes()
        broken = bytes([encoded[0] ^ 1]) + encoded[1:]
        path.write_bytes(broken)
        with patch.object(self.flow.executor, 'prepare', wraps=self.flow.executor.prepare) as prepare:
            result = self.flow.execute(self.plan, self.binding, self.owner)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, ReasonCode.HASH_MISMATCH)
        prepare.assert_not_called()
        self.assert_held_without_delivery()
        self.assertEqual(path.read_bytes(), broken)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)

    def test_target_revocation_after_real_source_open_blocks_final_commit(self):
        read = self.reader.read_original

        def revoke_after_open(**kwargs):
            opened = read(**kwargs)
            self.assertIs(type(opened), BoundedPayload)
            revoked = self.approvals.manage(user=self.approver, operation='revoke', plan=self.plan,
                binding=self.binding, context=self.output_context)
            self.assertIs(type(revoked), tuple)
            return opened

        with patch.object(self.reader, 'read_original', side_effect=revoke_after_open) as source:
            result = self.flow.execute(self.plan, self.binding, self.owner)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        source.assert_called_once()
        self.assert_held_without_delivery(state='prepared', objects=3)
        self.assertIsNotNone(ExportPlanApproval.objects.get().revoked_at)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)
