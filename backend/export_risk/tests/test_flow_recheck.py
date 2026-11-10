"""Flow pre-delivery checks and real PostgreSQL lock-wait evidence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier, Event
from time import monotonic
from unittest.mock import patch

from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService
from export_risk.contracts import AuthorizationResult, RecommendedAction
from export_risk.decisions import service
from export_risk.decisions.approval import InMemoryApprovalProvider
from export_risk.models import ExecutionAuthorizationRecord
from export_risk.tests.test_decisions import make_assessment, make_auth_snapshot, make_request


def active(**values):
    return service._legacy_require_active(**values)


class FlowFixture:
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        self.request = make_request()
        self.snapshot = make_auth_snapshot()
        self.decision = service.create_risk_decision(
            make_assessment(RecommendedAction.ALLOW), self.request, idempotency_key='decision/flow',
        )
        QuotaService.reserve(subject_id='u1', data_domain='d1', window_key='flow',
            amount=10, request_fingerprint='fp1', reservation_id='reservation/flow', limit=10)

    def prepare(self):
        return service.prepare_execution(self.decision.decision_id, self.request, self.snapshot,
            idempotency_key='prepare/flow', environment='test', reservation_id='reservation/flow',
            authorization_id='authorization/flow', execution_id='execution/flow', require_active=active)

    def recheck(self, **changes):
        values = dict(authorization_id='authorization/flow', request=self.request,
            authorization_snapshot=self.snapshot, decision_id=self.decision.decision_id,
            execution_id='execution/flow', reservation_id='reservation/flow',
            require_active=active, environment='test')
        values.update(changes)
        return service.recheck_execution(**values)


class FlowRecheckTests(FlowFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.authorization = self.prepare()
        self.assertTrue(service.claim(self.authorization.authorization_id, require_active=active))

    def test_claimed_execution_rechecks_without_reserving_settling_or_consuming(self):
        with patch.object(QuotaService, 'reserve', side_effect=AssertionError('second reserve')), \
                patch.object(QuotaService, 'commit', side_effect=AssertionError('risk settled')), \
                patch.object(QuotaService, 'release', side_effect=AssertionError('risk released')):
            self.assertEqual(self.recheck(), self.authorization)
            self.assertEqual(self.recheck(), self.authorization)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_each_execution_identity_is_bound(self):
        for field in ('authorization_id', 'decision_id', 'execution_id', 'reservation_id'):
            with self.subTest(field=field):
                result = self.recheck(**{field: 'other/identity'})
                self.assertEqual(result.kind, 'not_executable')

    def test_fresh_grant_revocation_and_narrowing_are_rechecked(self):
        for changes in ({'result': AuthorizationResult.FORBIDDEN}, {'allowed_scope': ()},
                        {'allowed_operations': ()}, {'allowed_recipients': ()},
                        {'subject_id': 'other'}, {'environment': 'evaluation'},
                        {'valid_until': (timezone.now() - timedelta(seconds=1)).isoformat()}):
            with self.subTest(changes=changes):
                result = self.recheck(authorization_snapshot=replace(self.snapshot, **changes))
                self.assertEqual(result.kind, 'not_executable')

    def test_changed_request_and_environment_are_rejected(self):
        self.assertEqual(self.recheck(request=replace(self.request,
            request_fingerprint='other')).kind, 'not_executable')
        self.assertEqual(self.recheck(environment='production').kind, 'not_executable')

    def test_current_approval_is_required(self):
        self.decision.action = 'require_approval'
        self.decision.save(update_fields=['action'])
        approval = InMemoryApprovalProvider()
        approval.set_status(self.decision.decision_id, 'approved')
        self.assertEqual(self.recheck(approval=approval).kind, 'executable')
        approval.set_status(self.decision.decision_id, 'revoked')
        self.assertEqual(self.recheck(approval=approval).kind, 'not_executable')

    def test_shortened_live_grant_cannot_be_extended(self):
        until = timezone.now() + timedelta(seconds=30)
        result = self.recheck(authorization_snapshot=replace(self.snapshot, valid_until=until.isoformat()))
        self.assertEqual(result.valid_until, until.isoformat())
        self.assertEqual(self.recheck().valid_until, until.isoformat())

    def test_revoked_decision_and_terminal_authorization_are_rejected(self):
        service.invalidate_decision(self.decision.decision_id)
        self.assertEqual(self.recheck().kind, 'not_executable')
        self.decision.status = 'valid'
        self.decision.save(update_fields=['status'])
        self.assertTrue(service.consume(self.authorization.authorization_id))
        self.assertEqual(self.recheck().kind, 'not_executable')

    def test_not_claimed_and_revoked_states_are_rejected(self):
        for state in ('valid', 'revoked', 'expired'):
            ExecutionAuthorizationRecord.objects.update(state=state)
            with self.subTest(state=state):
                self.assertEqual(self.recheck().kind, 'not_executable')

    def test_unknown_hold_is_not_executable_or_released(self):
        QuotaService.reconcile(reservation_id='reservation/flow', delivered_amount=None)
        with patch.object(QuotaService, 'release', side_effect=AssertionError('unknown released')):
            self.assertEqual(self.recheck().kind, 'not_executable')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 10, 0))

    def test_authorization_deadline_is_rechecked_after_quota_callback(self):
        until = timezone.now() + timedelta(seconds=10)
        snapshot = replace(self.snapshot, valid_until=until.isoformat())
        before = timezone.now()
        clock = [before]

        def waited(**values):
            clock[0] = until + timedelta(seconds=1)
            return until + timedelta(minutes=1)

        with patch.object(service.timezone, 'now', side_effect=lambda: clock[0]):
            result = self.recheck(authorization_snapshot=snapshot, require_active=waited)
        self.assertEqual(result.kind, 'not_executable')
        self.assertIn('exec.decision_expired', result.reason_codes)

    def test_recheck_tightening_rolls_back_with_the_callers_uow(self):
        shorter = timezone.now() + timedelta(seconds=20)
        with self.assertRaisesRegex(RuntimeError, 'audit failed'):
            with transaction.atomic():
                self.recheck(authorization_snapshot=replace(self.snapshot, valid_until=shorter.isoformat()))
                self.assertTrue(service.consume(self.authorization.authorization_id))
                raise RuntimeError('audit failed')
        auth = ExecutionAuthorizationRecord.objects.get()
        self.assertEqual(auth.state, 'claiming')
        self.assertEqual(auth.valid_until.isoformat(), self.authorization.valid_until)


class FlowLockTests(FlowFixture, TransactionTestCase):
    def test_identical_prepare_and_competing_claim_have_one_winner(self):
        ready = Barrier(2)

        def worker():
            try:
                ready.wait(timeout=10)
                authorization = self.prepare()
                return authorization
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = [future.result(timeout=15) for future in
                             [pool.submit(worker), pool.submit(worker)]]
        self.assertEqual(first, second)
        ready = Barrier(2)

        def claim():
            try:
                ready.wait(timeout=10)
                return service.claim(first.authorization_id, require_active=active)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=15) for future in [pool.submit(claim), pool.submit(claim)]]
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (10, 0, 0))

    def test_claim_and_recheck_reject_hold_expiring_during_real_bucket_lock(self):
        authorization = self.prepare()
        for stage in ('claim', 'recheck'):
            if stage == 'recheck':
                QuotaReservation.objects.update(expires_at=timezone.now() + timedelta(minutes=5))
                self.assertTrue(service.claim(authorization.authorization_id, require_active=active))
            entered = Event()
            backend_pid = []

            def waiting():
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SET lock_timeout = '5s'")
                        cursor.execute('SELECT pg_backend_pid()')
                        backend_pid.append(cursor.fetchone()[0])
                    entered.set()
                    return (service.claim(authorization.authorization_id, require_active=active)
                            if stage == 'claim' else self.recheck())
                finally:
                    connections.close_all()

            with self.subTest(stage=stage), ThreadPoolExecutor(max_workers=1) as pool:
                with transaction.atomic():
                    QuotaBucket.objects.select_for_update().get()
                    expires_at = timezone.now() + timedelta(seconds=1)
                    QuotaReservation.objects.update(expires_at=expires_at)
                    future = pool.submit(waiting)
                    self.assertTrue(entered.wait(timeout=5))
                    deadline = monotonic() + 5
                    locked = False
                    while monotonic() < deadline:
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))',
                                           [backend_pid[0]])
                            locked = cursor.fetchone()[0]
                        if locked:
                            break
                        Event().wait(0.01)
                    self.assertTrue(locked, 'worker must actually wait on the held PostgreSQL lock')
                    self.assertLess(timezone.now(), expires_at, 'wait must begin before expiry')
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_sleep(GREATEST(0, EXTRACT(EPOCH FROM '
                            '(%s::timestamptz - clock_timestamp())) + 0.05))', [expires_at])
                result = future.result(timeout=10)
                self.assertFalse(result if stage == 'claim' else result.kind == 'executable')
                self.assertGreaterEqual(timezone.now(), expires_at)
                print(f'PG_LOCK_EVIDENCE stage={stage} blocked=true expired_before_unlock=true')
            self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
            self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)
