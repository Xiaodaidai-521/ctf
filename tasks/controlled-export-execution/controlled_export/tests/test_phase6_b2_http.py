"""Explicit executor startup and prepared/unknown HTTP states on isolated PostgreSQL."""
import json
import os
import subprocess
import sys
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from controlled_export.models import DeliveryAttempt, ExecutionAttempt, ExportExecution, OutboxEvent, ProtectedArtifact, ShareGrant
from controlled_export_service.security_bootstrap import start_application
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject
from data_security.contracts import BASELINE_LIMITS
from data_security.tests.phase3_fixtures import configuration
from tools.data_security import isolation

from .helpers import AUTHORITY_SECRET, INTERNAL_KEY, authorization_for, csv_bytes, csv_plan


class ExecutorPrivateHTTPTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        files = configuration(providers=())
        self.path, original, refs, _, _ = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        self.root, self.legacy = self.path.parent / 'sealed', self.path.parent / 'legacy'
        self.root.mkdir(mode=0o700)
        self.legacy.mkdir(mode=0o700)
        self.config = {'schema_version': 'ds.executor-preparation.v1', 'environment': 'evaluation',
            'key_manifest': original['key_manifest'], 'data_key': refs['data_key'].to_wire(),
            'private_root': str(self.root), 'project_ref': 'executor/b2-http', 'limits': BASELINE_LIMITS.to_wire()}
        self.path.write_text(json.dumps(self.config))
        configured = override_settings(CONTROLLED_EXPORT_PRIVATE_CONFIG=str(self.path),
            CONTROLLED_EXPORT_PRIVATE_MODE=True, CONTROLLED_EXPORT_PRIVATE_PREPARATION=None,
            CONTROLLED_EXPORT_PRIVATE_ROOT=self.legacy, CONTROLLED_EXPORT_ENVIRONMENT='evaluation',
            CONTROLLED_EXPORT_INTERNAL_KEY=INTERNAL_KEY, EXECUTION_AUTHORITY_HMAC_SECRET=AUTHORITY_SECRET,
            SECRET_KEY='b2-synthetic-framework', ALLOWED_HOSTS=['testserver'], FILE_UPLOAD_MAX_MEMORY_SIZE=1)
        configured.enable()
        self.addCleanup(configured.disable)
        start_application()
        self.client = APIClient()
        self.content, self.plan = csv_bytes(), csv_plan()
        self.authorization, self.signature = authorization_for(self.content, self.plan)
        self.headers = {'HTTP_X_INTERNAL_AUTHORIZATION': 'Bearer ' + INTERNAL_KEY,
            'HTTP_X_CALLER_ID': 'risk-service'}

    def execute(self):
        with patch('controlled_export.services.PrivateStorage', side_effect=AssertionError('legacy storage')), \
             patch('django.core.files.uploadhandler.TemporaryUploadedFile', side_effect=AssertionError('ordinary spool')):
            return self.client.post(reverse('controlled-export-execute'), {
                'authorization': json.dumps(self.authorization), 'plan': json.dumps(self.plan),
                'file': SimpleUploadedFile('synthetic.csv', self.content, content_type='text/csv')},
                format='multipart', HTTP_X_AUTHORIZATION_SIGNATURE=self.signature, HTTP_IDEMPOTENCY_KEY='b2-private-http',
                **self.headers)

    def observe(self, *, reconcile=False, caller='risk-service'):
        url = reverse('controlled-export-preparation', kwargs={'execution_id': self.authorization['execution_id']})
        headers = {**self.headers, 'HTTP_X_CALLER_ID': caller}
        return (self.client.generic('POST', url, b'', content_type='application/octet-stream', **headers)
                if reconcile else self.client.get(url, **headers))

    def assert_no_delivery(self):
        self.assertFalse(ProtectedArtifact.objects.exists())
        self.assertFalse(ShareGrant.objects.exists())
        self.assertFalse(DeliveryAttempt.objects.exists())
        self.assertFalse(OutboxEvent.objects.filter(event_type='execution.completed').exists())
        self.assertFalse(PrivateObject.objects.filter(state='published').exists())
        self.assertEqual(list(self.legacy.iterdir()), [])

    def test_http_prepares_ciphertext_and_replay_does_not_publish_or_satisfy_delivery(self):
        first = self.execute()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data['status'], 'prepared')
        self.assertIsNone(first.data['completed_at'])
        self.assertIsNone(first.data['output_asset_version_id'])
        self.assertTrue(all(item['status'] == 'not_satisfied' for item in first.data['obligation_results']))
        self.assertEqual(PrivateFileOperation.objects.get().state, 'prepared')
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        replay = self.execute()
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertTrue(replay.data['idempotent_replay'])
        self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, before)
        self.assertEqual((ExportExecution.objects.count(), ExecutionAttempt.objects.count(), PrivateObject.objects.count()), (1, 1, 1))
        self.assert_no_delivery()

    def test_observation_and_positive_reconciliation_remain_prepared_not_delivered(self):
        self.assertEqual(self.execute().status_code, 201)
        observed = self.observe()
        self.assertEqual(observed.status_code, 200, observed.data)
        self.assertFalse(observed.data['candidate_verified'])
        reconciled = self.observe(reconcile=True)
        self.assertEqual(reconciled.status_code, 200, reconciled.data)
        self.assertTrue(reconciled.data['candidate_verified'])
        self.assertEqual(reconciled.data['status'], 'prepared')
        self.assertNotIn('private_candidate', reconciled.data)
        self.assertNotIn('stored', reconciled.data)
        self.assert_no_delivery()

    def test_original_service_ownership_and_reference_only_body_are_required(self):
        self.assertEqual(self.execute().status_code, 201)
        self.assertEqual(self.observe(caller='other-service').status_code, 404)
        url = reverse('controlled-export-preparation', kwargs={'execution_id': self.authorization['execution_id']})
        response = self.client.post(url, {'status': 'succeeded', 'candidate': {}}, format='json', **self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error_code'], 'PREPARATION_REFERENCE_ONLY')
        self.assertEqual(ExportExecution.objects.get().state, 'prepared')
        self.assert_no_delivery()

    def test_fsync_before_candidate_row_recovers_only_the_retained_intention(self):
        with patch.object(PrivateObject.objects, 'get_or_create', side_effect=DatabaseError('synthetic row failure')):
            failed = self.execute()
        self.assertEqual(failed.status_code, 409, failed.data)
        self.assertEqual(failed.data['error_code'], 'DELIVERY_UNKNOWN')
        self.assertEqual(ExportExecution.objects.get().state, 'repair_required')
        self.assertEqual(ExecutionAttempt.objects.get().status, 'unknown')
        self.assertFalse(PrivateObject.objects.exists())
        self.assertEqual(PrivateFileOperation.objects.get().state, 'preparing')
        before = {path.name: path.read_bytes() for path in self.root.glob('*.sealed')}
        result = self.observe(reconcile=True)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertTrue(result.data['candidate_verified'])
        self.assertEqual(result.data['status'], 'repair_required')
        self.assertEqual(PrivateFileOperation.objects.get().state, 'prepared')
        self.assertEqual({path.name: path.read_bytes() for path in self.root.glob('*.sealed')}, before)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')
        self.assert_no_delivery()

    def test_missing_intention_or_ciphertext_is_unknown_not_zero_effects(self):
        self.assertEqual(self.execute().status_code, 201)
        PrivateFileOperation.objects.all().delete()
        result = self.observe(reconcile=True)
        self.assertEqual(result.status_code, 409, result.data)
        self.assertEqual(result.data['error_code'], 'DELIVERY_UNKNOWN')
        self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)
        self.assertEqual(ExportExecution.objects.get().state, 'prepared')
        self.assert_no_delivery()

    def test_formal_http_share_and_legacy_delivery_routes_remain_closed(self):
        self.assertEqual(self.execute().status_code, 201)
        response = self.client.post(reverse('controlled-export-share-create'),
            {'execution_id': self.authorization['execution_id']}, format='json', **self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b'')
        self.assert_no_delivery()

    def test_real_commit_confirmation_loss_is_observable_without_success_promotion(self):
        commit, lost = connection.commit, False

        def commit_then_lose():
            nonlocal lost
            should_lose = not lost and ExportExecution.objects.filter(state='prepared').exists()
            result = commit()
            if should_lose:
                lost = True
                raise DatabaseError('synthetic post-commit confirmation loss')
            return result

        with patch.object(connection, 'commit', side_effect=commit_then_lose), self.assertRaises(DatabaseError):
            self.execute()
        self.assertTrue(lost)
        self.assertEqual(self.observe(reconcile=True).data['status'], 'prepared')
        self.assertEqual(self.execute().status_code, 200)
        self.assertEqual((ExportExecution.objects.count(), ExecutionAttempt.objects.count(), PrivateObject.objects.count()), (1, 1, 1))
        self.assert_no_delivery()

    def test_ordinary_executor_startup_binds_configuration_and_http_preparation(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_export')
        env = isolation.clean_env()
        env.update(DATA_SECURITY_ISOLATED_TEST='1', DJANGO_SETTINGS_MODULE='tools.data_security.export_test_settings',
            DS_TEST_PG_PORT=os.environ['DS_TEST_PG_PORT'], DS_TEST_PG_SOCKET=os.environ['DS_TEST_PG_SOCKET'],
            CONTROLLED_EXPORT_PRIVATE_CONFIG=str(self.path), CONTROLLED_EXPORT_PRIVATE_ROOT=str(self.legacy),
            CONTROLLED_EXPORT_DJANGO_SECRET='b2-synthetic-framework', CONTROLLED_EXPORT_INTERNAL_KEY=INTERNAL_KEY,
            EXECUTION_AUTHORITY_HMAC_SECRET=AUTHORITY_SECRET, CONTROLLED_EXPORT_ALLOWED_HOSTS='testserver')
        code = '''
import json,sys
from pathlib import Path
sys.path[:0] = [str(Path.cwd()), str(Path.cwd() / 'backend'), str(Path.cwd() / 'tasks/controlled-export-execution')]
from django.conf import settings
settings.DATABASES['default']['NAME'] = 'test_ds_phase1_export'
import django
django.setup()
from controlled_export.tests.test_phase6_b2_http import ordinary_executor_http
print(json.dumps(ordinary_executor_http()))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd=isolation.ROOT,
            env=env, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace')[-3000:])
        self.assertEqual(json.loads(result.stdout), {'upload': 201, 'status': 'prepared',
            'reconcile': 200, 'candidate_verified': True, 'share': 503})
        self.assert_no_delivery()


def ordinary_executor_http():
    client, content, plan = APIClient(), csv_bytes(), csv_plan()
    authorization, signature = authorization_for(content, plan)
    headers = {'HTTP_X_INTERNAL_AUTHORIZATION': 'Bearer ' + INTERNAL_KEY, 'HTTP_X_CALLER_ID': 'risk-service'}
    uploaded = client.post(reverse('controlled-export-execute'), {'authorization': json.dumps(authorization),
        'plan': json.dumps(plan), 'file': SimpleUploadedFile('synthetic.csv', content, content_type='text/csv')},
        format='multipart', HTTP_X_AUTHORIZATION_SIGNATURE=signature, HTTP_IDEMPOTENCY_KEY='b2-child', **headers)
    assert uploaded.status_code == 201, uploaded.data
    url = reverse('controlled-export-preparation', kwargs={'execution_id': authorization['execution_id']})
    reconciled = client.generic('POST', url, b'', content_type='application/octet-stream', **headers)
    assert reconciled.status_code == 200, reconciled.data
    share = client.post(reverse('controlled-export-share-create'), {}, format='json', **headers)
    return {'upload': uploaded.status_code, 'status': uploaded.data['status'], 'reconcile': reconciled.status_code,
        'candidate_verified': reconciled.data['candidate_verified'], 'share': share.status_code}
