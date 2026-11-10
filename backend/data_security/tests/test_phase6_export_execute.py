"""Execute ownership/order with doubles; real side effects have PostgreSQL tests."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock, sentinel

from data_security.application.table_reports import ReportCandidate
from data_security.contracts import DeliveryReceipt, ProtectionError, QuotaReceipt, QuotaState, ReasonCode
from data_security.tests.fixtures import AT, examples, recovery_context
from data_security.tests.test_phase6_export_flow import ExportFlowFixture


class ExportExecuteTests(ExportFlowFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.flow.request = sentinel.owner_request
        self.flow.object_context = self.record.context
        self.flow.load_input = Mock(return_value=sentinel.payload)
        self.flow.executor = Mock(prepare=Mock(return_value=ReportCandidate(
            stored=self.record.stored, report=self.record.report, proof=self.record.proof)))
        self.flow.authorize_recovery = Mock(return_value=recovery_context(self.record.binding))
        self.reports.read.return_value = None
        self.reports.begin.return_value = True
        self.reports.abort.return_value = None
        self.reports.put.side_effect = lambda record: record
        self.risk.decide.return_value = self.record.binding.decision_id
        self.risk.issue.return_value = sentinel.authorization
        self.quota.reserve.side_effect = lambda binding: QuotaReceipt(schema_version=QuotaReceipt.SCHEMA,
            binding=binding, state=QuotaState.RESERVED, observed_at=AT, settled_amount=None, evidence_ref='test/hold')
        self.quota.release.side_effect = lambda binding, evidence: QuotaReceipt(schema_version=QuotaReceipt.SCHEMA,
            binding=binding, state=QuotaState.RELEASED, observed_at=AT, settled_amount=None, evidence_ref=evidence)
        self.quota.reconcile.side_effect = lambda binding, delivered, evidence: QuotaReceipt(
            schema_version=QuotaReceipt.SCHEMA, binding=binding, state=QuotaState.UNKNOWN,
            observed_at=AT, settled_amount=None, evidence_ref=evidence)
        self.receipt = replace(examples()[DeliveryReceipt], binding=self.record.binding)
        self.flow.commit = Mock(return_value=self.receipt)

    def execute(self):
        return self.flow.execute(self.record.plan, self.record.binding, self.owner)

    def test_single_reservation_commits_before_claim_load_and_prepare(self):
        calls = Mock()
        for name, method in (('decide', self.risk.decide), ('begin', self.reports.begin),
            ('reserve', self.quota.reserve), ('uow_commit', self.work.commit), ('issue', self.risk.issue),
            ('load', self.flow.load_input), ('prepare', self.flow.executor.prepare),
            ('put', self.reports.put), ('deliver', self.flow.commit)):
            calls.attach_mock(method, name)
        self.assertEqual(self.execute(), self.receipt)
        self.assertEqual([c[0] for c in calls.mock_calls],
                         ['decide', 'begin', 'reserve', 'uow_commit', 'issue', 'load', 'prepare', 'put', 'deliver'])
        self.quota.reserve.assert_called_once_with(self.record.binding)
        self.flow.executor.prepare.assert_called_once_with(sentinel.payload, self.record.plan,
                                                            self.record.binding, self.record.context)
        self.reports.put.assert_called_once_with(self.record)
        self.quota.release.assert_not_called()
        self.quota.reconcile.assert_not_called()

    def test_completed_replay_never_reloads_input_claims_reserves_or_commits(self):
        self.reports.read.return_value = self.record
        self.reports.delivery.return_value = self.receipt
        self.flow.clock = lambda: self.record.binding.expires_at
        self.assertEqual(self.execute(), self.receipt)
        self.flow.load_input.assert_not_called()
        self.flow.executor.prepare.assert_not_called()
        self.flow.commit.assert_not_called()
        self.assertFalse(self.risk.mock_calls or self.quota.mock_calls)

    def test_pending_or_competing_owner_never_reclaims_or_fences_the_winner(self):
        self.reports.begin.return_value = False
        self.assertEqual(self.execute().code, ReasonCode.DELIVERY_UNKNOWN)
        self.reports.abort.assert_not_called()
        self.assertFalse(self.quota.mock_calls)
        self.reports.read.return_value = self.record
        self.assertEqual(self.execute().code, ReasonCode.DELIVERY_UNKNOWN)
        self.flow.commit.assert_not_called()
        self.flow.load_input.assert_not_called()

    def test_wrong_current_owner_policy_or_decision_denies_before_reserve(self):
        self.authorize.return_value = replace(self.owner, authorization_ref='other/authorization')
        self.assertEqual(self.execute().code, ReasonCode.AUTHORIZATION_DENIED)
        self.authorize.return_value = self.owner
        self.risk.decide.return_value = 'other/decision'
        self.assertEqual(self.execute().code, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.risk.decide.return_value = self.error()
        self.assertEqual(self.execute(), self.error())
        self.assertFalse(self.quota.mock_calls)
        self.flow.load_input.assert_not_called()

    def test_declined_reservation_rolls_back_without_issue_load_or_release(self):
        self.quota.reserve.side_effect = None
        self.quota.reserve.return_value = self.error(ReasonCode.LIMIT_EXCEEDED)
        self.assertEqual(self.execute(), self.error(ReasonCode.LIMIT_EXCEEDED))
        self.work.commit.assert_not_called()
        self.risk.issue.assert_not_called()
        self.flow.load_input.assert_not_called()
        self.quota.release.assert_not_called()

    def test_plan_expiry_after_report_lock_prevents_reserve_without_cleanup(self):
        def begin(*args):
            self.flow.clock = lambda: self.record.plan.expires_at
            return True
        self.reports.begin.side_effect = begin
        self.assertEqual(self.execute().code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.assertFalse(self.quota.mock_calls)
        self.reports.abort.assert_not_called()
        self.work.commit.assert_not_called()

    def test_known_failures_use_authorized_fenced_release_not_finally(self):
        for port in (self.risk.issue, self.flow.load_input, self.flow.executor.prepare,
                     self.reports.put, self.flow.commit):
            original, effect = port.return_value, port.side_effect
            port.return_value, port.side_effect = self.error(), None
            with self.subTest(port=port):
                self.assertEqual(self.execute(), self.error())
                self.reports.abort.assert_called_once_with(self.record.binding)
                self.quota.release.assert_called_once()
                self.quota.reconcile.assert_not_called()
            self.reports.abort.reset_mock()
            self.quota.release.reset_mock()
            port.return_value, port.side_effect = original, effect

    def test_missing_recovery_permission_retains_known_failure_and_capacity(self):
        self.flow.authorize_recovery = None
        self.risk.issue.return_value = self.error()
        self.assertEqual(self.execute(), self.error())
        self.quota.release.assert_not_called()
        self.reports.abort.assert_not_called()

    def test_unknown_preparation_fences_future_delivery_but_keeps_full_hold(self):
        self.flow.executor.prepare.return_value = self.error(ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(self.execute(), self.error(ReasonCode.DELIVERY_UNKNOWN))
        self.reports.abort.assert_called_once_with(self.record.binding)
        self.assertIsNone(self.quota.reconcile.call_args.args[1])
        self.quota.release.assert_not_called()
        self.flow.commit.assert_not_called()

    def test_lost_commit_acknowledgement_never_relabels_an_actual_winner(self):
        self.flow.commit.return_value = self.error(ReasonCode.DELIVERY_UNKNOWN)
        self.reports.abort.return_value = self.receipt
        self.assertEqual(self.execute(), self.error(ReasonCode.DELIVERY_UNKNOWN))
        self.quota.reconcile.assert_not_called()
        self.quota.release.assert_not_called()

    def test_database_unavailable_during_unknown_recording_never_frees_capacity(self):
        self.flow.executor.prepare.side_effect = RuntimeError('synthetic preparation failure')
        self.reports.abort.side_effect = RuntimeError('synthetic database unavailable')
        self.assertEqual(self.execute().code, ReasonCode.DELIVERY_UNKNOWN)
        self.quota.reconcile.assert_not_called()
        self.quota.release.assert_not_called()

    def test_unconfigured_execute_and_context_drift_are_closed(self):
        self.flow.request = None
        self.assertEqual(self.execute().code, ReasonCode.AUTHORIZATION_DENIED)
        self.flow.request = sentinel.owner_request
        wrong = replace(self.owner, object_version='other/version')
        self.assertEqual(self.flow.execute(self.record.plan, self.record.binding, wrong).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        self.reports.begin.assert_not_called()
        self.flow.load_input.assert_not_called()
