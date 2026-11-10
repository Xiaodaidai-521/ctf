"""Shared RiskPort contract against original risk/quota owners on isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic
from unittest.mock import patch

from django.db import DatabaseError, connection, connections, transaction
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from data_security.adapters.persistence import risk
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.risk import DjangoRiskPort
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import ReasonCode
from data_security.tests.risk_contract import RiskContract
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.decisions.serde import digest
from export_risk.decisions.service import invalidate_decision
from export_risk.models import EventOutbox, ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision


class PostgresRiskContractTests(RiskContract, TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        clock = patch('django.utils.timezone.now', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        super().setUp()

    def make_port(self, **changes):
        return DjangoRiskPort(**self.port_options(changes))

    def make_quota(self, **changes):
        options = dict(environment='test', window_key='risk-contract', limit=10, ttl_seconds=300)
        options.update(changes)
        return DjangoQuotaPort(**options)

    def resources(self):
        return (RiskDecision.objects.count(), ExecutionAuthorizationRecord.objects.count(),
                EventOutbox.objects.filter(event_type='decision.issued').count(),
                EventOutbox.objects.filter(event_type='execution.authorized').count())

    def balances(self):
        buckets = list(QuotaBucket.objects.all())
        return (QuotaReservation.objects.count(), sum(b.active_reserved for b in buckets),
                sum(b.unknown_reserved for b in buckets), sum(b.settled for b in buckets))

    def decision_state(self):
        decision = RiskDecision.objects.get()
        return dict(id=decision.decision_id, expires_at=decision.valid_until)

    def execution_state(self):
        return ExecutionAuthorizationRecord.objects.get().state

    def set_execution_state(self, state):
        ExecutionAuthorizationRecord.objects.update(state=state)

    def invalidate_decision(self):
        invalidate_decision(self.binding.decision_id)

    def test_delivered_rechecks_only_select_and_lock_decision_before_authorization(self):
        self.consume_and_commit()
        original = ExecutionAuthorizationRecord.objects.values().get()
        self.grant = replace(self.grant, valid_until=(self.now + timedelta(seconds=40)).isoformat())
        rebuilt = self.make_port()
        with transaction.atomic():
            with CaptureQueriesContext(connection) as queries:
                self.assertIs(rebuilt.recheck_delivered(self.binding), True)
                self.assertIs(rebuilt.recheck_delivered(self.binding), True)
            # Nested owner transactions add savepoint control, not business writes.
            statements = [query['sql'] for query in queries.captured_queries
                          if not query['sql'].upper().startswith(('SAVEPOINT ', 'RELEASE SAVEPOINT '))]
            self.assertTrue(statements)
            for statement in statements:
                self.assertTrue(statement.lstrip().upper().startswith('SELECT '))
            locks = [statement for statement in statements if 'FOR UPDATE' in statement.upper()]
            self.assertEqual(len(locks), 4)
            for statement, model in zip(locks, (RiskDecision, ExecutionAuthorizationRecord) * 2):
                self.assertIn('FROM "' + model._meta.db_table + '"', statement)
        self.assertEqual(ExecutionAuthorizationRecord.objects.values().get(), original)
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_delivered_recheck_rejects_revocation_and_expiry_after_real_owner_lock_wait(self):
        # Use the wall clock only for this 6-F02 lock-wait probe, not the shared clock fixture.
        self.now = datetime.now(timezone.utc)
        self.binding = replace(self.binding, expires_at=self.now + timedelta(seconds=900))
        self.grant = replace(self.grant, observed_at=(self.now - timedelta(seconds=1)).isoformat(),
                             valid_until=(self.now + timedelta(seconds=1200)).isoformat())
        with patch('django.utils.timezone.now', side_effect=lambda: datetime.now(timezone.utc)):
            self.consume_and_commit()
            quota = (QuotaReservation.objects.values().get(), QuotaBucket.objects.values().get())
            for model in (RiskDecision, ExecutionAuthorizationRecord):
                for change in ('revoked', 'expired'):
                    entered, backend_pid = Event(), []

                    def waiting():
                        try:
                            with connection.cursor() as cursor:
                                cursor.execute("SET lock_timeout = '5s'")
                                cursor.execute('SELECT pg_backend_pid()')
                                backend_pid.append(cursor.fetchone()[0])
                            entered.set()
                            return self.port.recheck_delivered(self.binding)
                        finally:
                            connections.close_all()

                    with self.subTest(model=model.__name__, change=change), ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic():
                            row = model.objects.select_for_update().get()
                            if change == 'expired':
                                field, value = 'valid_until', datetime.now(timezone.utc) + timedelta(seconds=1)
                            else:
                                field, value = (('status', 'invalidated') if model is RiskDecision
                                                else ('state', 'revoked'))
                            original = getattr(row, field)
                            if change == 'expired':
                                setattr(row, field, value)
                                row.save(update_fields=[field])
                            future = pool.submit(waiting)
                            self.assertTrue(entered.wait(timeout=5))
                            deadline, locked = monotonic() + 5, False
                            while monotonic() < deadline:
                                with connection.cursor() as cursor:
                                    cursor.execute('SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))',
                                                   [backend_pid[0]])
                                    locked = cursor.fetchone()[0]
                                if locked:
                                    break
                                Event().wait(0.01)
                            self.assertTrue(locked, 'delivered recheck must actually wait on the owner row lock')
                            if change == 'expired':
                                self.assertLess(datetime.now(timezone.utc), value, 'wait must begin before expiry')
                                with connection.cursor() as cursor:
                                    cursor.execute('SELECT pg_sleep(GREATEST(0, EXTRACT(EPOCH FROM '
                                        '(%s::timestamptz - clock_timestamp())) + 0.05))', [value])
                                self.assertGreaterEqual(datetime.now(timezone.utc), value)
                            else:
                                # Publish revocation while the recheck is already blocked on this row.
                                setattr(row, field, value)
                                row.save(update_fields=[field])
                            expected = (RiskDecision.objects.values().get(),
                                        ExecutionAuthorizationRecord.objects.values().get())
                        result = future.result(timeout=10)
                        self.assert_error(result)
                        self.assertEqual((RiskDecision.objects.values().get(),
                                          ExecutionAuthorizationRecord.objects.values().get()), expected)
                        self.assertEqual((QuotaReservation.objects.values().get(),
                                          QuotaBucket.objects.values().get()), quota)
                        model.objects.update(**{field: original})

    def test_delivered_recheck_missing_original_issuance_is_not_recreated(self):
        self.consume_and_commit()
        IdempotencyRecord.objects.filter(key='ds-issue/' + self.binding.idempotency_key).delete()
        records, assesses = IdempotencyRecord.objects.count(), len(self.assess_calls)
        self.assert_error(self.make_port().recheck_delivered(self.binding))
        self.assertEqual(IdempotencyRecord.objects.count(), records)
        self.assertEqual(len(self.assess_calls), assesses)
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_delivered_recheck_rejects_legacy_issue_digest_without_complete_binding(self):
        self.consume_and_commit()
        decision = RiskDecision.objects.get()
        legacy = digest('prepare', self.request.request_fingerprint, decision.decision_id, decision.obligations)
        legacy = digest(legacy, self.binding.reservation_id, self.binding.authorization_id, self.binding.execution_id)
        record = IdempotencyRecord.objects.get(key='ds-issue/' + self.binding.idempotency_key)
        record.bound_digest = legacy
        record.save(update_fields=['bound_digest'])
        self.assert_error(self.make_port().recheck_delivered(self.binding), ReasonCode.IDEMPOTENCY_CONFLICT)
        record.refresh_from_db()
        self.assertEqual(record.bound_digest, legacy)
        self.assertEqual(self.execution_state(), 'consumed')

    def test_delivered_recheck_rejects_unknown_stored_deadlines_without_repair(self):
        self.consume_and_commit()
        for model in (ExecutionAuthorizationRecord, RiskDecision):
            original = model.objects.get().valid_until
            model.objects.update(valid_until=None)
            with self.subTest(model=model.__name__):
                self.assert_error(self.port.recheck_delivered(self.binding))
                self.assertIsNone(model.objects.get().valid_until)
            model.objects.update(valid_until=original)
        self.assertIs(self.port.recheck_delivered(self.binding), True)
        self.assertEqual(self.execution_state(), 'consumed')

    def test_delivered_recheck_owner_database_error_is_not_permission(self):
        self.consume_and_commit()
        with patch.object(risk, 'recheck_delivered', side_effect=DatabaseError('synthetic fault')):
            self.assert_error(self.port.recheck_delivered(self.binding), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    @contextmanager
    def work(self):
        with DjangoUnitOfWork() as work:
            yield
            work.commit()
