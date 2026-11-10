"""6-B02: real formal deliveries feed only permissioned reference-only recovery HTTP."""
from datetime import timedelta

from django.contrib.auth.models import Permission
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from audit.test_phase6_recovery_http import recovery_http
from ctf_backend.security_bootstrap import assemble_recovery_permissions
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution, RecoveryPermission
from data_security.contracts import ProtectionError
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.models import ColumnRiskPermission, ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision
from users.models import CTFUser

from .models import ExportSource, ExportSourcePermission
from .test_phase6_formal_fixtures import FormalResourceFixture, formal_call


class FormalRecoveryHTTPTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def setUp(self):
        super().setUp()
        self.source_ref, self.permission_ref, self.risk_ref, self.execution = self.ready()
        self.operator = CTFUser.objects.create_user(username='formal-recovery-operator', role='student')
        self.reviewer.user_permissions.add(Permission.objects.get(content_type__app_label='security_policies',
            codename='add_recoverypermission'))
        self.permissions = assemble_recovery_permissions(config_path=self.config_path)
        self.recovery_ref, _ = self.ok(self.permissions.manage(user=self.reviewer, binding=self.execution,
            operation='grant', grantee_id=self.operator.pk, expires_at=timezone.now() + timedelta(minutes=20),
            allow_release=True, allow_reconcile=True))
        delivery = self.config['export_delivery']
        self.config['export_recovery'] = {name: delivery[name] for name in ('window_key', 'limit', 'ttl_seconds')}
        self.write_config()

    def unknown(self):
        self.assertEqual(formal_call(self, 'fault', source_ref=self.source_ref, permission_ref=self.permission_ref,
            risk_ref=self.risk_ref, fault='put-unknown'), {'code': 'DELIVERY_UNKNOWN',
            'stages': ['complete-report-persisted']})
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
        self.assertEqual(QuotaReservation.objects.get().state, 'unknown')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.execution.quantity)

    def request(self, operation='reconcile', **changes):
        return {'user': self.operator.pk, 'operation': operation,
            'body': {'execution_ref': self.execution.execution_id, 'permission_ref': self.recovery_ref}, **changes}

    def state(self):
        return tuple(list(model.objects.order_by('pk').values()) for model in (
            ExportSource, ExportSourcePermission, ColumnRiskPermission, RiskDecision, IdempotencyRecord,
            ExecutionAuthorizationRecord, ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution,
            QuotaReservation, QuotaBucket, RecoveryPermission, AuthenticatedAuditEntry, SecurityAuditRecord))

    def test_formal_unknown_release_is_denied_then_authoritative_fence_settles_zero_once(self):
        self.unknown()
        report = ExportReport.objects.get()
        authority = self.state()[:7]
        before = self.state()
        response, = recovery_http(self, [self.request('release')])
        self.assertEqual(response, {'status': 403, 'body': {'code': 'AUTHORIZATION_DENIED'}, 'cache': 'no-store'})
        self.assertEqual(self.state(), before)
        audit_count = AuthenticatedAuditEntry.objects.count()
        responses = recovery_http(self, [self.request(), self.request()])
        expected = {'execution_ref': self.execution.execution_id, 'state': 'committed',
                    'delivered_records': 0, 'network_delivery_confirmed': False}
        self.assertEqual(responses, [{'status': 200, 'body': expected, 'cache': 'no-store'}] * 2)
        self.assertEqual(self.state()[:7], authority)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 0, 0))
        self.assertEqual(QuotaExecution.objects.get().terminal_operation, 'reconcile')
        current = ExportReport.objects.get()
        self.assertEqual((current.state, current.document, current.intent_hash), ('aborted', report.document, report.intent_hash))
        self.assertIsNone(current.delivery_receipt)
        self.assertEqual(set(PrivateObject.objects.values_list('state', flat=True)), {'verified'})
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), audit_count + 2)
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())
        self.assertEqual(formal_call(self, 'execute', source_ref=self.source_ref,
            permission_ref=self.permission_ref), {'code': 'AUTHORIZATION_DENIED'})

    def test_original_source_risk_and_target_authorities_are_not_recovery_permission(self):
        self.unknown()
        requests = [self.request(user=self.teacher.pk)]
        for reference in (self.permission_ref, self.risk_ref, ExportSource.objects.get().target_approval_ref):
            item = self.request()
            item['body']['permission_ref'] = reference
            requests.append(item)
        before = self.state()
        responses = recovery_http(self, requests)
        self.assertEqual([response['status'] for response in responses], [403] * len(requests))
        self.assertEqual([response['body'] for response in responses], [{'code': 'AUTHORIZATION_DENIED'}] * len(requests))
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 2)

    def test_current_recovery_actor_and_exact_operation_scope_are_required(self):
        self.unknown()
        RecoveryPermission.objects.filter(authorization_ref=self.recovery_ref).update(allow_reconcile=False)
        before = self.state()
        response, = recovery_http(self, [self.request()])
        self.assertEqual(response['status'], 403)
        self.assertEqual(self.state(), before)
        RecoveryPermission.objects.filter(authorization_ref=self.recovery_ref).update(allow_reconcile=True)
        CTFUser.objects.filter(pk=self.operator.pk).update(is_active=False)
        before = self.state()
        response, = recovery_http(self, [self.request()])
        self.assertEqual(response['status'], 403)
        self.assertEqual(self.state(), before)

    def test_revoked_or_expired_formal_recovery_permission_cannot_discard_unknown_capacity(self):
        self.unknown()
        for changes in ({'revoked_at': timezone.now()},
                        {'revoked_at': None, 'expires_at': timezone.now() - timedelta(seconds=1)}):
            with self.subTest(changes=changes):
                RecoveryPermission.objects.filter(authorization_ref=self.recovery_ref).update(**changes)
                before = self.state()
                response, = recovery_http(self, [self.request()])
                self.assertEqual(response['status'], 403)
                self.assertEqual(self.state(), before)
                self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 2)

    def test_missing_both_retained_binding_sources_is_unknown_not_proof_of_zero(self):
        self.unknown()
        ExportReport.objects.update(binding_document=None, document=None, document_hash='', private_object=None)
        before = self.state()
        response, = recovery_http(self, [self.request()])
        self.assertEqual(response['status'], 409)
        self.assertEqual(response['body'], {'code': 'DELIVERY_UNKNOWN'})
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 2)
        self.assertIsNone(QuotaExecution.objects.get().terminal_receipt)

    def test_database_read_failure_cannot_create_a_negative_effect_receipt(self):
        self.unknown()
        before = self.state()
        response, = recovery_http(self, [self.request()], fault='binding-database')
        self.assertEqual(response['status'], 409)
        self.assertEqual(response['body'], {'code': 'DELIVERY_UNKNOWN'})
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 2)
        self.assertIsNone(QuotaExecution.objects.get().terminal_receipt)

    def test_failed_actual_recovery_audit_rolls_back_fence_settlement_and_event_together(self):
        self.unknown()
        before = self.state()
        response, = recovery_http(self, [self.request()], fault='audit')
        self.assertEqual(response['status'], 409)
        self.assertEqual(response['body'], {'code': 'AUDIT_UNAVAILABLE'})
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 2)

    def test_lost_recovery_commit_confirmation_reuses_the_existing_zero_receipt_without_double_settlement(self):
        self.unknown()
        audit_count = AuthenticatedAuditEntry.objects.count()
        responses = recovery_http(self, [self.request(), self.request()], fault='confirmation')
        self.assertEqual([response['status'] for response in responses], [409, 200])
        self.assertEqual(responses[0]['body'], {'code': 'DELIVERY_UNKNOWN'})
        self.assertEqual(responses[1]['body']['delivered_records'], 0)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        self.assertEqual(QuotaBucket.objects.get().settled, 0)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 0)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), audit_count + 2)
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)

    def test_formal_delivered_winner_is_never_refunded_or_recommitted_and_status_is_not_download_permission(self):
        self.assertEqual(formal_call(self, 'fault', source_ref=self.source_ref, permission_ref=self.permission_ref,
            risk_ref=self.risk_ref, fault='delivery-confirmation-lost'), {'code': 'DELIVERY_UNKNOWN',
            'stages': ['real-delivery-committed-before-confirmation-loss']})
        before = self.state()
        responses = recovery_http(self, [self.request(), self.request('release')])
        expected = {'execution_ref': self.execution.execution_id, 'state': 'logically_delivered',
                    'delivered_records': 2, 'network_delivery_confirmed': False}
        self.assertEqual(responses, [{'status': 200, 'body': expected, 'cache': 'no-store'}] * 2)
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
        self.assertEqual(formal_call(self, 'open', source_ref=self.source_ref,
            permission_ref=self.permission_ref, user=self.operator.pk), {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(self.state(), before)

    def test_closed_recovery_preserves_formal_unknown_and_retains_existing_503_audit_behavior(self):
        self.unknown()
        del self.config['export_recovery']
        self.write_config()
        before = self.state()
        response, = recovery_http(self, [self.request()])
        self.assertEqual(response['status'], 503)
        self.assertEqual(response['body'], {'code': 'SOURCE_NOT_APPROVED'})
        after = self.state()
        self.assertEqual(after[:-1], before[:-1])
        self.assertEqual(after[-1][:-1], before[-1])
        self.assertEqual(len(after[-1]), len(before[-1]) + 1)
        self.assertEqual({field: after[-1][-1]['event'][field]
            for field in ('kind', 'outcome', 'reason', 'correlation_ref')},
            {'kind': 'protection', 'outcome': 'failed', 'reason': 'AUDIT_UNAVAILABLE', 'correlation_ref': 'audit/legacy'})
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 2)
