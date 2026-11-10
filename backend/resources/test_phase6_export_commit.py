"""Real PG commit stage; synthetic owner/keys, real versioned audit and rollback.

The unconfigured v1 sink MUST reject a v2 delivery rather than silently downgrade.
"""
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock, patch

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.adapters.persistence.models import ExportReport, PolicyVersion, PrivateObject
from data_security.adapters.persistence.orm_policies import ORMPolicyRepository
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.adapters.persistence.risk import DjangoRiskPort
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.adapters.tabular.codec import TableCodec
from data_security.application.audit_gateway import AuditGateway
from data_security.application.export_flow import ExportFlow
from data_security.application.policy_catalog import PolicyCatalog
from data_security.application.reports import ReportAuthenticator
from data_security.application.table_reports import ReportCandidate, TableReportExecutor
from data_security.contracts import (
    Algorithm, BASELINE_LIMITS, DeliveryReceipt, Environment, ExecutionBinding, KeyPurpose, MediaType,
    PolicyRule, PolicySnapshot, PolicyStatus, ProtectionContext, ProtectionError,
    ReasonCode, ReportRecord, content_hash,
)
from data_security.tests.fixtures import approval, examples
from data_security.tests.phase2_fixtures import reference_key
from data_security.tests.test_phase5_codec import binary
from data_security.tests.test_phase5_pipeline import pipeline_fixture
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.contracts import ExecutionAuthorization, RecommendedAction
from export_risk.models import ExecutionAuthorizationRecord
from export_risk.tests.test_decisions import make_assessment, make_auth_snapshot, make_request
from resources.test_phase6_private_store import PrivateStoreFixture


class ExportOwnerFixture(PrivateStoreFixture):
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql')
        now = timezone.now()
        _, source_plan, _, content = pipeline_fixture('legacy', 'csv')
        # A new test-only owner plan: all email actions DROP, matching a single
        # approved rule. This is not a claim of current business-owner approval.
        drop = replace(source_plan.actions[0].algorithm, algorithm=Algorithm.DROP, replacement=None)
        actions = tuple(replace(a, algorithm=drop) for a in source_plan.actions)
        owner = examples()[ProtectionContext]
        rule = PolicyRule(schema_version=PolicyRule.SCHEMA, category=actions[0].category,
            outlet=owner.outlet, role=owner.role, purpose=owner.purpose, action=drop)
        values = dict(schema_version=PolicySnapshot.SCHEMA, version='test-only/flow-policy', rules=(rule,),
            teaching_exceptions=(), effective_at=now, expires_at=now + timedelta(minutes=5))
        policy_hash = content_hash(values)
        self.policy = PolicySnapshot(**values, status=PolicyStatus.APPROVED, content_hash=policy_hash,
                                     approval=approval(policy_hash, at=now))
        PolicyVersion.objects.create(version=self.policy.version, document=self.policy.to_wire())
        policy_binding = replace(source_plan.policy_binding, protection_version=self.policy.version,
                                 protection_hash=policy_hash)
        values = dict(source_plan.content(), actions=actions, policy_binding=policy_binding,
                      created_at=now, expires_at=self.policy.expires_at)
        plan = replace(source_plan, actions=actions, policy_binding=policy_binding, created_at=now,
                       expires_at=self.policy.expires_at, approval=None, plan_hash=content_hash(values))
        binding = replace(examples()[ExecutionBinding], policy_binding=policy_binding, scope=plan.scope,
            asset_version=plan.asset_version, expires_at=plan.expires_at, domain_ref=plan.source.source_domain)
        request = replace(make_request(fp=binding.request_fingerprint), request_id=binding.request_id,
                          subject_id=binding.subject_ref, asset_version=binding.asset_version)
        assessment = replace(make_assessment(RecommendedAction.ALLOW), request_id=request.request_id,
            request_fingerprint=request.request_fingerprint, policy_version=policy_binding.risk_version)
        auth_snapshot = replace(make_auth_snapshot(), subject_id=request.subject_id, data_domain=binding.domain_ref)
        self.quota = DjangoQuotaPort(environment='test', window_key='commit-stage', limit=10, ttl_seconds=120)
        self.risk = DjangoRiskPort(request=request, scope=binding.scope, domain_ref=binding.domain_ref,
            policy_binding=policy_binding, environment='test', assess=Mock(return_value=assessment),
            authorize=Mock(return_value=auth_snapshot), active_until=self.quota.active_until)
        binding = replace(binding, decision_id=self.risk.decide(request, policy_binding))
        context = replace(self.context, object_version=plan.asset_version, authorization_ref=binding.authorization_id)
        auth = ReportAuthenticator(crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
            executor_ref='test-only/flow-executor', environment=Environment.TEST, clock=timezone.now)
        executor = TableReportExecutor(codec_factory=TableCodec, crypto=self.crypto, data_key=self.key,
            store=self.store, authenticator=auth, limits=BASELINE_LIMITS, clock=timezone.now)
        self.plan, self.binding, self.object_context = plan, binding, context
        self.auth, self.executor, self.payload = auth, executor, binary(content, MediaType.CSV)
        self.reports = DjangoReportRepository(environment=Environment.TEST)
        owner = replace(owner, actor_ref=binding.subject_ref, authorization_ref=binding.authorization_id,
            scope_refs=(context.field_ref,), domain=binding.domain_ref, object_ref=context.object_uuid,
            object_version=context.object_version)
        self.owner = owner
        self.flow = ExportFlow(reports=self.reports, authenticator=auth, store=self.store, risk=self.risk,
            quota=self.quota, policies=PolicyCatalog(repository=ORMPolicyRepository(), clock=timezone.now),
            authorize=Mock(return_value=owner), audit=AuditGateway(sink=DjangoAuditSink(clock=timezone.now)),
            uow_factory=DjangoUnitOfWork, clock=timezone.now, request=request, object_context=context,
            load_input=Mock(return_value=self.payload), executor=executor)


