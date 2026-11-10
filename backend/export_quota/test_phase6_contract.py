"""Unmodified shared quota cases against the actual M6/original-domain writer."""
from contextlib import ExitStack
from dataclasses import replace
from unittest.mock import patch

from django.db import DatabaseError, connection
from django.test import TestCase

from data_security.adapters.persistence.models import QuotaExecution
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.contracts import ReasonCode
from data_security.tests.quota_contract import QuotaContract
from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaError, QuotaService


class PostgresQuotaContractTests(QuotaContract, TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        clock = patch('django.utils.timezone.now', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        super().setUp()

    def make_port(self, **changes):
        config = dict(environment='test', window_key='window/1', limit=10, ttl_seconds=300)
        config.update(changes)
        return DjangoQuotaPort(**config)

    def balances(self):
        buckets = list(QuotaBucket.objects.all())
        return (sum(b.active_reserved for b in buckets), sum(b.unknown_reserved for b in buckets),
                sum(b.settled for b in buckets))

    def quota_snapshot(self):
        return tuple(list(model.objects.order_by('pk').values())
                     for model in (QuotaExecution, QuotaBucket, QuotaReservation))

    def set_terminal(self, **changes):
        QuotaExecution.objects.filter(idempotency_key=self.binding.idempotency_key).update(**changes)

    def test_read_committed_uses_only_original_observe(self):
        self.port.reserve(self.binding)
        receipt = self.port.commit(self.binding, 7)
        before = self.quota_snapshot()
        with ExitStack() as stack:
            for name in ('reserve', 'require_active', 'commit', 'release', 'reconcile'):
                stack.enter_context(patch.object(QuotaService, name, side_effect=AssertionError(name)))
            for model in (QuotaExecution, QuotaBucket, QuotaReservation):
                stack.enter_context(patch.object(model, 'save', side_effect=AssertionError('read-only')))
            observe = stack.enter_context(patch.object(QuotaService, 'observe', wraps=QuotaService.observe))
            self.assertEqual(self.port.read_committed(self.binding), receipt)
            observe.assert_called_once_with(reservation_id=self.binding.reservation_id)
        self.assertEqual(self.quota_snapshot(), before)

    def test_read_committed_refuses_owner_or_receipt_read_errors(self):
        self.port.reserve(self.binding)
        self.port.commit(self.binding, 7)
        before = self.quota_snapshot()
        for target, name, error, code in (
                (QuotaExecution.objects, 'filter', DatabaseError('synthetic receipt read'),
                 ReasonCode.DELIVERY_UNKNOWN),
                (QuotaService, 'observe', DatabaseError('synthetic owner read'), ReasonCode.DELIVERY_UNKNOWN),
                (QuotaService, 'observe', QuotaError('synthetic missing reservation'),
                 ReasonCode.AUTHORIZATION_DENIED)):
            with self.subTest(source=name, error=type(error).__name__), patch.object(target, name, side_effect=error):
                self.assert_error(self.port.read_committed(self.binding), code)
            self.assertEqual(self.quota_snapshot(), before)

    def test_read_committed_refuses_inconsistent_owner_observations(self):
        self.port.reserve(self.binding)
        self.port.commit(self.binding, 7)
        state = QuotaService.observe(reservation_id=self.binding.reservation_id)
        before = self.quota_snapshot()
        for changes in ({'reservation_id': 'reservation/other'}, {'subject_id': 'actor/other'},
                        {'data_domain': 'domain/other'}, {'window_key': 'window/other'},
                        {'request_fingerprint': '1' * 64}, {'amount': 9}, {'settled_amount': 8}):
            with self.subTest(field=next(iter(changes))), patch.object(
                    QuotaService, 'observe', return_value=replace(state, **changes)):
                self.assert_error(self.port.read_committed(self.binding), ReasonCode.IDEMPOTENCY_CONFLICT)
            self.assertEqual(self.quota_snapshot(), before)
        for changed in ('reserved', 'unknown', 'released'):
            with self.subTest(state=changed), patch.object(
                    QuotaService, 'observe', return_value=replace(state, state=changed)):
                self.assert_error(self.port.read_committed(self.binding), ReasonCode.AUTHORIZATION_DENIED)
            self.assertEqual(self.quota_snapshot(), before)

    def test_read_committed_refuses_mismatched_execution_record(self):
        self.port.reserve(self.binding)
        self.port.commit(self.binding, 7)
        QuotaExecution.objects.filter(idempotency_key=self.binding.idempotency_key).update(
            reservation_id='reservation/other')
        before = self.quota_snapshot()
        self.assert_error(self.port.read_committed(self.binding), ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.quota_snapshot(), before)
