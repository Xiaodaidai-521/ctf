"""Focused transactional owner tests with synthetic audit ports and real Risk services.

These are not formal B, cryptographic-chain or PostgreSQL concurrency evidence.
The main runner owns serial integration validation; this module starts no services.
"""
from dataclasses import replace
from datetime import timedelta
import hashlib
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Permission
from django.db import transaction
from django.test import TransactionTestCase
from django.utils import timezone

from data_security.adapters.persistence.risk import DjangoRiskPort
from data_security.application.audit_gateway import AuditGateway
from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, FrozenJSON, PolicyBinding, ProtectionError,
    ReasonCode, TableScope, canonical_bytes, content_hash,
)
from data_security.tests.fixtures import examples
from export_quota.models import QuotaReservation
from export_risk.column_authority import (
    ADD, CHANGE, USE, ColumnRiskOwner, ColumnRiskSupplier, decode_request, freeze_request,
)
from export_risk.contracts import Disposition, QualityState, RecommendedAction, SourceMode
from export_risk.contracts import reason_codes as rc
from export_risk.decisions.service import check_execution_eligibility, invalidate_decision
from export_risk.models import ColumnRiskPermission, ExecutionAuthorizationRecord, RiskDecision
from export_risk.policies.catalog import policy_hash, resolve_policy
from users.models import CTFUser


class EvidenceSink:
    """Tests-only authenticated-read stand-in, not an approval/status authority."""
    def __init__(self, clock):
        self.clock, self.events, self.reads = clock, {}, []
        self.fail_write = False
        self.chain_version = 'ds.audit.v2'

    def append(self, event, durability):
        if not transaction.get_connection().in_atomic_block:
            raise AssertionError('risk authority and audit must share a transaction')
        if self.fail_write:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                   retryable=False, trace_id='test/audit')
        self.events[event.event_id] = event
        return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=event.event_id,
            durability=durability, stored_at=self.clock(), chain_version=self.chain_version,
            entry_ref='test/ledger/' + str(len(self.events)), sequence=len(self.events),
            entry_hash=content_hash(event), checkpoint_ref=None)

    def read(self, event_id):
        if transaction.get_connection().in_atomic_block:
            raise AssertionError('authenticated evidence read inside held-lock UoW')
        self.reads.append(event_id)
        return self.events.get(event_id, ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='test/audit-read'))


