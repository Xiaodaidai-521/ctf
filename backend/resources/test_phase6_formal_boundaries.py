"""Formal-owner negatives, confirmation recovery and authenticated output boundaries."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import os
from unittest.mock import patch

from django.db import DatabaseError, connection
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution
from data_security.adapters.persistence.private_store import DjangoPrivateStore
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.application.table_reports import TableReportExecutor
from data_security.contracts import (
    ActionPlan, AuditReceipt, Environment, FrozenJSON, Outlet, PolicyStatus,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, Role, canonical_bytes, content_hash,
)
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.contracts import Disposition, reason_codes as rc
from export_risk.models import ColumnRiskPermission, ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision
from export_risk.policies.catalog import policy_hash, resolve_policy
from users.models import CTFUser

from .export_sources import document_hash
from .models import ExportSource, ExportSourcePermission
from .test_phase6_formal_fixtures import FormalResourceFixture, formal_call


def invoke_boundary(entry, user, reviewer, fields):
    """The ordinary-startup child supplies the real entry, never a bound test capability."""
    source_ref, permission_ref = fields['source_ref'], fields['permission_ref']
    case = fields['case']
    if case == 'grant-risk':
        result = entry.grant_risk(user=reviewer, source_ref=source_ref,
                                 expires_at=timezone.now() + timedelta(minutes=10))
    elif case == 'admit-history':
        assessment, decision_id, blocker = entry.admit(user=user, source_ref=source_ref,
            permission_ref=permission_ref, risk_permission_ref=fields['risk_ref'])
        assert blocker is not None
        approval = entry.risks.approve(user=reviewer, permission_ref=fields['risk_ref'])
        assert isinstance(approval, ProtectionError)
        return {'action': assessment.recommended_action.value, 'history': assessment.feature_set_version,
                'decision_id': decision_id, 'disposition': blocker.disposition.value,
                'reasons': list(blocker.reason_codes), 'approval_code': approval.code.value}
    elif case == 'target-confirmation':
        original = entry.targets.write_permission
        references = []
        def lost_confirmation(**kwargs):
            receipt = original(**kwargs)
            assert isinstance(receipt, AuditReceipt) and receipt.chain_version == 'ds.audit.v2'
            assert not connection.in_atomic_block
            references.append(kwargs['plan'].approval.approval_ref)
            raise DatabaseError('synthetic target commit confirmation lost')
        with patch.object(entry.targets, 'write_permission', side_effect=lost_confirmation):
            result = entry.approve_target(user=reviewer, source_ref=source_ref, requester=user)
        assert isinstance(result, ProtectionError) and len(references) == 1
        assert result.trace_id == references[0]
        return {'code': result.code.value, 'approval_ref': references[0]}
    elif case == 'target-reconcile':
        with patch.object(entry.targets, 'manage', side_effect=AssertionError('reconciliation issued approval')), \
             patch.object(entry.targets, 'write_permission', side_effect=AssertionError('reconciliation wrote approval')):
            result = entry.reconcile_target(user=reviewer, source_ref=source_ref,
                                             approval_ref=fields['approval_ref'])
        assert isinstance(result, ActionPlan)
        return {'approval_ref': result.approval.approval_ref}
    elif case in ('retire-policy-after-preparation', 'revoke-risk-after-preparation'):
        original = TableReportExecutor.prepare
        stages = []
        def change_authority(self, *args):
            candidate = original(self, *args)
            assert not isinstance(candidate, ProtectionError) and not connection.in_atomic_block
            if case == 'revoke-risk-after-preparation':
                receipt = entry.risks.revoke(user=reviewer, permission_ref=fields['risk_ref'])
                assert isinstance(receipt, AuditReceipt)
                stages.append('risk-revoked-after-real-preparation')
            else:
                components = assemble(config_path=os.environ['DATA_SECURITY_CONFIG'])
                admin = CTFUser.objects.get(pk=fields['admin'], is_active=True, role='admin')
                principal = ProtectionContext(schema_version=ProtectionContext.SCHEMA,
                    actor_ref='user/' + str(admin.pk), authorization_ref='authorization/isolated-policy-manager',
                    scope_refs=('policy/manage',), environment=Environment.EVALUATION, domain='ctf',
                    outlet=Outlet.API, purpose=Purpose.SECURITY_AUDIT, role=Role(admin.role),
                    object_ref='policy/isolated', object_version=components['binding'].protection_version,
                    source_ref=None, source_version=None, source_hash=None, trace_id='policy/isolated-retire')
                retired = components['catalog'].retire(components['binding'], principal)
                assert not isinstance(retired, ProtectionError) and retired.status is PolicyStatus.RETIRED
                stages.append('policy-retired-after-real-preparation')
            return candidate
        with patch.object(TableReportExecutor, 'prepare', change_authority):
            result = entry.execute(user=user, source_ref=source_ref, permission_ref=permission_ref)
        assert isinstance(result, ProtectionError) and len(stages) == 1
        return {'code': result.code.value, 'stages': stages}
    elif case == 'open-before-file':
        with patch.object(DjangoPrivateStore, '_read_file', side_effect=AssertionError('untrusted evidence opened file')):
            result = entry.open_delivery(user=user, source_ref=source_ref, permission_ref=permission_ref)
    else:
        raise AssertionError('unknown formal boundary case')
    assert isinstance(result, ProtectionError)
    return {'code': result.code.value}


class FormalAuthorityBoundaryTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def state(self):
        return tuple(list(model.objects.order_by('pk').values()) for model in (
            ExportSource, ExportSourcePermission, ColumnRiskPermission, RiskDecision, IdempotencyRecord,
            ExecutionAuthorizationRecord, ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution,
            QuotaReservation, QuotaBucket, AuthenticatedAuditEntry, SecurityAuditRecord))

    def boundary(self, case, source_ref, permission_ref, **fields):
        return formal_call(self, 'boundary', case=case, source_ref=source_ref,
                           permission_ref=permission_ref, admin=self.policy_admin.pk, **fields)

    def test_every_retained_execution_identity_scope_domain_and_policy_is_rechecked_before_effects(self):
        source_ref, permission_ref, _, binding = self.ready()
        row = ExportSource.objects.get(source_ref=source_ref)
        changes = (
            {'subject_ref': 'user/999'}, {'request_id': 'request/other'}, {'request_fingerprint': 'f' * 64},
            {'asset_version': 'resource/other'}, {'quantity': 1}, {'domain_ref': 'domain/other'},
            {'environment': 'test'}, {'authorization_id': 'authorization/other'},
            {'scope': replace(binding.scope, sheets=(replace(binding.scope.sheets[0], column_ids=('c2',)),))},
            {'policy_binding': replace(binding.policy_binding, protection_hash='e' * 64)},
            {'policy_binding': replace(binding.policy_binding, risk_hash='d' * 64)},
        )
        for change in changes:
            with self.subTest(field=next(iter(change))):
                document = {**row.execution_document, 'binding': replace(binding, **change).to_wire()}
                ExportSource.objects.filter(pk=row.pk).update(execution_document=document)
                before = self.state()
                self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                                 {'code': 'REPORT_MISMATCH'})
                self.assertEqual(self.state(), before)
        ExportSource.objects.filter(pk=row.pk).update(execution_document=row.execution_document)
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())

    def test_complete_frozen_request_and_source_plan_cannot_be_replaced_with_recomputed_unkeyed_hashes(self):
        source_ref, permission_ref, _, _ = self.ready()
        row = ExportSource.objects.get(source_ref=source_ref)
        for field, value in (('recipient_id', 'recipient/other'), ('purpose', 'other purpose'),
                             ('business_task_id', 'task/other')):
            with self.subTest(field=field):
                document = deepcopy(row.document)
                document['request'][field] = value
                digest = document_hash(document)
                ExportSource.objects.filter(pk=row.pk).update(document=document, document_hash=digest)
                ExportSourcePermission.objects.filter(authorization_ref=permission_ref).update(source_hash=digest)
                before = self.state()
                self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                                 {'code': 'AUDIT_UNAVAILABLE'})
                self.assertEqual(self.state(), before)
        ExportSource.objects.filter(pk=row.pk).update(document=row.document, document_hash=row.document_hash)
        ExportSourcePermission.objects.filter(authorization_ref=permission_ref).update(source_hash=row.document_hash)
        plan = ActionPlan.from_wire(row.plan_document)
        changed = replace(plan, plan_id='source-plan/other',
                          plan_hash=content_hash({**plan.content(), 'plan_id': 'source-plan/other'}))
        ExportSource.objects.filter(pk=row.pk).update(plan_document=changed.to_wire())
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'AUDIT_UNAVAILABLE'})
        self.assertEqual(self.state(), before)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_original_risk_assessment_and_conditional_approval_require_their_actual_authenticated_evidence(self):
        source_ref, permission_ref, risk_ref, _ = self.ready()
        row = ColumnRiskPermission.objects.get(permission_ref=risk_ref)
        document = deepcopy(row.grant_document)
        document['assessment']['reason_codes'] = ['substituted-reason']
        ColumnRiskPermission.objects.filter(pk=row.pk).update(grant_document=document)
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'REPORT_MISMATCH'})
        self.assertEqual(self.state(), before)
        ColumnRiskPermission.objects.filter(pk=row.pk).update(grant_document=row.grant_document,
            approval_document={**row.approval_document, 'approved_by': 'user/' + str(self.teacher.pk)})
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'REPORT_MISMATCH'})
        self.assertEqual(self.state(), before)
        self.assertEqual(RiskDecision.objects.get().action, 'require_approval')
        self.assertFalse(QuotaReservation.objects.exists())

    def test_missing_conditional_permission_does_not_reuse_target_or_previous_admission(self):
        source_ref, permission_ref, risk_ref, _ = self.ready()
        ColumnRiskPermission.objects.filter(permission_ref=risk_ref).delete()
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(self.state(), before)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_original_decision_expiry_is_not_renewed_by_persistent_conditional_approval(self):
        source_ref, permission_ref, _, _ = self.ready()
        RiskDecision.objects.update(valid_until=timezone.now() - timedelta(seconds=1))
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'AUTHORIZATION_EXPIRED'})
        self.assertEqual(self.state(), before)
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertEqual(ColumnRiskPermission.objects.get().state, 'approved')

    def test_required_history_policies_defer_both_absence_and_unverified_zero_claims_in_formal_supplier(self):
        claim = FrozenJSON({'feature_snapshot': {'feature_set_version': 'claimed/features',
            'as_of_time': timezone.now().isoformat(), 'values': {'req_count_long': 0, 'distinct_objects_long': 0,
                                                               'anomaly::model': 0},
            'units': {}, 'missing': [], 'data_watermark': timezone.now().isoformat(),
            'current_request_counted': False, 'quality': 'ok', 'baseline_ref': 'claimed/baseline'}})
        for version in ('B-v1', 'C-v1', 'D-v1'):
            for inputs in (FrozenJSON({}), claim):
                with self.subTest(version=version, claimed=bool(inputs.to_value())):
                    binding = replace(self.binding, risk_version=version, risk_hash=policy_hash(resolve_policy(version)))
                    self.config['policy_binding'] = binding.to_wire()
                    self.write_config()
                    self.entry = assemble(config_path=self.config_path)['export_delivery']
                    self.sources, self.risks = self.entry.sources, self.entry.risks
                    source_ref, permission_ref = self.approved_source(risk_inputs=inputs)
                    risk_ref, _ = self.ok(self.entry.grant_risk(user=self.reviewer, source_ref=source_ref,
                        expires_at=timezone.now() + timedelta(minutes=10)))
                    before = self.state()
                    value = self.boundary('admit-history', source_ref, permission_ref, risk_ref=risk_ref)
                    self.assertEqual((value['action'], value['history'], value['disposition'], value['approval_code']),
                                     ('require_approval', '', Disposition.DEFER.value, 'AUTHORIZATION_DENIED'))
                    self.assertIn(rc.DEGRADE_FEATURES_MISSING, value['reasons'])
                    self.assertEqual(formal_call(self, 'bind', source_ref=source_ref,
                        permission_ref=permission_ref, risk_ref=risk_ref), {'code': 'AUTHORIZATION_DENIED'})
                    self.assertEqual(self.state(), before)
                    self.assertEqual(ColumnRiskPermission.objects.get(permission_ref=risk_ref).state, 'pending')
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertFalse(ExportPlanApproval.objects.exists())

    def test_profile_claims_cannot_become_authority_merely_because_the_source_is_approved(self):
        for profile in ({'coverage': 'ok', 'status': 'current'}, {'asset_version': 'other/asset'},
                        {'protection_level': 'L2'}):
            with self.subTest(profile=profile):
                source_ref, permission_ref = self.approved_source(risk_inputs=FrozenJSON({'sensitivity_profile': profile}))
                before = self.state()
                self.assertEqual(self.boundary('grant-risk', source_ref, permission_ref),
                                 {'code': 'SOURCE_NOT_APPROVED'})
                self.assertEqual(self.state(), before)
        self.assertFalse(ColumnRiskPermission.objects.exists())
        self.assertFalse(RiskDecision.objects.exists())
        self.assertFalse(QuotaReservation.objects.exists())

    def test_lost_target_approval_confirmation_recovers_exact_existing_authority_without_a_second_approval(self):
        source_ref, permission_ref = self.approved_source()
        risk_ref, _ = self.ok(self.entry.grant_risk(user=self.reviewer, source_ref=source_ref,
            expires_at=timezone.now() + timedelta(minutes=10)))
        self.ok(self.risks.approve(user=self.reviewer, permission_ref=risk_ref))
        self.ok(self.entry.bind(user=self.teacher, source_ref=source_ref, permission_ref=permission_ref,
                               risk_permission_ref=risk_ref))
        value = self.boundary('target-confirmation', source_ref, permission_ref)
        self.assertEqual(value['code'], 'DELIVERY_UNKNOWN')
        approval = ExportPlanApproval.objects.get()
        self.assertEqual(approval.approval_ref, value['approval_ref'])
        self.assertFalse(ExportSource.objects.get().target_approval_ref)
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'POLICY_NOT_APPROVED'})
        self.assertEqual(self.state(), before)
        authority = (list(ExportPlanApproval.objects.values()), list(AuthenticatedAuditEntry.objects.values()))
        for _ in range(2):
            self.assertEqual(self.boundary('target-reconcile', source_ref, permission_ref,
                approval_ref=value['approval_ref']), {'approval_ref': value['approval_ref']})
        self.assertEqual((list(ExportPlanApproval.objects.values()), list(AuthenticatedAuditEntry.objects.values())), authority)
        self.assertEqual(ExportSource.objects.get().target_approval_ref, value['approval_ref'])
        delivered = formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref)
        self.assertEqual(delivered['delivery']['delivered_records'], 2)
        self.assertEqual(ExportPlanApproval.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)

    def test_current_policy_retirement_after_real_preparation_denies_commit_without_refunding_hold(self):
        source_ref, permission_ref, _, _ = self.ready()
        self.assertEqual(self.boundary('retire-policy-after-preparation', source_ref, permission_ref),
            {'code': 'POLICY_NOT_APPROVED', 'stages': ['policy-retired-after-real-preparation']})
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (2, 0, 0))
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
        self.assertEqual(set(PrivateObject.objects.values_list('state', flat=True)), {'verified'})
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())

    def test_current_risk_revocation_after_real_preparation_denies_commit_without_refunding_hold(self):
        source_ref, permission_ref, risk_ref, _ = self.ready()
        self.assertEqual(self.boundary('revoke-risk-after-preparation', source_ref, permission_ref, risk_ref=risk_ref),
            {'code': 'AUTHORIZATION_DENIED', 'stages': ['risk-revoked-after-real-preparation']})
        self.assertEqual(ColumnRiskPermission.objects.get().state, 'revoked')
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (2, 0, 0))
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())

    def test_delivered_output_rejects_forged_report_mac_ciphertext_and_missing_authenticated_delivery(self):
        source_ref, permission_ref, _, binding = self.ready()
        delivery = formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref)['delivery']
        record = self.ok(DjangoReportRepository(environment=Environment.EVALUATION).read(binding))
        row = ExportReport.objects.get()
        bad = replace(record, proof=replace(record.proof, authentication=b'\x00' * len(record.proof.authentication)))
        ExportReport.objects.filter(pk=row.pk).update(document=bad.to_wire(include_payload=True),
            document_hash=hashlib.sha256(canonical_bytes(bad, include_payload=True)).hexdigest())
        before = self.state()
        self.assertEqual(self.boundary('open-before-file', source_ref, permission_ref), {'code': 'REPORT_MISMATCH'})
        self.assertEqual(self.state(), before)
        ExportReport.objects.filter(pk=row.pk).update(document=row.document, document_hash=row.document_hash)
        path = self.root / (record.stored.object_ref.removeprefix('private/') + '.sealed')
        encoded = path.read_bytes()
        corrupted = bytes([encoded[0] ^ 1]) + encoded[1:]
        path.write_bytes(corrupted)
        before = self.state()
        self.assertEqual(formal_call(self, 'open', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'HASH_MISMATCH'})
        self.assertEqual(self.state(), before)
        self.assertEqual(path.read_bytes(), corrupted)
        path.write_bytes(encoded)
        AuthenticatedAuditEntry.objects.filter(record__event_id=delivery['audit']['event_id']).delete()
        before = self.state()
        self.assertEqual(self.boundary('open-before-file', source_ref, permission_ref), {'code': 'AUDIT_UNAVAILABLE'})
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')

    def test_delivered_output_requires_current_source_use_even_with_valid_target_and_risk(self):
        source_ref, permission_ref, _, _ = self.ready()
        formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref)
        self.ok(self.sources.revoke_permission(user=self.reviewer, permission_ref=permission_ref))
        before = self.state()
        self.assertEqual(self.boundary('open-before-file', source_ref, permission_ref), {'code': 'SOURCE_NOT_APPROVED'})
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)

    def test_delivered_output_requires_current_target_approval_even_with_valid_source_and_risk(self):
        source_ref, permission_ref, _, binding = self.ready()
        formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref)
        owned = self.ok(self.entry._bound(user=self.teacher, source_ref=source_ref, permission_ref=permission_ref))
        self.ok(self.entry.targets.manage(user=self.reviewer, operation='revoke', plan=owned.plan,
                                         binding=binding, context=owned.context))
        before = self.state()
        self.assertEqual(self.boundary('open-before-file', source_ref, permission_ref), {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
