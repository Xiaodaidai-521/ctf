"""Real Flow consumes current target approval; request/source providers remain synthetic fixtures."""
from dataclasses import replace
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.test import TransactionTestCase
from django.utils import timezone

from audit.export_plans import ExportPlanOwner
from audit.models import AuthenticatedAuditEntry
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.adapters.persistence.export_plans import DjangoExportPlanApprovals
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PolicyVersion, PrivateObject
from data_security.application.audit_gateway import AuditGateway
from data_security.contracts import DeliveryReceipt, Environment, KeyPurpose, ReasonCode, Role, content_hash
from data_security.tests.fixtures import approval
from data_security.tests.phase2_fixtures import reference_key
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.models import ExecutionAuthorizationRecord
from users.models import CTFUser
from .test_phase6_export_commit import ExportOwnerFixture


class ExportPlanConsumptionTests(ExportOwnerFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.requester = CTFUser.objects.create_user(username='flow-plan-requester', role='teacher')
        self.approver = CTFUser.objects.create_user(username='flow-plan-approver', role='teacher')
        self.approver.user_permissions.add(*Permission.objects.filter(content_type__app_label='security_policies',
            codename__in=('add_exportplanapproval', 'change_exportplanapproval')))
        rules = tuple(replace(rule, role=Role.TEACHER) for rule in self.policy.rules)
        values = self.policy.content()
        values['rules'] = rules
        policy_hash = content_hash(values)
        self.policy = replace(self.policy, rules=rules, content_hash=policy_hash,
                              approval=approval(policy_hash, at=self.policy.effective_at))
        PolicyVersion.objects.filter(version=self.policy.version).update(document=self.policy.to_wire())
        policy_binding = replace(self.binding.policy_binding, protection_hash=policy_hash)
        values = dict(self.plan.content(), policy_binding=policy_binding)
        self.plan = replace(self.plan, policy_binding=policy_binding, plan_hash=content_hash(values))
        self.binding = replace(self.binding, subject_ref='user/' + str(self.requester.pk), policy_binding=policy_binding)
        self.risk.request = replace(self.risk.request, subject_id=self.binding.subject_ref)
        self.risk.policy_binding = policy_binding
        self.risk.authorize.return_value = replace(self.risk.authorize.return_value, subject_id=self.binding.subject_ref)
        self.binding = replace(self.binding, decision_id=self.risk.decide(self.risk.request, policy_binding))
        self.flow.request = self.risk.request
        sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
                               context=self.context)
        self.gateway = AuditGateway(sink=sink)
        self.flow.audit = self.gateway
        permissions = DjangoExportPlanApprovals(record_event=self.gateway.record, clock=timezone.now)
        self.approvals = ExportPlanOwner(write_permission=permissions.write, read_permission=permissions.authorize,
            identity=lambda: uuid4().hex, clock=timezone.now, environment=Environment.TEST)
        self.plan, _ = self.approvals.manage(user=self.approver, operation='approve', plan=self.plan,
            binding=self.binding, context=self.object_context, requester=self.requester)
        self.flow.authorize = lambda plan, binding, context: self.approvals.authorize(
            user=self.requester, plan=plan, binding=binding, context=context)
        self.owner = self.flow.authorize(self.plan, self.binding, self.object_context)

    def revoke(self):
        return self.approvals.manage(user=self.approver, operation='revoke', plan=self.plan,
                                    binding=self.binding, context=self.object_context)

    def test_real_execute_uses_approved_plan_and_replays_without_new_quota_or_approval(self):
        receipt = self.flow.execute(self.plan, self.binding, self.owner)
        self.assertIsInstance(receipt, DeliveryReceipt)
        self.assertEqual(receipt.delivered_records, 2)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(PrivateObject.objects.get().state, 'published')
        self.assertEqual(ExportPlanApproval.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.flow.load_input.reset_mock()
        self.assertEqual(self.flow.execute(self.plan, self.binding, self.owner), receipt)
        self.flow.load_input.assert_not_called()
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(self.gateway.sink.verify('ds.audit.v2'), receipt.audit)

    def test_revocation_before_admission_does_not_reserve_or_prepare(self):
        self.revoke()
        self.denied(self.flow.execute(self.plan, self.binding, self.owner), ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(ExportReport.objects.exists())
        self.assertFalse(PrivateObject.objects.exists())
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.flow.load_input.assert_not_called()

    def test_revocation_during_lock_free_preparation_blocks_commit_and_keeps_hold(self):
        def load(*args):
            _, receipt = self.revoke()
            self.assertEqual(receipt.chain_version, 'ds.audit.v2')
            return self.payload
        self.flow.load_input.side_effect = load
        self.denied(self.flow.execute(self.plan, self.binding, self.owner), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, self.binding.quantity)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assertEqual(ExportReport.objects.get().state, 'prepared')
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
