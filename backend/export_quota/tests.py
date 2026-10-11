"""M4 quota tests: accounting, lifecycle, idempotency, and PG concurrency."""

import threading
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase

from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaConflict, QuotaError, QuotaExceeded, QuotaService

BUCKET = dict(subject_id="u1", data_domain="d1", window_key="2026-10-11")


def do_reserve(reservation_id, amount, limit=100):
    return QuotaService.reserve(
        reservation_id=reservation_id, amount=amount, limit=limit,
        request_fingerprint="fp", **BUCKET,
    )


class QuotaAccountingTests(TestCase):
    def _bucket(self):
        return QuotaBucket.objects.get(**BUCKET)

    def test_reserve_then_exceed(self):
        do_reserve("r1", 60)
        self.assertEqual(self._bucket().active_reserved, 60)
        self.assertEqual(self._bucket().available, 40)
        with self.assertRaises(QuotaExceeded):
            do_reserve("r2", 60)  # 40 < 60

    def test_commit_uses_delivered_amount(self):
        do_reserve("r1", 60)
        QuotaService.commit(reservation_id="r1", delivered_amount=50)  # delivered <= reserved
        b = self._bucket()
        self.assertEqual(b.active_reserved, 0)
        self.assertEqual(b.settled, 50)
        self.assertEqual(b.available, 50)

    def test_release_frees_active(self):
        do_reserve("r1", 30)
        QuotaService.release(reservation_id="r1")
        self.assertEqual(self._bucket().active_reserved, 0)
        self.assertEqual(self._bucket().available, 100)

    def test_reconcile_unknown_holds_capacity(self):
        do_reserve("r1", 30)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=None)
        b = self._bucket()
        self.assertEqual(b.active_reserved, 0)
        self.assertEqual(b.unknown_reserved, 30)      # not released
        self.assertEqual(b.available, 70)             # capacity still held (R2/I6)
        self.assertEqual(QuotaReservation.objects.get(reservation_id="r1").state, "unknown")

    def test_idempotent_reserve_no_double_increment(self):
        do_reserve("r1", 40)
        again = do_reserve("r1", 40)
        self.assertTrue(again.idempotent_replay)
        self.assertEqual(self._bucket().active_reserved, 40)  # not 80


class QuotaSafeguardTests(TestCase):
    """Review F6/F7/F8: idempotency binding, unknown recovery, amount integrity."""

    def _bucket(self):
        return QuotaBucket.objects.get(**BUCKET)


    def test_replay_rejects_changed_binding(self):
        do_reserve("r1", 60)
        with self.assertRaises(QuotaConflict):
            QuotaService.reserve(reservation_id="r1", amount=90, limit=100,
                                 request_fingerprint="different-fp",
                                 subject_id="other-user", data_domain="d1", window_key="2026-10-11")
        self.assertEqual(QuotaReservation.objects.get(reservation_id="r1").bucket.subject_id, "u1")

    def test_unknown_can_be_reconciled_after_receipt(self):
        do_reserve("r1", 60)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=None)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=40)
        b = QuotaBucket.objects.get(**BUCKET)
        self.assertEqual((b.unknown_reserved, b.settled, b.available), (0, 40, 60))

    def test_repeated_unknown_result_is_idempotent(self):
        do_reserve("r1", 60)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=None)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=None)
        self.assertEqual(QuotaBucket.objects.get(**BUCKET).unknown_reserved, 60)

    def test_rejects_negative_amount(self):
        with self.assertRaises(ValueError):
            do_reserve("neg", -50)

    def test_over_delivery_is_not_silently_clamped(self):
        do_reserve("r1", 60)
        with self.assertRaises(QuotaError):
            QuotaService.commit(reservation_id="r1", delivered_amount=90)

    def test_confirmed_reconcile_retry_is_idempotent(self):
        do_reserve("r1", 60)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=None)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=40)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=40)
        bucket = self._bucket()
        self.assertEqual((bucket.unknown_reserved, bucket.settled, bucket.available), (0, 40, 60))

    def test_different_confirmed_reconcile_retry_conflicts(self):
        do_reserve("r1", 60)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=None)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=40)
        with self.assertRaises(QuotaConflict):
            QuotaService.reconcile(reservation_id="r1", delivered_amount=50)


    def test_expired_reservation_replay_is_not_active(self):
        do_reserve("r1", 60)
        reservation = QuotaReservation.objects.get(reservation_id="r1")
        with patch("export_quota.services.timezone.now", return_value=reservation.expires_at):
            with self.assertRaises(QuotaError):
                do_reserve("r1", 60)
        bucket = self._bucket()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.available), (60, 0, 40))

    def test_require_active_rejects_all_terminal_states(self):
        for state in ("released", "unknown", "committed"):
            with self.subTest(state=state):
                rid = "r-" + state
                do_reserve(rid, 10)
                if state == "released":
                    QuotaService.release(reservation_id=rid)
                elif state == "unknown":
                    QuotaService.reconcile(reservation_id=rid)
                else:
                    QuotaService.commit(reservation_id=rid, delivered_amount=5)
                with self.assertRaises(QuotaError):
                    QuotaService.require_active(reservation_id=rid, request_fingerprint="fp")

    def test_unknown_retry_cannot_reopen_settled_reservation(self):
        do_reserve("r1", 60)
        QuotaService.reconcile(reservation_id="r1", delivered_amount=40)
        with self.assertRaises(QuotaConflict):
            QuotaService.reconcile(reservation_id="r1", delivered_amount=None)
        self.assertEqual(self._bucket().settled, 40)
        self.assertEqual(self._bucket().unknown_reserved, 0)


@skipUnless(connection.vendor == "postgresql", "requires real PostgreSQL row locks")
class QuotaConcurrencyTests(TransactionTestCase):
    """Two concurrent 60-unit reservations on a 100 limit: exactly one wins."""

    def test_concurrent_reserve_only_one_succeeds(self):
        QuotaBucket.objects.create(limit=100, **BUCKET)
        results = {}
        barrier = threading.Barrier(2)

        def worker(rid):
            barrier.wait()
            try:
                do_reserve(rid, 60)
                results[rid] = "ok"
            except QuotaExceeded:
                results[rid] = "exceeded"
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(f"r{i}",)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(results.values()), ["exceeded", "ok"])
        self.assertEqual(QuotaBucket.objects.get(**BUCKET).active_reserved, 60)
