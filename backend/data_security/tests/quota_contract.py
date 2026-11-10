"""One behavioral contract, inherited unchanged by memory and PostgreSQL tests."""
from dataclasses import replace
from datetime import timedelta

from data_security.contracts import (
    ExecutionBinding, ProtectionError, QuotaPort, QuotaReceipt, QuotaState, ReasonCode, content_hash,
)
from data_security.tests.fixtures import AT, examples


class QuotaContract:
    def setUp(self):
        super().setUp()
        self.now = AT
        self.binding = replace(examples()[ExecutionBinding], expires_at=AT + timedelta(minutes=10))
        self.port: QuotaPort = self.make_port()

    def assert_error(self, result, code, binding=None):
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, code)
        self.assertFalse(result.retryable)
        self.assertEqual(result.trace_id, (binding or self.binding).execution_id)

    def assert_receipt(self, receipt, state, *, delivered=None, evidence=None, binding=None):
        self.assertIs(type(receipt), QuotaReceipt)
        self.assertEqual(receipt.binding, binding or self.binding)
        self.assertEqual(receipt.state, state)
        self.assertEqual(receipt.settled_amount, delivered)
        self.assertEqual(receipt.held_amount, receipt.binding.quantity
                         if state in (QuotaState.RESERVED, QuotaState.UNKNOWN) else 0)
        self.assertEqual(receipt.observed_at, self.now)
        if evidence is not None:
            self.assertEqual(receipt.evidence_ref, evidence)
        self.assertEqual(QuotaReceipt.from_wire(receipt.to_wire()), receipt)

    def test_protocol_reserve_and_reopen_do_not_double_hold_or_extend_ttl(self):
        for name in ('reserve', 'require_active', 'commit', 'release', 'reconcile'):
            self.assertTrue(callable(getattr(self.port, name)))
        first = self.port.reserve(self.binding)
        self.assert_receipt(first, QuotaState.RESERVED)
        self.now += timedelta(seconds=10)
        reopened = self.make_port()
        replay = reopened.reserve(self.binding)
        self.assert_receipt(replay, QuotaState.RESERVED)
        self.assertEqual(first.evidence_ref, replay.evidence_ref)
        self.assert_receipt(reopened.require_active(self.binding), QuotaState.RESERVED)
        self.assertEqual(reopened.active_until(self.binding), AT + timedelta(seconds=300))
        self.assertEqual(self.balances(), (10, 0, 0))

    def test_all_operations_reject_missing_and_cross_environment_bindings(self):
        for binding, code in ((self.binding, ReasonCode.AUTHORIZATION_DENIED),
                              (replace(self.binding, environment='evaluation'), ReasonCode.SOURCE_NOT_APPROVED)):
            for name, args in (('require_active', ()), ('active_until', ()), ('commit', (7,)),
                               ('release', ('proof/none',)), ('reconcile', (None, 'proof/unknown'))):
                with self.subTest(operation=name, environment=binding.environment):
                    self.assert_error(getattr(self.port, name)(binding, *args), code, binding)
        self.assert_error(self.port.reserve(replace(self.binding, environment='evaluation')),
                          ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.balances(), (0, 0, 0))

    def test_complete_binding_and_port_configuration_are_immutable(self):
        self.port.reserve(self.binding)
        changes = ({'request_id': 'request/other'}, {'request_fingerprint': '1' * 64},
                   {'authorization_id': 'authorization/other'}, {'decision_id': 'decision/other'},
                   {'asset_version': 'asset/other'}, {'execution_id': 'execution/other'},
                   {'reservation_id': 'reservation/other'}, {'subject_ref': 'actor/other'},
                   {'domain_ref': 'domain/other'}, {'quantity': 9},
                   {'expires_at': self.binding.expires_at + timedelta(seconds=1)},
                   {'policy_binding': replace(self.binding.policy_binding, risk_hash='2' * 64)},
                   {'scope': replace(self.binding.scope, sheets=(replace(
                       self.binding.scope.sheets[0], row_ranges=((1, 1),)),))})
        for change in changes:
            binding = replace(self.binding, **change)
            with self.subTest(field=next(iter(change))):
                self.assert_error(self.port.require_active(binding), ReasonCode.IDEMPOTENCY_CONFLICT, binding)
        for config in ({'window_key': 'window/other'}, {'limit': 20}, {'ttl_seconds': 301}):
            with self.subTest(config=config):
                self.assert_error(self.make_port(**config).reserve(self.binding), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.balances(), (10, 0, 0))

    def test_reservation_identity_cannot_be_adopted_by_another_idempotency_key(self):
        self.port.reserve(self.binding)
        other = replace(self.binding, idempotency_key='other/key')
        self.assert_error(self.port.reserve(other), ReasonCode.IDEMPOTENCY_CONFLICT, other)
        self.assert_error(self.port.require_active(other), ReasonCode.AUTHORIZATION_DENIED, other)
        self.assertEqual(self.balances(), (10, 0, 0))

    def test_limit_denial_leaves_no_hold_and_does_not_pin_configuration(self):
        self.assert_error(self.make_port(limit=9).reserve(self.binding), ReasonCode.LIMIT_EXCEEDED)
        self.assertEqual(self.balances(), (0, 0, 0))
        self.assert_receipt(self.port.reserve(self.binding), QuotaState.RESERVED)
        self.assertEqual(self.balances(), (10, 0, 0))

    def test_binding_expiry_is_exclusive_and_does_not_free_capacity(self):
        self.binding = replace(self.binding, expires_at=AT + timedelta(seconds=30))
        self.port.reserve(self.binding)
        self.assertEqual(self.port.active_until(self.binding), self.binding.expires_at)
        self.now = self.binding.expires_at
        for name, args in (('reserve', ()), ('require_active', ()), ('active_until', ()), ('commit', (7,))):
            with self.subTest(operation=name):
                self.assert_error(getattr(self.port, name)(self.binding, *args), ReasonCode.AUTHORIZATION_EXPIRED)
        self.assertEqual(self.balances(), (10, 0, 0))
        self.assert_receipt(self.port.release(self.binding, 'proof/expired-no-delivery'), QuotaState.RELEASED,
                            evidence='proof/expired-no-delivery')
        self.assertEqual(self.balances(), (0, 0, 0))

    def test_hold_ttl_is_exclusive_and_does_not_free_capacity(self):
        self.port = self.make_port(ttl_seconds=30)
        self.port.reserve(self.binding)
        self.assertEqual(self.port.active_until(self.binding), AT + timedelta(seconds=30))
        self.now += timedelta(seconds=30)
        for name, args in (('reserve', ()), ('require_active', ()), ('active_until', ()), ('commit', (7,))):
            with self.subTest(operation=name):
                self.assert_error(getattr(self.port, name)(self.binding, *args), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.balances(), (10, 0, 0))

    def test_expired_first_reserve_does_not_create_state(self):
        self.now = self.binding.expires_at
        self.assert_error(self.port.reserve(self.binding), ReasonCode.AUTHORIZATION_EXPIRED)
        self.assert_error(self.port.require_active(self.binding), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.balances(), (0, 0, 0))

    def test_commit_has_bound_receipt_and_exact_terminal_replay_after_expiry(self):
        self.port.reserve(self.binding)
        bound = content_hash({'binding': self.binding, 'window': 'window/1', 'limit': 10, 'ttl_seconds': 300})
        evidence = 'quota/' + content_hash({'binding': bound, 'operation': 'commit', 'delivered': 7})
        receipt = self.port.commit(self.binding, 7)
        self.assert_receipt(receipt, QuotaState.COMMITTED, delivered=7, evidence=evidence)
        self.now = self.binding.expires_at
        reopened = self.make_port()
        self.assertEqual(reopened.commit(self.binding, 7), receipt)
        for name, args in (('commit', (8,)), ('require_active', ()), ('active_until', ()),
                           ('release', ('proof/none',)), ('reconcile', (7, evidence))):
            with self.subTest(operation=name):
                self.assert_error(getattr(reopened, name)(self.binding, *args), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.balances(), (0, 0, 7))

    def test_invalid_amounts_and_evidence_do_not_mutate_hold(self):
        self.port.reserve(self.binding)
        for amount in (True, -1, 11, 1.5, None):
            with self.subTest(amount=amount):
                self.assert_error(self.port.commit(self.binding, amount), ReasonCode.INVALID_VALUE)
                if amount is not None:
                    self.assert_error(self.port.reconcile(self.binding, amount, 'proof/confirmed'),
                                      ReasonCode.INVALID_VALUE)
        for evidence in ('', '../invalid', '/tmp/invalid', None):
            with self.subTest(evidence=evidence):
                self.assert_error(self.port.release(self.binding, evidence), ReasonCode.INVALID_VALUE)
                self.assert_error(self.port.reconcile(self.binding, None, evidence), ReasonCode.INVALID_VALUE)
        self.assertEqual(self.balances(), (10, 0, 0))
        self.assert_receipt(self.port.require_active(self.binding), QuotaState.RESERVED)

    def test_release_replays_original_receipt_not_new_evidence_or_operation(self):
        self.port.reserve(self.binding)
        receipt = self.port.release(self.binding, 'proof/no-delivery')
        self.assert_receipt(receipt, QuotaState.RELEASED, evidence='proof/no-delivery')
        self.now += timedelta(seconds=1)
        reopened = self.make_port()
        self.assertEqual(reopened.release(self.binding, 'proof/no-delivery'), receipt)
        for name, args in (('release', ('proof/other',)), ('commit', (0,)),
                           ('reconcile', (0, 'proof/no-delivery')), ('require_active', ())):
            with self.subTest(operation=name):
                self.assert_error(getattr(reopened, name)(self.binding, *args), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.balances(), (0, 0, 0))

    def test_unknown_replay_retains_full_capacity_and_requires_exact_reconciliation(self):
        self.port.reserve(self.binding)
        unknown = self.port.reconcile(self.binding, None, 'proof/unknown')
        self.assert_receipt(unknown, QuotaState.UNKNOWN, evidence='proof/unknown')
        self.now = self.binding.expires_at
        reopened = self.make_port()
        self.assertEqual(reopened.reconcile(self.binding, None, 'proof/unknown'), unknown)
        self.assert_error(reopened.reconcile(self.binding, None, 'proof/changed'), ReasonCode.IDEMPOTENCY_CONFLICT)
        for name, args in (('release', ('proof/none',)), ('commit', (7,)),
                           ('require_active', ()), ('active_until', ())):
            with self.subTest(operation=name):
                self.assert_error(getattr(reopened, name)(self.binding, *args), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.balances(), (0, 10, 0))
        receipt = reopened.reconcile(self.binding, 7, 'proof/confirmed')
        self.assert_receipt(receipt, QuotaState.COMMITTED, delivered=7, evidence='proof/confirmed')
        self.now += timedelta(seconds=1)
        self.assertEqual(self.make_port().reconcile(self.binding, 7, 'proof/confirmed'), receipt)
        self.assert_error(reopened.reconcile(self.binding, 8, 'proof/confirmed'), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assert_error(reopened.reconcile(self.binding, 7, 'proof/changed'), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assert_error(reopened.commit(self.binding, 7), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.balances(), (0, 0, 7))

    def test_unknown_blocks_other_requests_until_zero_delivery_is_confirmed(self):
        self.port.reserve(self.binding)
        self.port.reconcile(self.binding, None, 'proof/unknown')
        other = replace(self.binding, idempotency_key='idempotency/2', reservation_id='reservation/2',
                        execution_id='execution/2', request_id='request/2', request_fingerprint='1' * 64)
        self.assert_error(self.port.reserve(other), ReasonCode.LIMIT_EXCEEDED, other)
        self.assertEqual(self.balances(), (0, 10, 0))
        self.assert_receipt(self.port.reconcile(self.binding, 0, 'proof/zero'),
                            QuotaState.COMMITTED, delivered=0, evidence='proof/zero')
        self.assert_receipt(self.port.reserve(other), QuotaState.RESERVED, binding=other)
        self.assertEqual(self.balances(), (10, 0, 0))

    def test_settled_quantity_stays_charged_while_unused_hold_is_returned(self):
        self.port.reserve(self.binding)
        self.port.commit(self.binding, 7)
        other = replace(self.binding, idempotency_key='idempotency/2', reservation_id='reservation/2',
                        execution_id='execution/2', quantity=4)
        self.assert_error(self.port.reserve(other), ReasonCode.LIMIT_EXCEEDED, other)
        other = replace(other, quantity=3)
        self.assert_receipt(self.port.reserve(other), QuotaState.RESERVED, binding=other)
        self.assertEqual(self.balances(), (3, 0, 7))
        self.assert_receipt(self.port.reconcile(other, 2, 'proof/direct'), QuotaState.COMMITTED,
                            delivered=2, evidence='proof/direct', binding=other)
        self.assertEqual(self.balances(), (0, 0, 9))

    def test_read_committed_rejects_missing_and_cross_environment_bindings(self):
        self.assertTrue(callable(QuotaPort.read_committed))
        before = self.quota_snapshot()
        for binding, code in ((self.binding, ReasonCode.AUTHORIZATION_DENIED),
                              (replace(self.binding, environment='evaluation'), ReasonCode.SOURCE_NOT_APPROVED),
                              (replace(self.binding, environment='production'), ReasonCode.SOURCE_NOT_APPROVED)):
            with self.subTest(environment=binding.environment):
                self.assert_error(self.port.read_committed(binding), code, binding)
                self.assertEqual(self.quota_snapshot(), before)
        self.assertEqual(self.balances(), (0, 0, 0))

    def test_read_committed_rejects_reserved_and_unknown_without_mutation(self):
        self.port.reserve(self.binding)
        for state, balances in ((QuotaState.RESERVED, (10, 0, 0)), (QuotaState.UNKNOWN, (0, 10, 0))):
            if state is QuotaState.UNKNOWN:
                self.port.reconcile(self.binding, None, 'proof/unknown')
            before = self.quota_snapshot()
            for elapsed in (timedelta(seconds=1), timedelta(days=1)):
                self.now += elapsed
                with self.subTest(state=state, elapsed=elapsed):
                    self.assert_error(self.make_port().read_committed(self.binding), ReasonCode.AUTHORIZATION_DENIED)
                    self.assertEqual(self.quota_snapshot(), before)
                    self.assertEqual(self.balances(), balances)

    def test_read_committed_rejects_released_without_mutation(self):
        self.port.reserve(self.binding)
        self.port.release(self.binding, 'proof/no-delivery')
        before = self.quota_snapshot()
        self.now = self.binding.expires_at + timedelta(days=1)
        self.assert_error(self.make_port().read_committed(self.binding), ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.quota_snapshot(), before)
        self.assertEqual(self.balances(), (0, 0, 0))

    def test_read_committed_replays_original_receipt_without_mutation(self):
        self.port.reserve(self.binding)
        receipt = self.port.commit(self.binding, 7)
        self.assert_receipt(receipt, QuotaState.COMMITTED, delivered=7)
        before = self.quota_snapshot()
        self.now += timedelta(seconds=10)
        for port in (self.port, self.make_port()):
            observed = port.read_committed(self.binding)
            self.assertEqual(observed, receipt)
            self.assertEqual(observed.to_wire(), receipt.to_wire())
            self.assertEqual(self.quota_snapshot(), before)
        self.assertEqual(self.balances(), (0, 0, 7))

    def test_read_committed_rejects_full_binding_and_port_configuration_conflicts(self):
        self.port.reserve(self.binding)
        receipt = self.port.commit(self.binding, 7)
        before = self.quota_snapshot()
        changes = ({'request_id': 'request/other'}, {'request_fingerprint': '1' * 64},
                   {'authorization_id': 'authorization/other'}, {'decision_id': 'decision/other'},
                   {'asset_version': 'asset/other'}, {'execution_id': 'execution/other'},
                   {'reservation_id': 'reservation/other'}, {'subject_ref': 'actor/other'},
                   {'domain_ref': 'domain/other'}, {'quantity': 9},
                   {'expires_at': self.binding.expires_at + timedelta(seconds=1)},
                   {'policy_binding': replace(self.binding.policy_binding, risk_hash='2' * 64)},
                   {'scope': replace(self.binding.scope, sheets=(replace(
                       self.binding.scope.sheets[0], row_ranges=((1, 1),)),))})
        for change in changes:
            binding = replace(self.binding, **change)
            with self.subTest(field=next(iter(change))):
                self.assert_error(self.port.read_committed(binding), ReasonCode.IDEMPOTENCY_CONFLICT, binding)
        other = replace(self.binding, idempotency_key='other/key')
        self.assert_error(self.port.read_committed(other), ReasonCode.AUTHORIZATION_DENIED, other)
        other = replace(self.binding, environment='evaluation')
        self.assert_error(self.port.read_committed(other), ReasonCode.SOURCE_NOT_APPROVED, other)
        self.assert_error(self.make_port(environment='evaluation').read_committed(other),
                          ReasonCode.IDEMPOTENCY_CONFLICT, other)
        for config in ({'window_key': 'window/other'}, {'limit': 20}, {'ttl_seconds': 301}):
            with self.subTest(config=config):
                self.assert_error(self.make_port(**config).read_committed(self.binding),
                                  ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.quota_snapshot(), before)
        self.assertEqual(self.port.read_committed(self.binding), receipt)
        self.assertEqual(self.balances(), (0, 0, 7))

    def test_read_committed_retains_receipt_after_binding_and_hold_expiry(self):
        self.binding = replace(self.binding, expires_at=AT + timedelta(seconds=60))
        self.port = self.make_port(ttl_seconds=30)
        self.port.reserve(self.binding)
        receipt = self.port.commit(self.binding, 7)
        before = self.quota_snapshot()
        for at in (AT + timedelta(seconds=30), self.binding.expires_at,
                   self.binding.expires_at + timedelta(days=1)):
            self.now = at
            with self.subTest(at=at):
                self.assertEqual(self.make_port(ttl_seconds=30).read_committed(self.binding), receipt)
                self.assertEqual(self.quota_snapshot(), before)
        self.assertEqual(self.balances(), (0, 0, 7))

    def test_read_committed_preserves_reconciliation_evidence_including_zero(self):
        for amount in (0, 7):
            with self.subTest(delivered=amount):
                binding = replace(self.binding, idempotency_key=f'idempotency/reconcile-{amount}',
                                  reservation_id=f'reservation/reconcile-{amount}',
                                  expires_at=self.now + timedelta(minutes=10))
                self.port.reserve(binding)
                self.port.reconcile(binding, None, 'proof/unknown')
                self.now = binding.expires_at
                evidence = f'proof/confirmed-{amount}'
                receipt = self.port.reconcile(binding, amount, evidence)
                self.assert_receipt(receipt, QuotaState.COMMITTED, delivered=amount,
                                    evidence=evidence, binding=binding)
                before = self.quota_snapshot()
                self.now += timedelta(days=1)
                self.assertEqual(self.make_port().read_committed(binding), receipt)
                self.assertEqual(self.quota_snapshot(), before)
        self.assertEqual(self.balances(), (0, 0, 7))

    def test_read_committed_rejects_missing_or_inconsistent_terminal_receipts(self):
        self.port.reserve(self.binding)
        receipt = self.port.commit(self.binding, 7)
        mismatched = replace(receipt, binding=replace(self.binding, request_id='request/other'))
        for changes, code in (
                ({'terminal_receipt': None}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'terminal_receipt': []}, ReasonCode.INVALID_TYPE),
                ({'terminal_receipt': {}}, ReasonCode.MISSING_FIELD),
                ({'terminal_receipt': mismatched.to_wire()}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'terminal_receipt': replace(receipt, state=QuotaState.RESERVED,
                                             settled_amount=None).to_wire()}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'terminal_receipt': replace(receipt, settled_amount=8).to_wire()}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'terminal_receipt': dict(receipt.to_wire(), settled_amount=11)}, ReasonCode.INVALID_VALUE),
                ({'terminal_receipt': replace(receipt, evidence_ref='proof/other').to_wire()},
                 ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'terminal_receipt': dict(receipt.to_wire(), evidence_ref='')}, ReasonCode.INVALID_VALUE),
                ({'terminal_operation': ''}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'terminal_operation': 'release'}, ReasonCode.IDEMPOTENCY_CONFLICT)):
            with self.subTest(changes=changes):
                self.set_terminal(terminal_operation='commit', terminal_receipt=receipt.to_wire())
                self.set_terminal(**changes)
                before = self.quota_snapshot()
                self.assert_error(self.make_port().read_committed(self.binding), code)
                self.assertEqual(self.quota_snapshot(), before)
                self.assertEqual(self.balances(), (0, 0, 7))
        self.set_terminal(terminal_operation='commit', terminal_receipt=receipt.to_wire())
        self.assertEqual(self.port.read_committed(self.binding), receipt)
