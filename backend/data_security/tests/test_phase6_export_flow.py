"""Commit-stage orchestration with explicit test doubles, NOT a v2 ledger test."""
from dataclasses import replace
from datetime import timedelta
from unittest import TestCase
from unittest.mock import MagicMock, Mock, sentinel

from data_security.application.export_flow import ExportFlow
from data_security.application.policy_catalog import PolicyCatalog
from data_security.contracts import (
    AuditReceipt, DeliveryReceipt, Durability, Outcome, PolicySnapshot, ProtectionContext,
    ProtectionError, QuotaReceipt, QuotaState, ReasonCode, ReportRecord, content_hash,
)
from data_security.tests.fixtures import AT, approval, examples


class ExportFlowFixture:
    def setUp(self):
        values = examples()
        policy_values = dict(values[PolicySnapshot].content(), teaching_exceptions=())
        policy_hash = content_hash(policy_values)
        self.policy = replace(values[PolicySnapshot], teaching_exceptions=(), content_hash=policy_hash,
                              approval=approval(policy_hash))
        record = values[ReportRecord]
        policy_binding = replace(record.binding.policy_binding, protection_hash=policy_hash)
        binding = replace(record.binding, policy_binding=policy_binding)
        plan_values = dict(record.plan.content(), policy_binding=policy_binding)
        plan = replace(record.plan, policy_binding=policy_binding, approval=None, plan_hash=content_hash(plan_values))
        context = replace(record.context, authorization_ref=binding.authorization_id,
                          object_version=binding.asset_version)
        self.record = replace(record, plan=plan, binding=binding, context=context,
                              stored=replace(record.stored, state='verified'))
        self.owner = replace(values[ProtectionContext], actor_ref=binding.subject_ref,
            authorization_ref=binding.authorization_id, scope_refs=(context.field_ref,),
            domain=binding.domain_ref, object_ref=context.object_uuid, object_version=context.object_version)
        self.reports = Mock(read=Mock(return_value=self.record), delivery=Mock(return_value=None),
                            lock_delivery=Mock(return_value=None), record_delivery=Mock(side_effect=lambda r: r))
        self.authenticator = Mock(verify=Mock(return_value=True))
        self.store = Mock(verify=Mock(return_value=self.record.stored),
                          publish=Mock(return_value=replace(self.record.stored, state='published')))
        self.risk = Mock(consume=Mock(return_value=sentinel.authorization),
                         recheck_delivered=Mock(return_value=True))
        self.quota = Mock(commit=Mock(side_effect=lambda b, n: QuotaReceipt(schema_version=QuotaReceipt.SCHEMA,
            binding=b, state=QuotaState.COMMITTED, settled_amount=n, observed_at=AT, evidence_ref='quota/test')))
        self.policy_repository = Mock(read=Mock(return_value=self.policy))
        self.policies = PolicyCatalog(repository=self.policy_repository, clock=lambda: AT + timedelta(seconds=1))
        self.authorize = Mock(return_value=self.owner)
        self.audit = Mock(record=Mock(side_effect=lambda e, d: AuditReceipt(schema_version=AuditReceipt.SCHEMA,
            event_id=e.event_id, durability=d, stored_at=e.occurred_at, chain_version='ds.audit.v2',
            entry_ref='test-double/ledger/1', sequence=1, entry_hash='0' * 64, checkpoint_ref=None)))
        self.work = MagicMock()
        self.work.__enter__.return_value = self.work
        self.work.__exit__.return_value = None
        self.uow_factory = Mock(return_value=self.work)
        self.flow = ExportFlow(reports=self.reports, authenticator=self.authenticator, store=self.store,
            risk=self.risk, quota=self.quota, policies=self.policies, authorize=self.authorize,
            audit=self.audit, uow_factory=self.uow_factory, clock=lambda: AT + timedelta(seconds=1))

    def commit(self):
        return self.flow.commit(self.record.plan, self.record.binding, self.record.context)

    def error(self, code=ReasonCode.AUTHORIZATION_DENIED):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='test/commit')


