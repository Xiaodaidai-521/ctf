"""Real, isolated PostgreSQL tests; outside pure unittest discovery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

from django.db import connection, connections
from django.test import TransactionTestCase

from mainline1.review import ReviewService, ReviewConflict, ReviewOutbox
from mainline1.review_repository import DjangoReviewRepository
from mainline1.tests import test_review


class PostgresReviews(test_review.ReviewTests, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql')
        self.repo = DjangoReviewRepository()
        self.service = ReviewService(self.repo, self.access)
        self.pid = self.service.register(self.actor, self.result, self.parsed)

    def test_two_reviewers_one_successor(self):
        gate = Barrier(2)
        def contender(actor):
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    backend_id = cursor.fetchone()[0]
                service = ReviewService(DjangoReviewRepository(), self.access)
                gate.wait(timeout=10)
                try:
                    result = service.submit_review(replace(self.actor, actor_id=actor), base_profile_id=self.pid,
                        expected_state_version=1, idempotency_key='race', action='confirm', reason='synthetic',
                        finding_id=self.email['finding_id'])
                except ReviewConflict as exc:
                    result = exc
                return backend_id, result
            finally:
                connections['default'].close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(contender, (1, 2)))
        self.assertNotEqual(rows[0][0], rows[1][0])
        values = [r[1] for r in rows]
        won = next(v for v in values if isinstance(v, dict))
        lost = next(v for v in values if isinstance(v, ReviewConflict))
        self.assertEqual(lost.latest_profile_id, won['successor_profile_id'])
        self.assertEqual(len(self.snapshot().reviews), 1)
        self.assertEqual(len(self.snapshot().bundles), 2)

    def test_reconnect_preserves_history_idempotency_and_pending_outbox(self):
        record = self.submit()
        connection.close()
        restarted = ReviewService(DjangoReviewRepository(), self.access)
        self.assertEqual(restarted.get_review(self.actor, record['review_id']), record)
        self.assertEqual(restarted.get_profile_applicability(self.actor, self.pid)['status'], 'superseded')
        self.service = restarted
        self.assertEqual(self.submit(), record)
        self.assertEqual(len(self.snapshot().outbox), 1)

    def test_ack_loss_after_delivery_replays_same_persistent_event(self):
        self.submit()
        seen = []
        class Sink:
            def publish(self, event):
                seen.append(event['event_id'])
                return True
        delegate = self.repo
        class FailingAckRepository:
            calls = 0
            def atomic(self, operation):
                self.calls += 1
                if self.calls == 2:
                    raise RuntimeError('simulated acknowledgement commit failure')
                return delegate.atomic(operation)
        with self.assertRaises(RuntimeError):
            ReviewOutbox(FailingAckRepository(), Sink()).dispatch()
        connection.close()
        ReviewOutbox(DjangoReviewRepository(), Sink()).dispatch()
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], seen[1])

    def test_ledger_unique_row_constraint(self):
        from django.db import IntegrityError, transaction
        from mainline1.models import ReviewLedger
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReviewLedger.objects.create(pk=2, state={})
