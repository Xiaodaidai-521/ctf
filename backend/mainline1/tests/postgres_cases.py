"""Real PostgreSQL transaction tests, deliberately outside unittest test_ discovery."""
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections
from django.test import TransactionTestCase

from mainline1.models import ParseAttempt, ParsedArtifact, ParseRun
from mainline1.parsing import AssetRef, InputError, parse_table
from mainline1.repository import DjangoRunRepository
from mainline1.tasks import ParseTasks
from mainline1.worker import execute_one, parse_snapshot


class PostgresTasks(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.repo = DjangoRunRepository()
        self.tasks = ParseTasks(self.repo)
        self.content = b'name,value\nsynthetic,42\n'
        self.asset = AssetRef('synthetic-v1', 'domain-test', 'sha256:' + hashlib.sha256(self.content).hexdigest(),
                              'csv', len(self.content), 'private:synthetic')
        self.args = dict(domain='domain-test', environment='test', evaluation='synthetic',
                         principal='test-principal', idempotency_key='key', snapshot=parse_snapshot(self.asset))

    def code(self, expected, fn, *args, **kwargs):
        with self.assertRaises(InputError) as error:
            fn(*args, **kwargs)
        self.assertEqual(error.exception.code, expected)

    def race(self, action):
        gate = threading.Barrier(2)
        def contender():
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    pid = cursor.fetchone()[0]
                repo = DjangoRunRepository()
                gate.wait(timeout=10)
                try:
                    return pid, action(repo)
                except InputError as exc:
                    return pid, exc.code
            finally:
                connections['default'].close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(contender) for _ in range(2)]
            outcomes = [job.result(timeout=20) for job in jobs]
        self.assertNotEqual(outcomes[0][0], outcomes[1][0])
        return [x[1] for x in outcomes]

    def test_concurrent_unique_create_and_conflicting_replay(self):
        results = self.race(lambda repo: ParseTasks(repo).create(**self.args).run_id)
        self.assertEqual(results[0], results[1])
        self.assertEqual(ParseRun.objects.count(), 1)
        self.code('IDEMPOTENCY_CONFLICT', self.tasks.create, **dict(self.args, snapshot={'changed': True}))

    def test_concurrent_claim_has_one_attempt(self):
        run = self.tasks.create(**self.args)
        results = self.race(lambda repo: ParseTasks(repo).claim(run.run_id, now=100, lease_seconds=20).status)
        self.assertEqual(results.count('running'), 1)
        self.assertTrue(any(r in ('TASK_NOT_QUEUED', 'TASK_VERSION_CONFLICT') for r in results))
        self.assertEqual(ParseAttempt.objects.count(), 1)

    def test_database_reconnect_recovery_retry_and_old_token_fencing(self):
        run = self.tasks.create(**self.args)
        first = self.tasks.claim(run.run_id, now=100, lease_seconds=1)
        connection.close()
        restarted = DjangoRunRepository()
        self.assertEqual(restarted.get(run.run_id), first)
        self.assertEqual(restarted.recover_expired(now=102), [run.run_id])
        tasks = ParseTasks(restarted)
        tasks.retry(run.run_id, expected_attempt=1, idempotency_key='retry-1')
        second = tasks.claim(run.run_id, now=103, lease_seconds=20)
        self.code('STALE_ATTEMPT', tasks.finish, run.run_id, token=first.attempts[-1].token,
                  now=104, parsed_ref='private:obsolete')
        self.code('STALE_ATTEMPT', tasks.finish, run.run_id, token=first.attempts[-1].token,
                  now=104, error_code='PARSE_FAILED')
        tasks.finish(run.run_id, token=second.attempts[-1].token, now=104, error_code='PARSE_FAILED')
        self.code('RETRY_LIMIT', tasks.retry, run.run_id, expected_attempt=2, idempotency_key='retry-2')
        self.assertEqual(ParseAttempt.objects.count(), 2)
        self.assertEqual(restarted.get(run.run_id).snapshot_json, run.snapshot_json)

    def test_worker_persists_private_result_and_no_detection(self):
        run = self.tasks.create(**self.args)
        content = self.content
        class SyntheticOwner:
            def open_version(owner, ref, *, principal, domain_id):
                self.assertEqual((ref, principal, domain_id), (self.asset, 'test-principal', 'domain-test'))
                return io.BytesIO(content)
        result = execute_one(self.repo, run.run_id, SyntheticOwner(), clock=lambda: 100)
        connection.close()
        saved = DjangoRunRepository().get(run.run_id)
        self.assertEqual(saved, result)
        self.assertEqual(saved.status, 'succeeded')
        self.assertEqual(saved.detection_status, 'not_run')
        artifact = ParsedArtifact.objects.get(run_id=run.run_id)
        self.assertEqual(saved.parsed_ref, f'private:{artifact.pk}')
        self.assertEqual(artifact.payload['cells'][0]['source_text'], 'synthetic')
        self.assertEqual(json.loads(artifact.payload['coverage_json'])['semantic']['status'], 'not_run')

    def test_artifact_failure_rolls_back_success_and_attempt(self):
        run = self.tasks.create(**self.args)
        active = self.tasks.claim(run.run_id, now=100, lease_seconds=20)
        with patch('django.db.models.query.QuerySet.create', side_effect=RuntimeError('synthetic write failure')):
            with self.assertRaises(RuntimeError):
                self.repo.publish(run.run_id, token=active.attempts[-1].token, now=101,
                                  result=parse_table(self.content, self.asset))
        self.assertEqual(self.repo.get(run.run_id), active)
        self.assertEqual(ParsedArtifact.objects.count(), 0)

    def test_concurrent_cancel_and_publish_are_atomic(self):
        run = self.tasks.create(**self.args)
        active = self.tasks.claim(run.run_id, now=100, lease_seconds=20)
        parsed = parse_table(self.content, self.asset)
        gate = threading.Barrier(2)
        def operation(cancel):
            try:
                repo = DjangoRunRepository()
                gate.wait(timeout=10)
                try:
                    if cancel:
                        return ParseTasks(repo).cancel(run.run_id).status
                    return repo.publish(run.run_id, token=active.attempts[-1].token, now=101, result=parsed).status
                except InputError as exc:
                    return exc.code
            finally:
                connections['default'].close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(operation, flag) for flag in (True, False)]
            [job.result(timeout=20) for job in jobs]
        final = self.repo.get(run.run_id)
        self.assertIn(final.status, ('succeeded', 'cancelled'))
        self.assertEqual(ParsedArtifact.objects.count(), int(final.status == 'succeeded'))
        self.assertEqual(final.cancel_requested, final.status == 'cancelled')

    def test_cancel_before_publish_has_no_artifact(self):
        run = self.tasks.create(**self.args)
        active = self.tasks.claim(run.run_id, now=100, lease_seconds=20)
        self.tasks.cancel(run.run_id)
        final = self.repo.publish(run.run_id, token=active.attempts[-1].token, now=101,
                                  result=parse_table(self.content, self.asset))
        self.assertEqual(final.status, 'cancelled')
        self.assertEqual(ParsedArtifact.objects.count(), 0)

    def test_worker_failure_contains_only_code(self):
        run = self.tasks.create(**self.args)
        class BrokenOwner:
            def open_version(owner, *args, **kwargs):
                raise RuntimeError('SECRET synthetic source diagnostic')
        final = execute_one(self.repo, run.run_id, BrokenOwner(), clock=lambda: 100)
        self.assertEqual(final.status, 'failed')
        self.assertEqual(final.attempts[-1].error_code, 'ASSET_UNAVAILABLE')
        self.assertNotIn('SECRET', str(ParseRun.objects.get(pk=run.run_id).state))
        self.assertEqual(ParsedArtifact.objects.count(), 0)

    def test_repository_refuses_snapshot_mutation(self):
        run = self.tasks.create(**self.args)
        self.code('TASK_INPUT_INVALID', self.repo.compare_and_swap, run.revision,
                  replace(run, revision=2, snapshot_json='{}'))
        self.assertEqual(self.repo.get(run.run_id), run)

    def test_changed_parser_version_fails_without_opening_asset(self):
        snapshot = dict(self.args['snapshot'], parser_version='obsolete-parser')
        run = self.tasks.create(**dict(self.args, snapshot=snapshot))
        final = execute_one(self.repo, run.run_id, object(), clock=lambda: 100)
        self.assertEqual(final.status, 'failed')
        self.assertEqual(final.attempts[-1].error_code, 'CONFIG_INVALID')

    def test_publish_rejects_result_from_different_parser_configuration(self):
        run = self.tasks.create(**self.args)
        active = self.tasks.claim(run.run_id, now=100, lease_seconds=20)
        parsed = replace(parse_table(self.content, self.asset), config_hash='sha256:wrong')
        self.code('CONFIG_INVALID', self.repo.publish, run.run_id,
                  token=active.attempts[-1].token, now=101, result=parsed)
        self.assertEqual(self.repo.get(run.run_id), active)
        self.assertEqual(ParsedArtifact.objects.count(), 0)

    def test_new_python_process_reads_persisted_attempt(self):
        run = self.tasks.create(**self.args)
        active = self.tasks.claim(run.run_id, now=100, lease_seconds=20)
        script = '''import json, os, django
from django.conf import settings
settings.DATABASES['default']['NAME'] = os.environ['ML1_CHILD_DATABASE']
django.setup()
from mainline1.repository import DjangoRunRepository
r = DjangoRunRepository().get(os.environ['ML1_CHILD_RUN'])
print(json.dumps([r.run_id, r.status, len(r.attempts), r.attempts[-1].attempt_id]))
'''
        env = dict(os.environ, DJANGO_SETTINGS_MODULE='mainline1.test_settings',
                   ML1_CHILD_DATABASE=connection.settings_dict['NAME'], ML1_CHILD_RUN=run.run_id)
        child = subprocess.run([sys.executable, '-B', '-c', script], env=env,
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout), [run.run_id, 'running', 1, active.attempts[-1].attempt_id])

    def test_management_command_fails_closed_without_owner(self):
        with self.assertRaisesMessage(CommandError, 'PRIVATE_SOURCE_NOT_CONFIGURED'):
            call_command('run_parse_worker')
