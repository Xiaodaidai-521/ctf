from threading import Event, Thread
from unittest import skipUnless
from datetime import timedelta

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from controlled_export.models import ExportExecution


@skipUnless(connection.vendor == "postgresql", "requires a real PostgreSQL test database")
class PostgreSQLLockingTests(TransactionTestCase):
    reset_sequences = True

    def test_execution_row_lock_serializes_competing_state_changes(self):
        execution = ExportExecution.objects.create(
            authorization_id="postgres-lock-auth",
            export_request_id="postgres-lock-request",
            decision_id="postgres-lock-decision",
            asset_version_id="postgres-lock-asset",
            input_content_hash="a" * 64,
            profile_id="postgres-lock-profile",
            request_fingerprint="b" * 64,
            scope_hash="c" * 64,
            effective_action="allow",
            obligations=[],
            valid_until=timezone.now() + timedelta(minutes=5),
            environment="evaluation",
            data_domain="synthetic-domain",
            subject_id="synthetic-subject",
        )
        locked = Event()
        release = Event()
        second_finished = Event()

        def first_worker():
            close_old_connections()
            with transaction.atomic():
                ExportExecution.objects.select_for_update().get(pk=execution.pk)
                locked.set()
                release.wait(5)
            close_old_connections()

        def second_worker():
            close_old_connections()
            locked.wait(5)
            with transaction.atomic():
                ExportExecution.objects.select_for_update().get(pk=execution.pk)
            second_finished.set()
            close_old_connections()

        first = Thread(target=first_worker)
        second = Thread(target=second_worker)
        first.start()
        second.start()
        self.assertTrue(locked.wait(5))
        self.assertFalse(second_finished.wait(0.2))
        release.set()
        first.join(5)
        second.join(5)
        self.assertTrue(second_finished.is_set())
