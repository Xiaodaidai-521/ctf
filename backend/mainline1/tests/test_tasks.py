"""Sequential repository-contract tests, NOT persistence or PostgreSQL concurrency tests."""
import unittest
from dataclasses import replace

from mainline1.parsing import InputError, PARSING_ERROR_CODES
from mainline1.tasks import ParseTasks, dump_run, restore_run


class RepositoryDouble:
    """Store serialized values to avoid shared mutable objects; memory only."""
    def __init__(self):
        self.rows = {}
        self.keys = {}
        self.reject_next_update = False

    def create_unique(self, candidate):
        if candidate.key not in self.keys:
            self.keys[candidate.key] = candidate.run_id
            self.rows[candidate.run_id] = dump_run(candidate)
        return self.get(self.keys[candidate.key])

    def get(self, run_id):
        return restore_run(self.rows[run_id])

    def compare_and_swap(self, expected_revision, replacement):
        if self.reject_next_update:
            self.reject_next_update = False
            return False
        if self.get(replacement.run_id).revision != expected_revision:
            return False
        self.rows[replacement.run_id] = dump_run(replacement)
        return True


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.repo = RepositoryDouble()
        self.tasks = ParseTasks(self.repo)
        self.args = dict(domain='synthetic-domain', environment='test', evaluation='synthetic-eval',
                         principal='test-owner', idempotency_key='key',
                         snapshot={'asset_version_id': 'v1', 'parser_config': {'normalization': 'identity-v1'}, 'scope': [1, 2]})

    def assertCode(self, code, function, *args, **kwargs):
        with self.assertRaises(InputError) as caught:
            function(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def claimed(self, **kwargs):
        run = self.tasks.create(**dict(self.args, **kwargs))
        return self.tasks.claim(run.run_id, now=10, lease_seconds=20)

    def fail(self, run):
        return self.tasks.finish(run.run_id, token=run.attempts[-1].token, now=12, error_code='PARSE_FAILED')

    def test_same_request_same_key_returns_same_run(self):
        first = self.tasks.create(**self.args)
        self.assertEqual(first, self.tasks.create(**self.args))
        self.assertEqual(len(self.repo.rows), 1)

    def test_same_key_different_request_conflicts(self):
        self.tasks.create(**self.args)
        self.assertCode('IDEMPOTENCY_CONFLICT', self.tasks.create, **dict(self.args, snapshot={'asset_version_id':'v2'}))

    def test_scope_and_rescan_key_are_separate_runs(self):
        first = self.tasks.create(**self.args)
        for changed in (dict(domain='second-domain'), dict(environment='development'), dict(evaluation='second-evaluation'), dict(principal='second-user'), dict(idempotency_key='rescan')):
            self.assertNotEqual(first.run_id, self.tasks.create(**dict(self.args, **changed)).run_id)

    def test_snapshot_roundtrip_and_caller_mutation_do_not_change_saved_data(self):
        run = self.tasks.create(**self.args)
        self.args['snapshot']['scope'].append(100)
        loaded = restore_run(dump_run(run))
        self.assertEqual(run, loaded)
        self.assertNotIn('100', loaded.snapshot_json)

    def test_queue_cancel_is_idempotent_and_cannot_be_claimed(self):
        run = self.tasks.create(**self.args)
        cancelled = self.tasks.cancel(run.run_id)
        self.assertEqual(cancelled.status, 'cancelled')
        self.assertEqual(cancelled, self.tasks.cancel(run.run_id))
        self.assertCode('TASK_NOT_QUEUED', self.tasks.claim, run.run_id, now=1, lease_seconds=10)

    def test_running_cancel_before_finish_prevents_publication(self):
        run = self.claimed()
        pending = self.tasks.cancel(run.run_id)
        self.assertEqual(pending.status, 'running')
        self.assertTrue(pending.cancel_requested)
        done = self.tasks.finish(run.run_id, token=run.attempts[-1].token, now=11, parsed_ref='private:parsed')
        self.assertEqual(done.status, 'cancelled')
        self.assertIsNone(done.parsed_ref)
        self.assertEqual(done.detection_status, 'not_run')

    def test_parse_finish_first_rejects_cancel_and_is_not_scan_success(self):
        run = self.claimed()
        done = self.tasks.finish(run.run_id, token=run.attempts[-1].token, now=11, parsed_ref='private:parsed')
        self.assertEqual(done.status, 'succeeded')
        self.assertEqual(done.result_kind, 'parsed_asset')
        self.assertEqual(done.scan_quality, 'unavailable')
        self.assertCode('TASK_TERMINAL', self.tasks.cancel, run.run_id)
        self.assertCode('TASK_NOT_RETRYABLE', self.tasks.retry, run.run_id, expected_attempt=1, idempotency_key='retry')

    def test_retry_uses_new_attempt_and_old_failure_cannot_overwrite(self):
        first = self.claimed(); self.fail(first)
        queued = self.tasks.retry(first.run_id, expected_attempt=1, idempotency_key='retry')
        second = self.tasks.claim(first.run_id, now=20, lease_seconds=20)
        self.assertEqual(second.run_id, first.run_id)
        self.assertEqual(second.attempts[0].status, 'failed')
        self.assertNotEqual(second.attempts[-1].token, first.attempts[-1].token)
        self.assertEqual(second.request_hash, queued.request_hash)
        self.assertCode('STALE_ATTEMPT', self.tasks.finish, first.run_id, token=first.attempts[-1].token, now=21, error_code='PARSE_FAILED')
        self.assertEqual(self.repo.get(first.run_id), second)

    def test_retry_idempotency_and_limit(self):
        run = self.claimed();self.fail(run)
        queued = self.tasks.retry(run.run_id, expected_attempt=1, idempotency_key='retry')
        self.assertEqual(queued, self.tasks.retry(run.run_id, expected_attempt=1, idempotency_key='retry'))
        self.assertCode('IDEMPOTENCY_CONFLICT', self.tasks.retry, run.run_id, expected_attempt=2, idempotency_key='retry')
        second = self.tasks.claim(run.run_id, now=10, lease_seconds=20);self.fail(second)
        self.assertCode('RETRY_LIMIT', self.tasks.retry, run.run_id, expected_attempt=2, idempotency_key='retry2')

    def test_expired_worker_cannot_write_and_can_be_retried(self):
        run = self.claimed()
        self.assertCode('STALE_ATTEMPT', self.tasks.finish, run.run_id, token=run.attempts[-1].token, now=30, parsed_ref='private:old')
        failed = self.tasks.expire(run.run_id, now=30)
        self.assertEqual(failed.attempts[-1].status, 'expired')
        self.tasks.retry(run.run_id, expected_attempt=1, idempotency_key='recover')
        second = self.tasks.claim(run.run_id, now=31, lease_seconds=10)
        self.assertCode('STALE_ATTEMPT', self.tasks.finish, run.run_id, token=run.attempts[-1].token, now=32, parsed_ref='private:old')
        self.assertEqual(self.repo.get(run.run_id), second)

    def test_heartbeat_checks_owner_and_expiry(self):
        run = self.claimed()
        updated = self.tasks.heartbeat(run.run_id, token=run.attempts[-1].token, now=20, lease_seconds=20)
        self.assertEqual(updated.attempts[-1].lease_expires, 40)
        self.assertCode('STALE_ATTEMPT', self.tasks.heartbeat, run.run_id, token='old', now=21, lease_seconds=20)
        self.tasks.cancel(run.run_id)
        self.assertCode('TASK_CANCELLED', self.tasks.heartbeat, run.run_id, token=run.attempts[-1].token, now=21, lease_seconds=20)

    def test_cancelled_expiry_is_not_retried(self):
        run = self.claimed();self.tasks.cancel(run.run_id)
        end = self.tasks.expire(run.run_id, now=40)
        self.assertEqual(end.status, 'cancelled')
        self.assertCode('TASK_NOT_RETRYABLE', self.tasks.retry, run.run_id, expected_attempt=1, idempotency_key='retry')

    def test_repository_cas_conflict_is_not_silently_overwritten(self):
        run = self.tasks.create(**self.args)
        self.repo.reject_next_update = True
        self.assertCode('TASK_VERSION_CONFLICT', self.tasks.claim, run.run_id, now=1, lease_seconds=1)
        self.assertEqual(self.repo.get(run.run_id), run)

    def test_no_success_without_private_result_and_no_raw_error_persistence(self):
        run = self.claimed()
        self.assertCode('TASK_INPUT_INVALID', self.tasks.finish, run.run_id, token=run.attempts[-1].token, now=12)
        self.assertCode('TASK_INPUT_INVALID', self.tasks.finish, run.run_id, token=run.attempts[-1].token, now=12, error_code='raw secret exception')

    def test_progress_unknown_total_and_stale_owner(self):
        run = self.claimed()
        args = dict(token=run.attempts[-1].token, now=12, stage='parse', processed_count=3, total_count=None)
        next_run = self.tasks.record_progress(run.run_id, **args)
        self.assertIsNone(next_run.attempts[-1].progress_ratio)
        next_run = self.tasks.record_progress(run.run_id, **dict(args, processed_count=4, total_count=10))
        self.assertEqual(next_run.attempts[-1].progress_ratio, .4)
        self.assertCode('PROGRESS_INVALID', self.tasks.record_progress, run.run_id, **dict(args, processed_count=2, total_count=10))
        self.assertCode('STALE_ATTEMPT', self.tasks.record_progress, run.run_id, **dict(args, token='old'))

    def test_all_sanitized_parser_errors_can_be_recorded(self):
        for code in PARSING_ERROR_CODES:
            with self.subTest(code=code):
                run = self.claimed(idempotency_key=code)
                result = self.tasks.finish(run.run_id, token=run.attempts[-1].token, now=11, error_code=code)
                self.assertEqual(result.attempts[-1].error_code, code)
                self.assertIsNone(result.parsed_ref)

    def test_old_success_cannot_overwrite_new_success(self):
        first = self.claimed();self.fail(first)
        self.tasks.retry(first.run_id, expected_attempt=1, idempotency_key='retry')
        second = self.tasks.claim(first.run_id, now=20, lease_seconds=20)
        result = self.tasks.finish(second.run_id, token=second.attempts[-1].token, now=21, parsed_ref='private:new')
        self.assertCode('STALE_ATTEMPT', self.tasks.finish, first.run_id, token=first.attempts[-1].token, now=22, parsed_ref='private:old')
        self.assertEqual(self.repo.get(first.run_id), result)


if __name__ == '__main__':
    unittest.main()
