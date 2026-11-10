"""Internal recovery orchestration; doubles do not prove PostgreSQL atomicity."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import MagicMock, Mock

from data_security.application.export_flow import ExportFlow
from data_security.contracts import (
    AuditReceipt, DeliveryReceipt, Durability, ExecutionBinding, ProtectionError,
    QuotaReceipt, QuotaRecoveryEvent, QuotaState, ReasonCode, content_hash,
)
from data_security.tests.fixtures import AT, examples, recovery_context


class ExportRecoveryTests(TestCase):
    def setUp(self):
        self.binding = examples()[ExecutionBinding]
        self.reports = Mock(abort=Mock(return_value=None))
        self.actor = recovery_context(self.binding)
        self.authorize = Mock(return_value=self.actor)
        self.quota = Mock()
        self.quota.release.side_effect = lambda binding, evidence: QuotaReceipt(
            schema_version=QuotaReceipt.SCHEMA, binding=binding, state=QuotaState.RELEASED,
            observed_at=AT, settled_amount=None, evidence_ref=evidence)
        self.quota.reconcile.side_effect = lambda binding, delivered, evidence: QuotaReceipt(
            schema_version=QuotaReceipt.SCHEMA, binding=binding, state=QuotaState.COMMITTED,
            observed_at=AT, settled_amount=delivered, evidence_ref=evidence)
        self.work = MagicMock()
        self.work.__enter__.return_value = self.work
        self.work.__exit__.return_value = None
        self.audit = Mock(record=Mock(side_effect=lambda e, d: AuditReceipt(schema_version=AuditReceipt.SCHEMA,
            event_id=e.event_id, durability=d, stored_at=e.occurred_at, chain_version='ds.audit.v2',
            entry_ref='test-double/recovery', sequence=1, entry_hash='0' * 64, checkpoint_ref=None)))
        self.flow = ExportFlow(reports=self.reports, authenticator=Mock(), store=Mock(),
            risk=Mock(), quota=self.quota, policies=Mock(), authorize=Mock(), audit=self.audit,
            uow_factory=Mock(return_value=self.work), clock=lambda: AT,
            authorize_recovery=self.authorize)

    def error(self, code=ReasonCode.DELIVERY_UNKNOWN):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='test/recovery')

    def test_release_fences_before_current_recovery_authorization_and_quota(self):
        calls = Mock()
        for name, method in (('abort', self.reports.abort), ('authorize', self.authorize),
                             ('release', self.quota.release), ('audit', self.audit.record),
                             ('commit', self.work.commit)):
            calls.attach_mock(method, name)
        result = self.flow.release(self.binding)
        self.assertIsInstance(result, QuotaReceipt)
        self.assertIs(result.state, QuotaState.RELEASED)
        self.assertEqual([c[0] for c in calls.mock_calls], ['abort', 'authorize', 'release', 'audit', 'commit'])
        self.authorize.assert_called_once_with(self.binding, 'release')
        evidence = 'flow/no-delivery/' + content_hash({'domain': 'ds.abort.v1', 'binding': self.binding})
        self.quota.release.assert_called_once_with(self.binding, evidence)
        self.quota.reserve.assert_not_called()
        self.quota.reconcile.assert_not_called()
        self.assertFalse(self.flow.store.mock_calls or self.flow.risk.mock_calls)

    def test_reconcile_uses_fenced_zero_not_a_caller_supplied_delivered_amount(self):
        result = self.flow.reconcile(self.binding)
        self.assertIs(result.state, QuotaState.COMMITTED)
        self.assertEqual(result.settled_amount, 0)
        self.quota.reconcile.assert_called_once_with(self.binding, 0, result.evidence_ref)
        self.authorize.assert_called_once_with(self.binding, 'reconcile')
        self.quota.release.assert_not_called()
        self.work.commit.assert_called_once()

    def test_existing_delivery_is_status_only_without_republication_or_settlement(self):
        receipt = examples()[DeliveryReceipt]
        self.reports.abort.return_value = receipt
        for operation in ('release', 'reconcile'):
            with self.subTest(operation=operation):
                self.assertEqual(getattr(self.flow, operation)(self.binding), receipt)
        self.assertFalse(self.quota.mock_calls or self.flow.store.mock_calls or self.flow.risk.mock_calls)
        self.work.commit.assert_not_called()

    def test_absent_or_failed_fence_never_proves_zero_delivery(self):
        for code in (ReasonCode.REPORT_MISMATCH, ReasonCode.DELIVERY_UNKNOWN, ReasonCode.IDEMPOTENCY_CONFLICT):
            self.reports.abort.return_value = self.error(code)
            for operation in ('release', 'reconcile'):
                self.assertEqual(getattr(self.flow, operation)(self.binding), self.error(code))
        self.assertFalse(self.quota.mock_calls)
        self.work.commit.assert_not_called()

    def test_recovery_permission_is_explicit_and_checked_after_lock_wait(self):
        self.flow.authorize_recovery = None
        self.assertEqual(self.flow.release(self.binding).code, ReasonCode.AUTHORIZATION_DENIED)
        self.reports.abort.assert_not_called()
        self.flow.authorize_recovery = self.authorize
        for grant in (True, False, None, 1, self.error(ReasonCode.AUTHORIZATION_DENIED)):
            self.authorize.return_value = grant
            self.assertEqual(self.flow.reconcile(self.binding).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(self.quota.mock_calls)
        self.work.commit.assert_not_called()

    def test_expired_execution_can_be_cancelled_only_under_current_recovery_permission(self):
        self.flow.clock = lambda: self.binding.expires_at
        self.assertIs(self.flow.release(self.binding).state, QuotaState.RELEASED)
        self.authorize.assert_called_once_with(self.binding, 'release')
        self.assertFalse(self.flow.risk.mock_calls or self.flow.store.mock_calls)

    def test_unknown_quota_error_does_not_commit_abort_or_fall_back_to_release(self):
        self.quota.reconcile.side_effect = None
        self.quota.reconcile.return_value = self.error()
        self.assertEqual(self.flow.reconcile(self.binding), self.error())
        self.quota.release.assert_not_called()
        self.work.commit.assert_not_called()

    def test_audit_binds_actual_operator_current_grant_operation_and_full_quota_receipt(self):
        result = self.flow.release(self.binding)
        event, durability = self.audit.record.call_args.args
        self.assertIs(type(event), QuotaRecoveryEvent)
        self.assertIs(durability, Durability.LEDGER_CONFIRMED)
        self.assertEqual((event.actor_ref, event.authorization_ref),
                         (self.actor.actor_ref, self.actor.authorization_ref))
        self.assertNotEqual(event.actor_ref, self.binding.subject_ref)
        self.assertEqual(event.operation, 'release')
        self.assertEqual(event.quota, result)
        self.assertEqual(event.counts, (('records', 0),))

    def test_missing_or_weak_audit_prevents_terminal_commit(self):
        issue = self.audit.record.side_effect
        for failure in (self.error(ReasonCode.AUDIT_UNAVAILABLE),
                        lambda e, d: replace(issue(e, d), chain_version='v1')):
            self.audit.record.side_effect = failure if callable(failure) else lambda *args: failure
            self.assertEqual(self.flow.release(self.binding).code, ReasonCode.AUDIT_UNAVAILABLE)
            self.work.commit.assert_not_called()

    def test_current_recovery_context_must_match_execution_domain_and_scope(self):
        for actor in (replace(self.actor, object_ref='other/execution'),
                      replace(self.actor, domain='other/domain'),
                      replace(self.actor, scope_refs=('other/reservation',))):
            self.authorize.return_value = actor
            self.assertEqual(self.flow.reconcile(self.binding).code, ReasonCode.AUTHORIZATION_DENIED)
        self.audit.record.assert_not_called()
        self.assertFalse(self.quota.mock_calls)

    def test_wrong_settlement_and_commit_acknowledgement_loss_are_unknown(self):
        produce = self.quota.reconcile.side_effect
        self.quota.reconcile.side_effect = lambda b, n, e: replace(produce(b, n, e), settled_amount=1)
        self.assertEqual(self.flow.reconcile(self.binding).code, ReasonCode.DELIVERY_UNKNOWN)
        self.work.commit.assert_not_called()
        self.quota.reconcile.side_effect = produce
        self.work.__exit__.side_effect = RuntimeError('synthetic lost commit acknowledgement')
        self.assertEqual(self.flow.reconcile(self.binding).code, ReasonCode.DELIVERY_UNKNOWN)
        self.quota.release.assert_not_called()
