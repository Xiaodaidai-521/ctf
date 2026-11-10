"""Stateful test quota under the same contract as the real PostgreSQL adapter."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock

from data_security.contracts import DeliveryReceipt, QuotaState, ReasonCode
from data_security.tests.quota_contract import QuotaContract
from data_security.tests.quota_memory import MemoryQuotaPort
from data_security.tests.test_phase6_export_flow import ExportFlowFixture


class MemoryQuotaContractTests(QuotaContract, TestCase):
    def setUp(self):
        self.records, self.bucket_limits = {}, {}
        super().setUp()

    def make_port(self, **changes):
        config = dict(environment='test', window_key='window/1', limit=10, ttl_seconds=300)
        config.update(changes)
        return MemoryQuotaPort(records=self.records, bucket_limits=self.bucket_limits,
                               clock=lambda: self.now, **config)

    def balances(self):
        receipts = [r['receipt'] for r in self.records.values()]
        return (sum(r.held_amount for r in receipts if r.state is QuotaState.RESERVED),
                sum(r.held_amount for r in receipts if r.state is QuotaState.UNKNOWN),
                sum(r.settled_amount or 0 for r in receipts))

    def quota_snapshot(self):
        return deepcopy((self.records, self.bucket_limits))

    def set_terminal(self, **changes):
        self.records[self.binding.idempotency_key].update(changes)


class StatefulQuotaExportTests(ExportFlowFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.records = {}
        self.memory = MemoryQuotaPort(records=self.records, bucket_limits={}, clock=self.flow.clock,
            environment='test', window_key='window/1', limit=self.record.binding.quantity)
        self.flow.quota = Mock(wraps=self.memory)

    def test_commit_settles_real_test_hold_and_replay_does_not_call_quota(self):
        binding = self.record.binding
        self.memory.reserve(binding)
        receipt = self.commit()
        self.assertIs(type(receipt), DeliveryReceipt)
        quota = self.records[binding.idempotency_key]['receipt']
        self.assertEqual(quota.state, QuotaState.COMMITTED)
        self.assertEqual(quota.settled_amount, receipt.delivered_records)
        self.assertEqual(quota.held_amount, 0)
        self.reports.delivery.return_value = receipt
        self.flow.quota.reset_mock()
        self.assertEqual(self.commit(), receipt)
        self.assertFalse(self.flow.quota.mock_calls)
        self.assertEqual(self.records[binding.idempotency_key]['receipt'], quota)

    def test_missing_hold_cannot_be_fabricated_by_commit_stage(self):
        self.assertEqual(self.commit().code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.records, {})
        self.reports.record_delivery.assert_not_called()
        self.work.commit.assert_not_called()
        self.audit.record.assert_not_called()
        self.flow.quota.reserve.assert_not_called()
        self.flow.quota.release.assert_not_called()