class ColumnRiskAuthorityTests(TransactionTestCase):
    def setUp(self):
        self.now = timezone.now()
        self.sink = EvidenceSink(lambda: self.now)
        self.owner = ColumnRiskOwner(AuditGateway(sink=self.sink), self.sink.read, lambda: self.now)
        self.requester = CTFUser.objects.create_user(username='column-risk-requester', role='teacher')
        self.approver = CTFUser.objects.create_user(username='column-risk-approver', role='teacher')
        self.permissions = {name: Permission.objects.get(content_type__app_label='export_risk',
                                                        codename=name.split('.')[1])
                            for name in (ADD, CHANGE, USE)}
        self.requester.user_permissions.add(self.permissions[USE])
        self.approver.user_permissions.add(self.permissions[ADD], self.permissions[CHANGE])
        self.scope = examples()[TableScope]
        self.policy = replace(examples()[PolicyBinding], risk_version='policy-m0',
                              risk_hash=policy_hash(resolve_policy('policy-m0')))
        self.inputs = FrozenJSON({})
        self.frozen = freeze_request({'recipient_id': 'recipient/internal', 'purpose': 'approved task'},
            request_id='column-request/1', subject_id='user/' + str(self.requester.pk), asset_version='resource/v1',
            scope=('resource/1',), record_count=1, environment='evaluation', source_mode=SourceMode.EVALUATION)
        self.request = decode_request({**self.frozen.to_value(), 'request_fingerprint': hashlib.sha256(canonical_bytes({
            'request': vars(decode_request(self.frozen)), 'source': 'a' * 64, 'scope': self.scope,
            'policy': self.policy, 'risk': self.inputs}, include_payload=True)).hexdigest()})
        self.arguments = dict(source_ref='source/column-1', source_hash='a' * 64, request=self.request,
            scope=self.scope, domain_ref='domain/column', policy_binding=self.policy, risk_inputs=self.inputs)

    def grant(self, **changes):
        return self.owner.grant(user=self.approver, expires_at=self.now + timedelta(minutes=5),
                                **{**self.arguments, **changes})

    def load(self, permission_ref, **changes):
        return self.owner.load(user=self.requester, permission_ref=permission_ref,
                               **{**self.arguments, **changes})

    def approved(self):
        permission_ref, receipt = self.grant()
        self.assertIsInstance(receipt, AuditReceipt)
        self.assertIsInstance(self.owner.approve(self.approver, permission_ref), AuditReceipt)
        supplier = self.load(permission_ref)
        self.assertIsInstance(supplier, ColumnRiskSupplier)
        return permission_ref, supplier

    def test_freeze_and_decode_keep_complete_original_request_and_empty_initial_fingerprint(self):
        self.assertEqual(self.frozen.to_value()['request_fingerprint'], '')
        self.assertEqual(decode_request(self.frozen).request_fingerprint, '')
        forged = freeze_request({'recipient_id': 'recipient/internal', 'request_id': 'client/forged',
                                 'subject_id': 'user/999', 'request_fingerprint': 'f' * 64},
            request_id='server/1', subject_id=self.request.subject_id, asset_version=self.request.asset_version,
            scope=self.request.scope, record_count=1, environment='evaluation', source_mode=SourceMode.EVALUATION)
        self.assertEqual(forged.to_value()['request_id'], 'server/1')
        self.assertEqual(forged.to_value()['subject_id'], self.request.subject_id)
        self.assertEqual(forged.to_value()['request_fingerprint'], '')
        for change in ({'extra': True}, {'source_mode': 'production'}, {'environment': 'production'},
                       {'schema_version': 'other'}, {'scope': [{}]}, {'request_fingerprint': 'not-a-digest'}):
            with self.subTest(change=change), self.assertRaises(ContractViolation):
                decode_request({**self.request.__dict__, 'scope': list(self.request.scope),
                                'source_mode': self.request.source_mode.value, **change})

    def test_missing_profile_is_genuine_pending_and_original_decision_is_exposed_without_execution(self):
        permission_ref, receipt = self.grant()
        self.assertEqual(receipt.chain_version, 'ds.audit.v2')
        self.assertIs(receipt.durability, Durability.LEDGER_CONFIRMED)
        supplier = self.load(permission_ref)
        assessment, decision_id, blocker = supplier.admit()
        self.assertEqual(assessment.recommended_action, RecommendedAction.REQUIRE_APPROVAL)
        self.assertIn(rc.DEGRADE_PROFILE_INCOMPLETE, assessment.reason_codes)
        self.assertEqual(assessment.profile_id, '')
        self.assertEqual(assessment.feature_set_version, '')
        self.assertEqual(supplier._profile.asset_version, self.request.asset_version)
        self.assertEqual(supplier._profile.source_mode, self.request.source_mode)
        self.assertEqual(supplier._profile.coverage, QualityState.MISSING)
        self.assertEqual(supplier._profile.status, 'unknown')
        self.assertEqual(supplier._profile.protection_level, 'unknown')
        self.assertEqual(decision_id, ColumnRiskPermission.objects.get().decision_id)
        self.assertEqual(blocker.disposition, Disposition.REQUIRE_APPROVAL)
        self.assertEqual(supplier.status(decision_id, self.request.request_fingerprint), 'pending')
        self.assertEqual(supplier.status(decision_id, 'f' * 64), 'none')
        self.assertEqual(RiskDecision.objects.count(), 1)
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(supplier.is_production_authority)

    def test_second_actor_approval_reloads_proof_and_reuses_exact_original_ds_risk_key(self):
        permission_ref, _ = self.grant()
        pending = self.load(permission_ref)
        self.requester.user_permissions.add(self.permissions[CHANGE])
        self.assertEqual(self.owner.approve(self.requester, permission_ref).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.owner.approve(self.approver, permission_ref, 'dec/wrong').code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.assertIsInstance(self.owner.approve(self.approver, permission_ref, pending.decision_id), AuditReceipt)
        with self.assertRaises(ContractViolation):
            pending.status(pending.decision_id, self.request.request_fingerprint)
        supplier = self.load(permission_ref)
        assessment, decision_id, blocker = supplier.admit()
        self.assertIsNone(blocker)
        self.assertEqual(assessment.recommended_action, RecommendedAction.REQUIRE_APPROVAL)
        self.assertEqual(RiskDecision.objects.get().action, 'require_approval')
        def no_quota(execution):
            self.fail('admission must not read or reserve quota')
        port = DjangoRiskPort(request=self.request, scope=self.scope, domain_ref=self.arguments['domain_ref'],
            policy_binding=self.policy, environment='evaluation', assess=supplier.assess, authorize=supplier.authorize,
            approval=supplier.approval, active_until=no_quota)
        self.assertEqual(port.decide(self.request, self.policy), decision_id)
        self.assertEqual(RiskDecision.objects.count(), 1)
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertFalse(QuotaReservation.objects.exists())

    def test_authenticated_original_assessment_is_reloaded_without_rerunning_judgment(self):
        permission_ref, _ = self.grant()
        original = list(RiskDecision.objects.values())
        with patch('export_risk.column_authority.assess_risk',
                   side_effect=AssertionError('retained risk assessment was recomputed')):
            pending = self.load(permission_ref)
            assessment, decision_id, blocker = pending.admit()
            self.assertEqual(blocker.disposition, Disposition.REQUIRE_APPROVAL)
            self.assertIsInstance(self.owner.approve(self.approver, permission_ref), AuditReceipt)
            supplier = self.load(permission_ref)
            self.assertEqual(supplier.assess(self.request, self.policy), assessment)
            self.assertEqual(supplier.admit(), (assessment, decision_id, None))
        document = ColumnRiskPermission.objects.get().grant_document['assessment']
        self.assertEqual(document['recommended_action'], assessment.recommended_action.value)
        self.assertEqual(document['request_fingerprint'], self.request.request_fingerprint)
        self.assertEqual(document['authorization_snapshot_id'], permission_ref)
        self.assertEqual(list(RiskDecision.objects.values()), original)
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertFalse(QuotaReservation.objects.exists())

    def test_original_idempotency_conflict_is_returned_without_rewriting_decision(self):
        permission_ref, _ = self.grant()
        decision_id = self.load(permission_ref).decision_id
        # Deliberately reuse the frozen request instead of registering new inputs.
        inputs = FrozenJSON({'evaluation_time': (self.now - timedelta(seconds=1)).isoformat()})
        self.assertEqual(self.grant(risk_inputs=inputs).code, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(ColumnRiskPermission.objects.count(), 1)
        self.assertEqual(RiskDecision.objects.get().decision_id, decision_id)
        self.assertEqual(RiskDecision.objects.get().action, 'require_approval')

    def test_risk_capabilities_are_explicit_live_and_not_roles_source_or_target_permissions(self):
        self.approver.user_permissions.clear()
        CTFUser.objects.filter(pk=self.approver.pk).update(role='admin', is_staff=True)
        self.assertEqual(self.grant().code, ReasonCode.AUTHORIZATION_DENIED)
        self.approver.user_permissions.add(self.permissions[ADD])
        self.requester.user_permissions.clear()
        self.requester.user_permissions.add(*Permission.objects.filter(
            content_type__app_label__in=('resources', 'security_policies')))
        self.assertEqual(self.grant().code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(ColumnRiskPermission.objects.exists())
        self.requester.user_permissions.add(self.permissions[USE])
        permission_ref, _ = self.grant()
        self.assertEqual(self.owner.approve(self.approver, permission_ref).code, ReasonCode.AUTHORIZATION_DENIED)
        self.approver.user_permissions.add(self.permissions[CHANGE])
        self.assertIsInstance(self.owner.approve(self.approver, permission_ref), AuditReceipt)
        supplier = self.load(permission_ref)
        self.assertTrue(self.requester.has_perm(USE))
        self.requester.user_permissions.clear()
        self.assertEqual(supplier.authorize(self.request).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(supplier.status(supplier.decision_id, self.request.request_fingerprint), 'none')
        self.assertEqual(supplier.admit()[2].disposition, Disposition.DENY)
        self.assertEqual(self.load(permission_ref).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.owner.grant(AnonymousUser(), **self.arguments,
            expires_at=self.now + timedelta(minutes=5)).code, ReasonCode.AUTHORIZATION_DENIED)

    def test_historical_approver_permission_loss_does_not_auto_revoke_but_inactive_requester_cannot_use(self):
        permission_ref, supplier = self.approved()
        self.approver.user_permissions.clear()
        CTFUser.objects.filter(pk=self.approver.pk).update(is_active=False)
        rebuilt = self.load(permission_ref)
        self.assertEqual(rebuilt.status(supplier.decision_id, self.request.request_fingerprint), 'approved')
        CTFUser.objects.filter(pk=self.requester.pk).update(is_active=False)
        self.assertEqual(rebuilt.authorize(self.request).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(rebuilt.status(supplier.decision_id, self.request.request_fingerprint), 'none')

    def test_revoke_none_and_expiry_are_non_approved_without_renewal(self):
        permission_ref, supplier = self.approved()
        self.assertIsInstance(self.owner.revoke(self.approver, permission_ref), AuditReceipt)
        self.assertEqual(supplier.status(supplier.decision_id, self.request.request_fingerprint), 'revoked')
        self.assertEqual(supplier.authorize(self.request).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.owner.approve(self.approver, permission_ref).code, ReasonCode.AUTHORIZATION_DENIED)
        ColumnRiskPermission.objects.filter(permission_ref=permission_ref).delete()
        self.assertEqual(supplier.status(supplier.decision_id, self.request.request_fingerprint), 'none')
        permission_ref, supplier = self.approved()
        original_deadline = supplier.active_until
        self.now = original_deadline
        self.assertEqual(supplier.status(supplier.decision_id, self.request.request_fingerprint), 'none')
        self.assertEqual(supplier.authorize(self.request).code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.assertEqual(supplier.admit()[2].disposition, Disposition.DEFER)
        self.assertEqual(supplier.active_until, original_deadline)

    def test_expired_pending_grant_cannot_be_approved(self):
        permission_ref, _ = self.grant()
        supplier = self.load(permission_ref)
        self.now = supplier.active_until
        self.assertEqual(supplier.status(supplier.decision_id, self.request.request_fingerprint), 'none')
        self.assertEqual(self.owner.approve(self.approver, permission_ref).code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.assertEqual(ColumnRiskPermission.objects.get().state, 'pending')
        self.assertNotIn(permission_ref + '/approve', self.sink.events)

    def test_every_source_request_scope_policy_and_risk_input_binding_is_exact(self):
        permission_ref, _ = self.grant()
        changes = (
            {'source_ref': 'source/other'}, {'source_hash': 'b' * 64}, {'domain_ref': 'domain/other'},
            {'request': replace(self.request, request_fingerprint='b' * 64)},
            {'request': replace(self.request, recipient_id='recipient/other')},
            {'request': replace(self.request, record_count=2)},
            {'scope': replace(self.scope, sheets=(replace(self.scope.sheets[0], column_ids=('column:2',)),))},
            {'policy_binding': replace(self.policy, risk_hash='c' * 64)},
            {'risk_inputs': FrozenJSON({'model_version': 'unavailable-model-label'})},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assertIsInstance(self.load(permission_ref, **change), ProtectionError)
        for policy in (replace(self.policy, risk_version='missing-policy'),
                       replace(self.policy, risk_version='risk/disabled-phase4'),
                       replace(self.policy, risk_hash='f' * 64)):
            self.assertEqual(self.grant(policy_binding=policy).code, ReasonCode.POLICY_NOT_APPROVED)
        self.assertIsInstance(self.load(permission_ref), ColumnRiskSupplier)

    def test_authenticated_grant_and_approval_evidence_cannot_be_substituted(self):
        permission_ref, supplier = self.approved()
        grant_event = self.sink.events[permission_ref + '/grant']
        self.sink.events[grant_event.event_id] = replace(grant_event, actor_ref='user/999')
        self.assertEqual(self.load(permission_ref).code, ReasonCode.REPORT_MISMATCH)
        self.sink.events[grant_event.event_id] = grant_event
        approved_event = self.sink.events[permission_ref + '/approve']
        self.sink.events[approved_event.event_id] = replace(approved_event, evidence_hashes=(('report', 'f' * 64),))
        self.assertEqual(self.load(permission_ref).code, ReasonCode.REPORT_MISMATCH)
        self.sink.events.pop(approved_event.event_id)
        self.assertEqual(self.load(permission_ref).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.sink.events[approved_event.event_id] = approved_event
        row = ColumnRiskPermission.objects.get(permission_ref=permission_ref)
        ColumnRiskPermission.objects.filter(pk=row.pk).update(approval_document={**row.approval_document,
                                                                                'request_fingerprint': 'f' * 64})
        with self.assertRaises(ContractViolation):
            supplier.status(supplier.decision_id, self.request.request_fingerprint)
        self.assertEqual(self.load(permission_ref).code, ReasonCode.REPORT_MISMATCH)

    def test_malformed_persisted_grant_documents_fail_at_owner_boundary(self):
        permission_ref, _ = self.grant()
        row = ColumnRiskPermission.objects.get()
        original = row.grant_document
        missing_request = {**original['binding']['request']}
        missing_request.pop('request_fingerprint')
        malformed = ([], {}, {**original, 'binding': {}},
                     {**original, 'binding': {**original['binding'], 'request': missing_request}})
        for document in malformed:
            with self.subTest(document=document):
                ColumnRiskPermission.objects.filter(pk=row.pk).update(grant_document=document)
                self.assertIsInstance(self.load(permission_ref), ProtectionError)
                self.assertIsInstance(self.owner.approve(self.approver, permission_ref), ProtectionError)
                self.assertIsInstance(self.owner.revoke(self.approver, permission_ref), ProtectionError)
        ColumnRiskPermission.objects.filter(pk=row.pk).update(grant_document=original)
        self.assertIsInstance(self.load(permission_ref), ColumnRiskSupplier)

    def test_required_history_stays_defer_even_for_zero_valued_unverified_feature_claims(self):
        claim = FrozenJSON({'feature_snapshot': {'feature_set_version': 'claimed/fs',
            'as_of_time': self.now.isoformat(), 'values': {'req_count_long': 0, 'distinct_objects_long': 0,
                                                         'anomaly::model': 0},
            'units': {}, 'missing': [], 'data_watermark': self.now.isoformat(),
            'current_request_counted': False, 'quality': 'ok', 'baseline_ref': 'claimed/baseline'}})
        for version in ('B-v1', 'C-v1', 'D-v1'):
            policy = replace(self.policy, risk_version=version, risk_hash=policy_hash(resolve_policy(version)))
            for inputs in (self.inputs, claim):
                with self.subTest(version=version, inputs=inputs):
                    request = replace(self.request, request_fingerprint=hashlib.sha256(canonical_bytes({
                        'request': vars(decode_request(self.frozen)), 'source': 'a' * 64, 'scope': self.scope,
                        'policy': policy, 'risk': inputs}, include_payload=True)).hexdigest())
                    permission_ref, _ = self.grant(request=request, policy_binding=policy, risk_inputs=inputs)
                    supplier = self.load(permission_ref, request=request, policy_binding=policy, risk_inputs=inputs)
                    assessment, decision_id, blocker = supplier.admit()
                    self.assertEqual(assessment.recommended_action, RecommendedAction.REQUIRE_APPROVAL)
                    self.assertEqual(assessment.feature_set_version, '')
                    self.assertEqual(blocker.disposition, Disposition.DEFER)
                    self.assertIn(rc.DEGRADE_FEATURES_MISSING, blocker.reason_codes)
                    self.assertIsInstance(supplier.assess(request, policy), ProtectionError)
                    self.assertEqual(self.owner.approve(self.approver, permission_ref).code, ReasonCode.AUTHORIZATION_DENIED)
                    row = ColumnRiskPermission.objects.get(permission_ref=permission_ref)
                    self.assertEqual(row.state, 'pending')
                    self.assertEqual(row.grant_document['initial_disposition'], 'defer')
                    self.assertEqual(RiskDecision.objects.get(decision_id=decision_id).action, 'require_approval')

    def test_complete_or_wrong_asset_profile_claims_are_not_a_profile_authority(self):
        for profile in ({'coverage': 'ok', 'status': 'current'}, {'asset_version': 'other/asset'},
                        {'protection_level': 'L2'}, {'categories': ['email']}, {'source_mode': 'production'}):
            with self.subTest(profile=profile):
                self.assertEqual(self.grant(risk_inputs=FrozenJSON({'sensitivity_profile': profile})).code,
                                 ReasonCode.SOURCE_NOT_APPROVED)
        self.assertFalse(ColumnRiskPermission.objects.exists())
        for inputs in ({'extra': True}, {'feature_snapshot': {'quality': 'invented'}},
                       {'feature_snapshot': {'values': {'req_count_long': 'zero'}}}):
            self.assertIsInstance(self.grant(risk_inputs=FrozenJSON(inputs)), ProtectionError)
        self.assertFalse(RiskDecision.objects.exists())

    def test_original_deny_or_defer_cannot_be_cleared_by_conditional_approval(self):
        permission_ref, _ = self.grant()
        supplier = self.load(permission_ref)
        invalidate_decision(supplier.decision_id)
        self.assertEqual(supplier.admit()[2].disposition, Disposition.DENY)
        self.assertEqual(self.owner.approve(self.approver, permission_ref).code, ReasonCode.AUTHORIZATION_DENIED)
        inputs = FrozenJSON({'evaluation_time': (self.now - timedelta(seconds=1)).isoformat()})
        request = replace(self.request, request_id='column-request/deferred', request_fingerprint='d' * 64)
        permission_ref, _ = self.grant(request=request, risk_inputs=inputs)
        supplier = self.load(permission_ref, request=request, risk_inputs=inputs)
        assessment, _, blocker = supplier.admit()
        self.assertEqual(assessment.recommended_action, RecommendedAction.DEFER)
        self.assertEqual(blocker.disposition, Disposition.DEFER)
        self.assertEqual(self.owner.approve(self.approver, permission_ref).code, ReasonCode.AUTHORIZATION_DENIED)

    def test_live_flow_callbacks_do_not_authenticate_evidence_inside_a_uow(self):
        permission_ref, supplier = self.approved()
        reads = list(self.sink.reads)
        with transaction.atomic():
            snapshot = supplier.authorize(self.request)
            self.assertIsNone(check_execution_eligibility(supplier.decision_id, self.request, snapshot,
                environment='evaluation', approval=supplier.approval))
            self.assertEqual(self.load(permission_ref).code, ReasonCode.DELIVERY_UNKNOWN)
            self.assertEqual(self.grant().code, ReasonCode.DELIVERY_UNKNOWN)
            self.assertEqual(self.owner.approve(self.approver, permission_ref).code, ReasonCode.DELIVERY_UNKNOWN)
            self.assertEqual(self.owner.revoke(self.approver, permission_ref).code, ReasonCode.DELIVERY_UNKNOWN)
            self.assertEqual(supplier.admit().code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(self.sink.reads, reads)

    def test_failed_audit_rolls_back_own_grant_approval_and_revocation(self):
        self.sink.fail_write = True
        self.assertEqual(self.grant().code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertFalse(ColumnRiskPermission.objects.exists())
        self.assertFalse(RiskDecision.objects.exists())
        self.sink.fail_write = False
        permission_ref, _ = self.grant()
        self.sink.fail_write = True
        self.assertEqual(self.owner.approve(self.approver, permission_ref).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(ColumnRiskPermission.objects.get().state, 'pending')
        self.sink.fail_write = False
        self.owner.approve(self.approver, permission_ref)
        self.sink.fail_write = True
        self.assertEqual(self.owner.revoke(self.approver, permission_ref).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(ColumnRiskPermission.objects.get().state, 'approved')
        self.assertIsNone(ColumnRiskPermission.objects.get().revoked_at)

    def test_non_v2_receipt_and_expiry_extension_do_not_create_authority(self):
        self.sink.chain_version = 'v1'
        self.assertEqual(self.grant().code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertFalse(ColumnRiskPermission.objects.exists())
        self.sink.chain_version = 'ds.audit.v2'
        permission_ref, supplier = self.approved()
        ColumnRiskPermission.objects.filter(permission_ref=permission_ref).update(
            expires_at=supplier.active_until + timedelta(minutes=1))
        self.assertEqual(supplier.authorize(self.request).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.load(permission_ref).code, ReasonCode.REPORT_MISMATCH)
