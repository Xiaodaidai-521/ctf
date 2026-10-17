"""SQL-level proof that plan validation cannot create/update business records."""
from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from mainline1.models import ReviewLedger
from mainline1.review import ReviewService
from mainline1.review_repository import DjangoReviewRepository
from mainline1.tests import test_planning


class PostgresPlanning(TransactionTestCase):
    def setUp(self):
        self.case = test_planning.PlanningTests()
        self.case.setUp()
        t = self.case
        t.repo = DjangoReviewRepository()
        t.review = ReviewService(t.repo, t.access)
        t.register(t.parsed)
        t.source.review = t.review

    def test_success_and_invalid_validation_only_select(self):
        t = self.case
        plan = t.build()
        before = t.repo.read(lambda s: s)
        with CaptureQueriesContext(connection) as queries:
            self.assertTrue(t.check(plan)['valid'])
            t.source.overrides['asset_state'] = 'deleted'
            t.invalid(plan, 'ASSET_UNAVAILABLE')
        self.assertGreater(len(queries), 0)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT ') for q in queries))
        self.assertEqual(before, t.repo.read(lambda s: s))

    def test_absent_ledger_validation_does_not_create_it(self):
        t = self.case
        plan = t.build()
        ReviewLedger.objects.all().delete()  # Only this test's disposable isolated DB.
        with CaptureQueriesContext(connection) as queries:
            t.code('OBJECT_NOT_FOUND', t.check, plan)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT ') for q in queries))
        self.assertEqual(ReviewLedger.objects.count(), 0)

    def test_reconnect_observes_manual_change(self):
        t = self.case
        plan = t.build()
        t.review.submit_review(t.actor, base_profile_id=t.pid, expected_state_version=1,
            idempotency_key='postgres-manual', action='add_manual', reason='synthetic',
            category_id=t.findings[0]['category_id'], locations=t.findings[0]['locations'])
        connection.close()
        t.source.review = ReviewService(DjangoReviewRepository(), t.access)
        with CaptureQueriesContext(connection) as queries:
            t.invalid(plan, 'PROFILE_SUPERSEDED')
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT ') for q in queries))
