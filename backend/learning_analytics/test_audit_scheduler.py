"""Recovery and ownership regressions for recorded-data analytics jobs."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from io import StringIO
import threading
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from users.models import CTFUser
from .models import LearningAuditJob, LearningEffectSnapshot, LearningEvent
from .scheduler import get_idempotency_key, get_period, run_analytics_job


class AnalyticsJobRecoveryTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='audit-job-student', role='student')

    def running_job(self, *, stale):
        start, end = get_period(30)
        job = LearningAuditJob.objects.create(
            job_id='audit-job', idempotency_key=get_idempotency_key('manual', start, end, self.student.pk),
            job_type='manual', target_user=self.student, analysis_start_time=start,
            analysis_end_time=end, start_time=timezone.now(), status='running', attempt_count=1,
            success_count=99, processed_user_count=99, progress=99,
        )
        if stale:
            LearningAuditJob.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(hours=1))
        return job

    def test_stale_job_retries_and_resets_old_progress(self):
        original = self.running_job(stale=True)
        result = run_analytics_job(job_type='manual', user_id=self.student.pk)
        self.assertEqual(result.pk, original.pk)
        self.assertEqual(result.status, 'completed')
        self.assertEqual(result.attempt_count, 2)
        self.assertEqual(result.success_count, 1)
        self.assertEqual(result.processed_user_count, 1)
        self.assertEqual(result.progress, 100)
        self.assertTrue(LearningEffectSnapshot.objects.filter(user=self.student).exists())

    def test_live_job_is_not_reclaimed(self):
        original = self.running_job(stale=False)
        with patch('learning_analytics.scheduler.rebuild_user_analytics') as rebuild:
            result = run_analytics_job(job_type='manual', user_id=self.student.pk)
        rebuild.assert_not_called()
        self.assertEqual(result.pk, original.pk)
        self.assertEqual(result.status, 'running')
        self.assertEqual(result.attempt_count, 1)

    def test_failed_user_work_rolls_back_and_command_reports_failure(self):
        def partial_failure(user, start, end):
            LearningEvent.objects.create(event_id='partial-audit-write', user=user,
                                         event_type='page_heartbeat', event_time=timezone.now())
            raise RuntimeError('synthetic rebuild failure')

        output = StringIO()
        with patch('learning_analytics.scheduler.rebuild_user_analytics', side_effect=partial_failure):
            with self.assertRaises(CommandError):
                call_command('refresh_learning_analytics', user_id=self.student.pk, stdout=output)
        self.assertEqual(output.getvalue(), '')
        self.assertFalse(LearningEvent.objects.filter(event_id='partial-audit-write').exists())
        job = LearningAuditJob.objects.get()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.error_count, 1)
        self.assertEqual(job.success_count, 0)

    def test_failed_job_can_retry_without_retaining_failed_counters(self):
        with patch('learning_analytics.scheduler.rebuild_user_analytics', side_effect=RuntimeError('first failure')):
            failed = run_analytics_job(job_type='manual', user_id=self.student.pk)
        self.assertEqual(failed.status, 'failed')
        retried = run_analytics_job(job_type='manual', user_id=self.student.pk)
        self.assertEqual(retried.pk, failed.pk)
        self.assertEqual(retried.attempt_count, 2)
        self.assertEqual(retried.status, 'completed')
        self.assertEqual(retried.error_count, 0)
        self.assertEqual(retried.error_message, '')

    def test_superseded_worker_cannot_rebuild_or_overwrite_new_attempt(self):
        student = self.student
        newer_results = []

        class PausedStudents:
            def order_by(self, *args):
                return self

            def filter(self, **kwargs):
                return self

            def __iter__(self):
                # Pause after the first worker claims the job, outside its row lock.
                job = LearningAuditJob.objects.get()
                LearningAuditJob.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(hours=1))
                newer_results.append(run_analytics_job(job_type='manual', user_id=student.pk))
                return iter([student])

        class PausedManager:
            def filter(self, **kwargs):
                return PausedStudents()

        class PausedModel:
            objects = PausedManager()

        with patch('learning_analytics.scheduler.get_user_model', side_effect=[PausedModel, CTFUser]):
            with patch('learning_analytics.scheduler.rebuild_user_analytics') as rebuild:
                result = run_analytics_job(job_type='manual', user_id=student.pk)
        self.assertEqual(result.attempt_count, 2)
        self.assertEqual(result.status, 'completed')
        self.assertEqual(result.success_count, 1)
        self.assertEqual(newer_results[0].pk, result.pk)
        rebuild.assert_called_once()

    def test_command_does_not_announce_running_job_as_completed(self):
        self.running_job(stale=False)
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command('refresh_learning_analytics', user_id=self.student.pk, stdout=output)
        self.assertEqual(output.getvalue(), '')


class AnalyticsJobOwnershipConcurrencyTests(TransactionTestCase):
    def test_live_user_transaction_blocks_reclaim_even_if_heartbeat_looks_old(self):
        if connection.vendor != 'postgresql':
            self.skipTest('requires PostgreSQL row locking')
        student = CTFUser.objects.create_user(username='audit-job-concurrent', role='student')
        entered, release = threading.Event(), threading.Event()
        observed_users = []

        def rebuild(user, start, end):
            observed_users.append(user.pk)
            LearningAuditJob.objects.filter(target_user=user).update(updated_at=timezone.now() - timedelta(hours=1))
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test did not release worker')

        def worker():
            try:
                return run_analytics_job(job_type='manual', user_id=student.pk)
            finally:
                connections.close_all()

        with patch('learning_analytics.scheduler.rebuild_user_analytics', side_effect=rebuild):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(worker)
                try:
                    self.assertTrue(entered.wait(5))
                    second = pool.submit(worker)
                    with self.assertRaises(FutureTimeout):
                        second.result(timeout=0.3)
                finally:
                    release.set()
                completed = first.result(timeout=5)
                other = second.result(timeout=5)
        self.assertEqual(completed.status, 'completed')
        self.assertEqual(other.pk, completed.pk)
        self.assertEqual(observed_users, [student.pk])
        persisted = LearningAuditJob.objects.get(pk=completed.pk)
        self.assertEqual(persisted.attempt_count, 1)
        self.assertEqual(persisted.status, 'completed')
