"""Small SQL-backed smoke over the backend-only workflow; isolated DB only."""
from django.test import TransactionTestCase

from mainline1.operations import Operations
from mainline1.cleanup import CleanupPolicy
from mainline1.parsing import InputError
from mainline1.review import ReviewPrincipal, ReviewService
from mainline1.review_repository import DjangoReviewRepository
from mainline1.tests.test_operations import OperationsTests


class PostgresOperations(TransactionTestCase):
    def setUp(self):
        fixture = OperationsTests()
        fixture.setUp()
        fixture.repo = DjangoReviewRepository()
        fixture.ops = Operations(fixture.repo, fixture.access, fixture.asset_store, clock=lambda: 1000)
        self.fixture = fixture

    def test_scan_query_and_cleanup_preview_use_durable_review_ledger(self):
        f = self.fixture
        created = f.ops.create_scan(f.actor, f.ref.version_id, configuration=f.fixture.config,
            context=f.fixture.context(f.parsed), idempotency_key='pg-workflow', scope=f.parsed.scope,
            semantic_required=False)
        self.assertEqual(f.ops.execute_one(f.actor, created['scan_id'])['status'], 'succeeded')
        self.assertEqual(f.ops.get_scan(f.actor, created['scan_id'])['status'], 'succeeded')
        preview = f.ops.cleanup_preview(f.actor)
        self.assertEqual(preview['candidate_count'], 0)

    def test_cleanup_tombstone_and_audit_survive_reconnect(self):
        from django.db import connection
        f = self.fixture
        finished = f.scan(key='pg-cleanup')
        f.repo.atomic(lambda s: s.resources['parsed:' + finished['scan_id']].update(expires_at=1))
        ops = Operations(f.repo, f.access, f.asset_store, clock=lambda: 1000,
                         cleanup_policy=CleanupPolicy(approved=True, retention_seconds=10))
        preview = ops.cleanup_preview(f.actor)
        ops.cleanup_execute(f.actor, dry_run=False, reason='RETENTION_EXPIRED',
                            preview_hash=preview['preview_hash'])
        connection.close()
        reopened = Operations(DjangoReviewRepository(), f.access, f.asset_store, clock=lambda: 1000)
        with self.assertRaises(InputError) as deleted:
            reopened.read_private_parsed(f.actor, finished['scan_id'])
        self.assertEqual(deleted.exception.code, 'ARTIFACT_DELETED')
        self.assertEqual(reopened.review.get_profile_applicability(f.actor, finished['profile_id'])['status'],
                         'unverifiable_deleted')
        self.assertEqual(reopened.repository.read(lambda s: s.cleanup_audit[-1]['deleted_ids']),
                         ['parsed:' + finished['scan_id']])

    def test_cancelled_run_survives_reconnect(self):
        f = self.fixture
        created = f.ops.create_scan(f.actor, f.ref.version_id, configuration=f.fixture.config,
            context=f.fixture.context(f.parsed), idempotency_key='pg-cancel', scope=f.parsed.scope,
            semantic_required=False)
        f.ops.cancel_scan(f.actor, created['scan_id'])
        from django.db import connection
        connection.close()
        f.ops = Operations(f.repo, f.access, f.asset_store, clock=lambda: 1000)
        self.assertEqual(f.ops.get_scan(f.actor, created['scan_id'])['status'], 'cancelled')
