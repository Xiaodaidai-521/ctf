"""Isolated PostgreSQL checks for the M6 quota binding and short UoW."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.db import DatabaseError, connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from data_security.adapters.persistence.models import QuotaExecution
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import ExecutionBinding, ProtectionError, QuotaState, ReasonCode
from data_security.tests.fixtures import examples
from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService


class QuotaFixture:
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        self.binding = replace(examples()[ExecutionBinding], expires_at=timezone.now() + timedelta(minutes=5))
        self.port = DjangoQuotaPort(environment='test', window_key='window/1', limit=10)

    def held(self):
        bucket = QuotaBucket.objects.get()
        return bucket.active_reserved, bucket.unknown_reserved, bucket.settled


class QuotaPortTests(QuotaFixture, TestCase):
    def test_risk_deadline_uses_the_shorter_authoritative_hold(self):
        self.port = DjangoQuotaPort(environment='test', window_key='window/1', limit=10, ttl_seconds=30)
        self.port.reserve(self.binding)
        expiry = QuotaReservation.objects.get().expires_at
        self.assertLess(expiry, self.binding.expires_at)
        with patch.object(QuotaService, 'reserve', side_effect=AssertionError('second reserve')), \
                patch.object(QuotaService, 'require_active', wraps=QuotaService.require_active) as active:
            self.assertEqual(self.port.active_until(self.binding), expiry)
            active.assert_called_once()
        with patch('django.utils.timezone.now', return_value=expiry):
            self.assertIsInstance(self.port.active_until(self.binding), ProtectionError)
        self.assertEqual(self.held(), (10, 0, 0))

    def test_risk_deadline_never_extends_binding_or_accepts_changed_binding(self):
        self.binding = replace(self.binding, expires_at=timezone.now() + timedelta(seconds=30))
        self.port.reserve(self.binding)
        self.assertGreater(QuotaReservation.objects.get().expires_at, self.binding.expires_at)
        self.assertEqual(self.port.active_until(self.binding), self.binding.expires_at)
        for changes in ({'execution_id': 'other/execution'}, {'scope': replace(self.binding.scope,
                        sheets=(replace(self.binding.scope.sheets[0], row_ranges=((1, 1),)),))}):
            self.assertEqual(self.port.active_until(replace(self.binding, **changes)).code,
                             ReasonCode.IDEMPOTENCY_CONFLICT)
        with patch('django.utils.timezone.now', return_value=self.binding.expires_at):
            self.assertEqual(self.port.active_until(self.binding).code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.assertEqual(self.held(), (10, 0, 0))

    def test_risk_deadline_denies_missing_unknown_and_settled_hold(self):
        self.assertIsInstance(self.port.active_until(self.binding), ProtectionError)
        self.port.reserve(self.binding)
        self.port.reconcile(self.binding, None, 'proof/unknown')
        self.assertIsInstance(self.port.active_until(self.binding), ProtectionError)
        self.assertEqual(self.held(), (0, 10, 0))
        self.port.reconcile(self.binding, 7, 'proof/confirmed')
        self.assertIsInstance(self.port.active_until(self.binding), ProtectionError)
        self.assertEqual(self.held(), (0, 0, 7))

    def test_reserve_replay_and_require_active_do_not_double_hold(self):
        first = self.port.reserve(self.binding)
        second = self.port.reserve(self.binding)
        self.assertEqual(first.state, QuotaState.RESERVED)
        self.assertEqual(first.binding, second.binding)
        self.assertEqual(self.port.require_active(self.binding).held_amount, 10)
        self.assertEqual(QuotaExecution.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(self.held(), (10, 0, 0))

    def test_full_binding_and_configuration_are_immutable(self):
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
            with self.subTest(field=next(iter(change))):
                result = self.port.require_active(replace(self.binding, **change))
                self.assertEqual(result.code, ReasonCode.IDEMPOTENCY_CONFLICT)
        changed_port = DjangoQuotaPort(environment='test', window_key='window/other', limit=20)
        self.assertEqual(changed_port.reserve(self.binding).code, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.held(), (10, 0, 0))

    def test_changed_idempotency_key_cannot_adopt_existing_reservation(self):
        self.port.reserve(self.binding)
        result = self.port.reserve(replace(self.binding, idempotency_key='other/key'))
        self.assertEqual(result.code, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(QuotaExecution.objects.count(), 1)
        self.assertEqual(self.held(), (10, 0, 0))

    def test_unbound_legacy_hold_cannot_be_adopted(self):
        QuotaService.reserve(subject_id=self.binding.subject_ref, data_domain=self.binding.domain_ref,
            window_key='window/1', amount=10, request_fingerprint=self.binding.request_fingerprint,
            reservation_id=self.binding.reservation_id, limit=10)
        self.assertEqual(self.port.reserve(self.binding).code, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertFalse(QuotaExecution.objects.exists())
        self.assertEqual(self.held(), (10, 0, 0))

    def test_limit_denial_rolls_back_binding_record(self):
        port = DjangoQuotaPort(environment='test', window_key='window/1', limit=9)
        self.assertEqual(port.reserve(self.binding).code, ReasonCode.LIMIT_EXCEEDED)
        self.assertFalse(QuotaExecution.objects.exists())
        self.assertFalse(QuotaReservation.objects.exists())

    def test_missing_and_cross_environment_binding_deny(self):
        self.assertIsInstance(self.port.require_active(self.binding), ProtectionError)
        self.assertEqual(self.port.reserve(replace(self.binding, environment='evaluation')).code,
                         ReasonCode.SOURCE_NOT_APPROVED)
        self.assertFalse(QuotaExecution.objects.exists())

    def test_commit_is_idempotent_and_original_service_is_the_writer(self):
        self.port.reserve(self.binding)
        with patch.object(QuotaService, 'commit', wraps=QuotaService.commit) as commit:
            receipt = self.port.commit(self.binding, 7)
            self.assertEqual(self.port.commit(self.binding, 7), receipt)
            commit.assert_called_once_with(reservation_id=self.binding.reservation_id, delivered_amount=7)
        self.assertEqual(receipt.state, QuotaState.COMMITTED)
        self.assertEqual(self.held(), (0, 0, 7))
        self.assertEqual(self.port.commit(self.binding, 8).code, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertIsInstance(self.port.reserve(self.binding), ProtectionError)
        self.assertIsInstance(self.port.require_active(self.binding), ProtectionError)

    def test_invalid_amounts_never_reach_original_writer(self):
        self.port.reserve(self.binding)
        for amount in (True, -1, 11, 1.5, None):
            with self.subTest(amount=amount), patch.object(QuotaService, 'commit') as commit:
                self.assertIsInstance(self.port.commit(self.binding, amount), ProtectionError)
                commit.assert_not_called()
        self.assertEqual(self.held(), (10, 0, 0))

    def test_release_requires_bound_evidence_and_is_idempotent(self):
        self.port.reserve(self.binding)
        self.assertIsInstance(self.port.release(self.binding, ''), ProtectionError)
        with patch.object(QuotaService, 'release', wraps=QuotaService.release) as release:
            receipt = self.port.release(self.binding, 'proof/no-delivery')
            self.assertEqual(self.port.release(self.binding, 'proof/no-delivery'), receipt)
            release.assert_called_once_with(reservation_id=self.binding.reservation_id)
        self.assertEqual(receipt.state, QuotaState.RELEASED)
        self.assertEqual(self.held(), (0, 0, 0))
        self.assertEqual(self.port.release(self.binding, 'proof/other').code, ReasonCode.IDEMPOTENCY_CONFLICT)

    def test_unknown_retains_capacity_until_exact_reconciliation(self):
        self.port.reserve(self.binding)
        unknown = self.port.reconcile(self.binding, None, 'proof/unknown')
        self.assertEqual(unknown.held_amount, 10)
        self.assertEqual(self.port.reconcile(self.binding, None, 'proof/unknown'), unknown)
        self.assertEqual(self.held(), (0, 10, 0))
        self.assertIsInstance(self.port.release(self.binding, 'proof/no-delivery'), ProtectionError)
        self.assertIsInstance(self.port.commit(self.binding, 7), ProtectionError)
        self.assertIsInstance(self.port.require_active(self.binding), ProtectionError)
        self.assertIsInstance(self.port.reconcile(self.binding, 7, ''), ProtectionError)
        receipt = self.port.reconcile(self.binding, 7, 'proof/confirmed')
        self.assertEqual(self.port.reconcile(self.binding, 7, 'proof/confirmed'), receipt)
        self.assertEqual(self.held(), (0, 0, 7))
        self.assertEqual(self.port.reconcile(self.binding, 7, 'proof/other').code,
                         ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.port.reconcile(self.binding, 8, 'proof/confirmed').code,
                         ReasonCode.IDEMPOTENCY_CONFLICT)

    def test_expiry_denies_execution_but_never_frees_unknown(self):
        self.port.reserve(self.binding)
        with patch('django.utils.timezone.now', return_value=self.binding.expires_at + timedelta(seconds=1)):
            self.assertIsInstance(self.port.require_active(self.binding), ProtectionError)
            self.assertIsInstance(self.port.commit(self.binding, 10), ProtectionError)
            self.assertEqual(self.port.reconcile(self.binding, None, 'proof/unknown').state, QuotaState.UNKNOWN)
            self.assertIsInstance(self.port.release(self.binding, 'proof/expired'), ProtectionError)
            self.assertEqual(self.held(), (0, 10, 0))
            self.assertEqual(self.port.reconcile(self.binding, 0, 'proof/zero-delivery').state, QuotaState.COMMITTED)
        self.assertEqual(self.held(), (0, 0, 0))

    def test_receipt_write_failure_rolls_back_quota_commit(self):
        self.port.reserve(self.binding)
        with patch.object(QuotaExecution, 'save', side_effect=DatabaseError('synthetic receipt failure')):
            self.assertEqual(self.port.commit(self.binding, 7).code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(self.held(), (10, 0, 0))
        self.assertIsNone(QuotaExecution.objects.get().terminal_receipt)
        self.assertEqual(self.port.commit(self.binding, 7).state, QuotaState.COMMITTED)
        self.assertEqual(self.held(), (0, 0, 7))

    def test_uow_without_commit_rolls_back_reserve_and_binding(self):
        with DjangoUnitOfWork():
            self.assertEqual(self.port.reserve(self.binding).state, QuotaState.RESERVED)
        self.assertFalse(QuotaExecution.objects.exists())
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(QuotaBucket.objects.exists())

    def test_uow_commit_and_later_failure_do_not_partially_settle(self):
        with DjangoUnitOfWork() as work:
            self.port.reserve(self.binding)
            work.commit()
        with self.assertRaisesRegex(RuntimeError, 'audit failed'):
            with DjangoUnitOfWork() as work:
                self.assertEqual(self.port.commit(self.binding, 8).state, QuotaState.COMMITTED)
                work.commit()
                raise RuntimeError('audit failed')
        self.assertEqual(self.held(), (10, 0, 0))
        self.assertIsNone(QuotaExecution.objects.get().terminal_receipt)


class QuotaPortConcurrencyTests(QuotaFixture, TransactionTestCase):
    def test_two_committers_receive_one_effect_receipt(self):
        self.port.reserve(self.binding)
        barrier = Barrier(2)

        def worker():
            try:
                barrier.wait(timeout=10)
                return self.port.commit(self.binding, 7)
            finally:
                connections.close_all()

        with patch.object(QuotaService, 'commit', wraps=QuotaService.commit) as commit:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = [f.result(timeout=15) for f in [pool.submit(worker), pool.submit(worker)]]
            commit.assert_called_once()
        self.assertEqual(first, second)
        self.assertEqual(first.state, QuotaState.COMMITTED)
        self.assertEqual(self.held(), (0, 0, 7))