class ExportCommitTests(ExportFlowFixture, TestCase):
    def test_order_and_logical_record_units_not_cells_or_network_acknowledgement(self):
        calls = Mock()
        for name, value in (('verify', self.store.verify), ('lock', self.reports.lock_delivery),
                            ('owner', self.authorize), ('policy', self.policy_repository.read),
                            ('consume', self.risk.consume), ('publish', self.store.publish),
                            ('quota', self.quota.commit), ('audit', self.audit.record),
                            ('recheck', self.risk.recheck_delivered),
                            ('receipt', self.reports.record_delivery), ('commit', self.work.commit)):
            calls.attach_mock(value, name)
        result = self.commit()
        self.assertIsInstance(result, DeliveryReceipt)
        self.assertEqual(result.delivered_records, 1)  # Two source rows, one header.
        self.assertEqual([c[0] for c in calls.mock_calls],
                         ['verify', 'lock', 'owner', 'policy', 'consume', 'publish', 'quota', 'audit',
                          'owner', 'policy', 'recheck', 'receipt', 'commit'])
        self.quota.reserve.assert_not_called()
        self.quota.release.assert_not_called()
        event = self.audit.record.call_args.args[0]
        self.assertEqual(event.counts, (('records', 1),))
        self.assertEqual(event.schema_version, 'ds.security-event.v2')
        self.assertEqual(event.evidence_hashes, (('ciphertext', self.record.stored.ciphertext_hash),
                                               ('report', content_hash(self.record.report))))

    def test_replay_is_internal_status_only_no_publish_settlement_or_fresh_grant(self):
        first = self.commit()
        self.assertIsInstance(first, DeliveryReceipt)
        self.reports.delivery.return_value = first
        self.flow.clock = lambda: self.record.binding.expires_at
        self.store.reset_mock()
        self.quota.reset_mock()
        self.risk.reset_mock()
        self.authorize.reset_mock()
        self.assertEqual(self.commit(), first)
        self.assertFalse(self.store.mock_calls or self.quota.mock_calls or self.risk.mock_calls)
        self.authorize.assert_not_called()

    def test_competing_commit_observes_winner_after_report_lock(self):
        first = self.commit()
        self.reports.lock_delivery.return_value = first
        self.quota.reset_mock()
        self.store.publish.reset_mock()
        self.risk.reset_mock()
        self.assertEqual(self.commit(), first)
        self.quota.commit.assert_not_called()
        self.store.publish.assert_not_called()
        self.risk.consume.assert_not_called()

    def test_missing_report_owner_binding_drift_and_failed_proof_cannot_publish(self):
        for value in (None, replace(self.record, context=replace(self.record.context, field_ref='other/field'))):
            self.reports.read.return_value = value
            self.assertEqual(self.commit().code, ReasonCode.REPORT_MISMATCH)
        self.reports.read.return_value = self.record
        self.authenticator.verify.return_value = self.error(ReasonCode.REPORT_MISMATCH)
        self.assertEqual(self.commit().code, ReasonCode.REPORT_MISMATCH)
        self.store.publish.assert_not_called()
        self.work.commit.assert_not_called()

    def test_each_port_failure_returns_error_without_commit_or_release(self):
        ports = (self.reports.read, self.reports.delivery, self.authenticator.verify, self.store.verify,
                 self.reports.lock_delivery, self.authorize, self.policy_repository.read, self.risk.consume,
                 self.store.publish, self.quota.commit, self.audit.record, self.risk.recheck_delivered,
                 self.reports.record_delivery)
        for port in ports:
            original, effect = port.return_value, port.side_effect
            port.side_effect, port.return_value = None, self.error()
            with self.subTest(port=ports.index(port)):
                self.assertEqual(self.commit(), self.error())
                self.work.commit.assert_not_called()
                self.quota.release.assert_not_called()
            port.return_value, port.side_effect = original, effect

    def test_expiry_is_checked_after_wait_not_only_before_file_authentication(self):
        self.reports.lock_delivery.side_effect = lambda *args: setattr(
            self.flow, 'clock', lambda: self.record.binding.expires_at)
        self.assertEqual(self.commit().code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.store.publish.assert_not_called()
        self.risk.consume.assert_not_called()

    def test_expiry_during_publish_quota_or_final_audit_wait_prevents_receipt(self):
        for port in (self.store.publish, self.quota.commit, self.audit.record):
            self.flow.clock = lambda: AT + timedelta(seconds=1)
            original, effect = port.return_value, port.side_effect

            def expire(*args):
                self.flow.clock = lambda: self.record.binding.expires_at
                return effect(*args) if effect is not None else original

            port.side_effect = expire
            with self.subTest(port=port):
                self.assertEqual(self.commit().code, ReasonCode.AUTHORIZATION_EXPIRED)
                self.reports.record_delivery.assert_not_called()
                self.work.commit.assert_not_called()
                self.quota.release.assert_not_called()
            port.return_value, port.side_effect = original, effect

    def test_current_owner_and_policy_are_reloaded_after_final_audit_wait(self):
        produce = self.audit.record.side_effect
        for port, value, code in (
            (self.authorize, self.error(), ReasonCode.AUTHORIZATION_DENIED),
            (self.policy_repository.read, replace(self.policy, status=type(self.policy.status).RETIRED),
             ReasonCode.POLICY_NOT_APPROVED),
        ):
            original = port.return_value

            def withdraw(event, durability):
                receipt = produce(event, durability)
                port.return_value = value
                return receipt

            self.audit.record.side_effect = withdraw
            with self.subTest(port=port):
                self.assertEqual(self.commit().code, code)
                self.reports.record_delivery.assert_not_called()
                self.work.commit.assert_not_called()
                self.quota.release.assert_not_called()
            port.return_value = original
        self.audit.record.side_effect = produce

    def test_current_policy_and_exact_algorithm_parameters_are_required(self):
        self.policy_repository.read.return_value = replace(self.policy, status=type(self.policy.status).RETIRED)
        self.assertEqual(self.commit().code, ReasonCode.POLICY_NOT_APPROVED)
        self.policy_repository.read.return_value = self.policy
        self.authorize.return_value = replace(self.owner, role=type(self.owner.role).STUDENT)
        self.assertEqual(self.commit().code, ReasonCode.POLICY_NOT_APPROVED)
        self.authorize.return_value = replace(self.owner, authorization_ref='other/grant')
        self.assertEqual(self.commit().code, ReasonCode.AUTHORIZATION_DENIED)
        self.store.publish.assert_not_called()

    def test_old_chain_or_outbox_receipt_never_meets_new_ledger_requirement(self):
        produce = self.audit.record.side_effect
        for durability in (Durability.DURABLE, Durability.LEDGER_CONFIRMED):
            def old(event, requested):
                if durability is Durability.DURABLE:
                    return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=event.event_id,
                        durability=durability, stored_at=event.occurred_at, chain_version=None,
                        entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
                return replace(produce(event, requested), chain_version='v1')
            self.audit.record.side_effect = old
            self.assertEqual(self.commit().code, ReasonCode.AUDIT_UNAVAILABLE)
            self.work.commit.assert_not_called()
            self.reports.record_delivery.assert_not_called()

    def test_uow_exit_failure_is_unknown_and_does_not_release_or_republish(self):
        self.work.__exit__.side_effect = RuntimeError('synthetic commit acknowledgement lost')
        self.assertEqual(self.commit().code, ReasonCode.DELIVERY_UNKNOWN)
        self.quota.release.assert_not_called()
        self.store.publish.assert_called_once()
        self.quota.commit.assert_called_once()

    def test_plan_expiry_after_risk_lock_wait_rolls_back_before_publication(self):
        def consume(binding):
            self.flow.clock = lambda: self.record.plan.expires_at
            return sentinel.authorization
        self.risk.consume.side_effect = consume
        self.assertEqual(self.commit().code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.store.publish.assert_not_called()
        self.work.commit.assert_not_called()

    def test_quantity_overrun_is_denied_before_lock_and_settlement(self):
        scope = self.record.plan.scope
        scope = replace(scope, sheets=(replace(scope.sheets[0], row_ranges=((1, 12),)),))
        fields = dict(self.record.plan.content(), scope=scope)
        plan = replace(self.record.plan, scope=scope, plan_hash=content_hash(fields))
        self.record = replace(self.record, plan=plan, binding=replace(self.record.binding, scope=scope))
        self.reports.read.return_value = self.record
        self.assertEqual(self.commit().code, ReasonCode.LIMIT_EXCEEDED)
        self.reports.lock_delivery.assert_not_called()
        self.quota.commit.assert_not_called()