class ExportCommitPostgresTests(ExportOwnerFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.quota.reserve(self.binding)
        self.assertIsInstance(self.risk.issue(self.binding), ExecutionAuthorization)
        candidate = self.executor.prepare(self.payload, self.plan, self.binding, self.object_context)
        self.assertIsInstance(candidate, ReportCandidate)
        self.record = ReportRecord(schema_version=ReportRecord.SCHEMA, binding=self.binding, plan=self.plan,
            context=self.object_context, stored=candidate.stored, report=candidate.report, proof=candidate.proof)
        self.assertEqual(self.reports.put(self.record), self.record)

    def commit(self):
        return self.flow.commit(self.record.plan, self.record.binding, self.record.context)

    def assert_rolled_back(self):
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
        self.assertTrue(self.path(self.record.stored).exists())
        self.denied(self.store.read(self.record.stored, self.record.context), ReasonCode.AUTHORIZATION_DENIED)

    def test_real_v1_audit_is_rejected_and_all_database_effects_roll_back(self):
        ledger_count = AuditLedgerEntry.objects.count()
        authenticate = self.store.verify
        def verify(*args):
            self.assertFalse(connection.in_atomic_block)
            return authenticate(*args)
        with patch.object(self.store, 'verify', side_effect=verify), \
                patch.object(self.quota, 'commit', wraps=self.quota.commit) as settle, \
                patch.object(self.flow.audit, 'record', wraps=self.flow.audit.record) as audited:
            self.denied(self.commit(), ReasonCode.AUDIT_UNAVAILABLE)
            settle.assert_called_once_with(self.record.binding, 2)
            audited.assert_called_once()
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        self.assertEqual(AuditLedgerEntry.objects.count(), ledger_count)
        self.assert_rolled_back()

    def test_failure_after_real_quota_write_rolls_back_publish_consume_and_balance(self):
        commit = self.quota.commit
        def fail_after_write(binding, delivered):
            self.assertTrue(connection.in_atomic_block)
            result = commit(binding, delivered)
            self.assertNotIsInstance(result, ProtectionError)
            self.assertEqual(PrivateObject.objects.get().state, 'published')
            self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
                                   retryable=False, trace_id='test-only/after-quota')
        with patch.object(self.quota, 'commit', side_effect=fail_after_write):
            self.denied(self.commit(), ReasonCode.DELIVERY_UNKNOWN)
        self.assert_rolled_back()

    def test_real_v2_commits_once_and_authenticates_report_and_ciphertext_evidence(self):
        sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
                               context=self.context)
        self.flow.audit = AuditGateway(sink=sink)
        first = self.commit()
        self.assertIsInstance(first, DeliveryReceipt)
        self.assertEqual(first.delivered_records, 2)
        self.assertEqual(first.audit.chain_version, 'ds.audit.v2')
        self.assertEqual(PrivateObject.objects.get().state, 'published')
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 0)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(self.reports.delivery(self.record.binding), first)
        self.assertEqual(sink.verify('ds.audit.v2'), first.audit)
        event = SecurityAuditRecord.objects.get(event_id=first.audit.event_id).event
        self.assertEqual(event['evidence_hashes'], [
            ['ciphertext', self.record.stored.ciphertext_hash], ['report', content_hash(self.record.report)]])
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        ledger_count = AuditLedgerEntry.objects.count()
        with patch.object(self.quota, 'commit', wraps=self.quota.commit) as settle, \
                patch.object(self.store, 'publish', wraps=self.store.publish) as publish:
            self.assertEqual(self.commit(), first)
            settle.assert_not_called()
            publish.assert_not_called()
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(AuditLedgerEntry.objects.count(), ledger_count)

    def test_failure_after_real_v2_append_rolls_back_chain_and_entire_delivery(self):
        sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
                               context=self.context)
        self.flow.audit = AuditGateway(sink=sink)
        def fail_receipt(receipt):
            self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
            self.assertEqual(PrivateObject.objects.get().state, 'published')
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
                                   retryable=False, trace_id='test-only/after-v2')
        with patch.object(self.reports, 'record_delivery', side_effect=fail_receipt):
            self.denied(self.commit(), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        self.assert_rolled_back()

    def test_policy_retirement_after_preparation_prevents_publication(self):
        retired = replace(self.policy, status=PolicyStatus.RETIRED)
        PolicyVersion.objects.filter(version=self.policy.version).update(document=retired.to_wire())
        with patch.object(self.store, 'publish', wraps=self.store.publish) as publish:
            self.denied(self.commit(), ReasonCode.POLICY_NOT_APPROVED)
            publish.assert_not_called()
        self.assert_rolled_back()
