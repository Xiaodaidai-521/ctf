"""M4 quota tests: accounting, lifecycle, idempotency, and PG concurrency."""

import threading
from unittest import skipUnless

from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase

from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaExceeded, QuotaService

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
