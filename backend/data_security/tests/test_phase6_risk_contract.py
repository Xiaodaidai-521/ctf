"""Run the shared cases with independent stateful risk/quota test implementations."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from unittest import TestCase

from data_security.tests.quota_memory import MemoryQuotaPort
from data_security.tests.risk_contract import RiskContract
from data_security.tests.risk_memory import MemoryRiskPort


class MemoryRiskContractTests(RiskContract, TestCase):
    def setUp(self):
        self.decisions, self.authorizations, self.issue_keys, self.events = {}, {}, {}, []
        self.quota_records, self.bucket_limits, self.in_work = {}, {}, False
        super().setUp()

    def make_port(self, **changes):
        return MemoryRiskPort(decisions=self.decisions, authorizations=self.authorizations,
            issue_keys=self.issue_keys, events=self.events, clock=lambda: self.now,
            in_work=lambda: self.in_work, **self.port_options(changes))

    def make_quota(self, **changes):
        options = dict(environment='test', window_key='risk-contract', limit=10, ttl_seconds=300)
        options.update(changes)
        return MemoryQuotaPort(records=self.quota_records, bucket_limits=self.bucket_limits,
                               clock=lambda: self.now, **options)

    def resources(self):
        return (len(self.decisions), len(self.authorizations), self.events.count('decision.issued'),
                self.events.count('execution.authorized'))

    def balances(self):
        receipts = [r['receipt'] for r in self.quota_records.values()]
        return (len(receipts), sum(r.held_amount for r in receipts if r.state.value == 'reserved'),
                sum(r.held_amount for r in receipts if r.state.value == 'unknown'),
                sum(r.settled_amount or 0 for r in receipts))

    def decision_state(self):
        decision, = self.decisions.values()
        return dict(id=decision['id'], expires_at=decision['expires_at'])

    def execution_state(self):
        auth, = self.authorizations.values()
        return auth['state']

    def set_execution_state(self, state):
        auth, = self.authorizations.values()
        auth['state'] = state

    def invalidate_decision(self):
        decision, = self.decisions.values()
        decision['status'] = 'invalidated'

    def test_delivered_recheck_does_not_change_any_memory_records(self):
        self.consume_and_commit()
        self.grant = replace(self.grant, valid_until=(self.now + timedelta(seconds=40)).isoformat())
        records = (self.decisions, self.authorizations, self.issue_keys, self.events,
                   self.quota_records, self.bucket_limits)
        # Risk DTOs are immutable; copy their mutable owner containers, not their frozen mappings.
        original = ({key: dict(value) for key, value in self.decisions.items()},
                    {key: dict(value) for key, value in self.authorizations.items()},
                    dict(self.issue_keys), list(self.events),
                    *deepcopy((self.quota_records, self.bucket_limits)))
        rebuilt = self.make_port()
        self.assertIs(rebuilt.recheck_delivered(self.binding), True)
        self.assertIs(rebuilt.recheck_delivered(self.binding), True)
        self.assertEqual(records, original)

    @contextmanager
    def work(self):
        # Only an explicit scope marker, not an emulated transactional rollback.
        self.in_work = True
        try:
            yield
        finally:
            self.in_work = False
