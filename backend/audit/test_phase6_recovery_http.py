"""Reference-only HTTP through ordinary Django startup and real PostgreSQL owners."""
from dataclasses import replace
from datetime import timedelta
import json
import os
import subprocess
import sys

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from ctf_backend.security_bootstrap import assemble_recovery_permissions
from data_security.adapters.persistence.models import ExportReport, QuotaExecution, RecoveryPermission
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import ActionPlan, Environment, ExecutionBinding, ObjectContext, QuotaReceipt
from data_security.tests.fixtures import examples
from resources.test_phase6_private_uploads import PrivateResourceUploadFixture
from tools.data_security import isolation
from users.models import CTFUser
from .models import AuthenticatedAuditEntry, SecurityAuditRecord


def recovery_http(test, requests, *, fault=None):
    """A fresh normal startup, not a test binding of the recovery callable."""
    env = isolation.clean_env()
    env.update(DATA_SECURITY_CONFIG=str(test.config_path), DATA_SECURITY_ISOLATED_TEST='1',
        DJANGO_SETTINGS_MODULE='tools.data_security.test_settings',
        DS_TEST_PG_PORT=os.environ['DS_TEST_PG_PORT'], DS_TEST_PG_SOCKET=os.environ['DS_TEST_PG_SOCKET'],
        ALLOWED_HOSTS='testserver,localhost', DEBUG='false')
    database = connection.settings_dict['NAME']
    test.assertEqual(database, 'test_ds_phase1_main')
    code = '''
import json,sys
from pathlib import Path
sys.path[:0] = [str(Path.cwd()), str(Path.cwd() / 'backend')]
from django.conf import settings
assert sys.argv[1] == 'test_ds_phase1_main'
settings.DATABASES['default']['NAME'] = sys.argv[1]
import django
django.setup()
from django.db import DatabaseError, connection
assert connection.settings_dict['NAME'] == 'test_ds_phase1_main'
from django.db.models.query import QuerySet
from data_security.adapters.persistence.models import ExportReport
from rest_framework.test import APIClient
from users.models import CTFUser
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import ProtectionError, ReasonCode
from unittest.mock import patch
from contextlib import nullcontext
fault = sys.argv[3]
original_append, original_exit = DjangoAuditSink.append, DjangoUnitOfWork.__exit__
def failed_append(self, *args):
    result = original_append(self, *args)
    assert not isinstance(result, ProtectionError)
    return ProtectionError(schema_version=ProtectionError.SCHEMA,
        code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='test/recovery-audit')
failed = False
def lost_confirmation(self, *args):
    global failed
    original_exit(self, *args)
    if not failed:
        failed = True
        raise RuntimeError('synthetic commit confirmation lost')
original_first = QuerySet.first
binding_reads = 0
def failed_binding_read(self):
    global binding_reads
    if self.model is ExportReport:
        binding_reads += 1
        raise DatabaseError('synthetic retained binding read failure')
    return original_first(self)
probe = (patch.object(DjangoAuditSink, 'append', failed_append) if fault == 'audit' else
         patch.object(DjangoUnitOfWork, '__exit__', lost_confirmation) if fault == 'confirmation' else
         patch.object(QuerySet, 'first', failed_binding_read) if fault == 'binding-database' else nullcontext())
responses = []
with probe:
    for item in json.loads(sys.argv[2]):
        client = APIClient()
        if item['user'] is not None:
            client.force_login(CTFUser.objects.get(pk=item['user']))
        method = getattr(client, item.get('method', 'post'))
        response = method('/api/data-security/exports/recovery/' + item['operation'] + '/',
                          item['body'], format='json', secure=True)
        responses.append({'status': response.status_code, 'body': response.json(),
                          'cache': response.get('Cache-Control')})
if fault == 'binding-database':
    assert binding_reads == len(responses), 'retained binding read fault was not reached'
print(json.dumps(responses))
connection.close()
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, database,
        json.dumps(requests), fault or 'none'], cwd=isolation.ROOT, env=env, capture_output=True, timeout=60)
    test.assertEqual(result.returncode, 0, 'ordinary recovery HTTP subprocess failed')
    return json.loads(result.stdout)


class RecoveryHTTPTests(PrivateResourceUploadFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.operator = CTFUser.objects.create_user(username='recovery-http-operator', role='student')
        self.teacher.user_permissions.add(*Permission.objects.filter(content_type__app_label='security_policies',
            codename__in=('add_recoverypermission', 'change_recoverypermission')))
        values = examples()
        self.binding = replace(values[ExecutionBinding], environment='evaluation',
            expires_at=timezone.now() + timedelta(minutes=5))
        self.context = replace(values[ObjectContext], environment=Environment.EVALUATION,
            object_version=self.binding.asset_version, authorization_ref=self.binding.authorization_id)
        self.reports = DjangoReportRepository(environment=Environment.EVALUATION)
        with DjangoUnitOfWork() as work:
            self.assertIs(self.reports.begin(values[ActionPlan], self.binding, self.context), True)
            work.commit()
        self.quota = DjangoQuotaPort(environment='evaluation', window_key='recovery-http', limit=20)
        self.assertIs(type(self.quota.reserve(self.binding)), QuotaReceipt)
        self.permissions = assemble_recovery_permissions(config_path=self.config_path)
        self.reference, _ = self.permissions.manage(user=self.teacher, binding=self.binding, operation='grant',
            grantee_id=self.operator.pk, expires_at=timezone.now() + timedelta(minutes=10),
            allow_release=True, allow_reconcile=True)
        self.config['export_recovery'] = {'window_key': 'recovery-http', 'limit': 20, 'ttl_seconds': 300}
        self.config_path.write_text(json.dumps(self.config))

    def request(self, operation='reconcile', **changes):
        return dict(user=self.operator.pk, operation=operation,
            body={'execution_ref': self.binding.execution_id, 'permission_ref': self.reference}, **changes)

    def state(self):
        from export_quota.models import QuotaBucket, QuotaReservation
        return tuple(list(model.objects.order_by('pk').values()) for model in (
            ExportReport, QuotaExecution, QuotaBucket, QuotaReservation, RecoveryPermission,
            SecurityAuditRecord, AuthenticatedAuditEntry))

    def test_default_closed_without_explicit_recovery_configuration(self):
        del self.config['export_recovery']
        self.config_path.write_text(json.dumps(self.config))
        before = self.state()
        response, = recovery_http(self, [self.request()])
        self.assertEqual(response['status'], 503)
        self.assertEqual(response['body'], {'code': 'SOURCE_NOT_APPROVED'})
        after = self.state()
        self.assertEqual(after[:5], before[:5])
        self.assertEqual(after[6], before[6])
        self.assertEqual(len(after[5]), len(before[5]) + 1)
        self.assertEqual(after[5][:-1], before[5])
        self.assertEqual({field: after[5][-1]['event'][field]
            for field in ('kind', 'outcome', 'reason', 'correlation_ref')},
            {'kind': 'protection', 'outcome': 'failed', 'reason': 'AUDIT_UNAVAILABLE',
             'correlation_ref': 'audit/legacy'})

    def test_reference_only_reconcile_fences_unknown_and_retries_without_new_effect(self):
        self.quota.reconcile(self.binding, None, 'synthetic/unknown')
        responses = recovery_http(self, [self.request('release'), self.request(), self.request()])
        self.assertEqual([item['status'] for item in responses], [403, 200, 200])
        self.assertEqual(responses[0]['body'], {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(responses[0]['cache'], 'no-store')
        self.assertEqual(responses[1]['body'], {
            'execution_ref': self.binding.execution_id, 'state': 'committed', 'delivered_records': 0,
            'network_delivery_confirmed': False})
        self.assertEqual(responses[2]['body'], responses[1]['body'])
        self.assertEqual(responses[1]['cache'], 'no-store')
        from export_quota.models import QuotaBucket, QuotaReservation
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 0, 0))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)

    def test_release_of_reserved_execution_is_not_delivery_or_network_confirmation(self):
        responses = recovery_http(self, [self.request('release'), self.request('release')])
        self.assertEqual([item['status'] for item in responses], [200, 200])
        self.assertEqual(responses[0]['body'], {
            'execution_ref': self.binding.execution_id, 'state': 'released', 'delivered_records': None,
            'network_delivery_confirmed': False})
        self.assertEqual(responses[0]['body'], responses[1]['body'])
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())

    def test_http_does_not_accept_binding_counts_evidence_or_extra_fields(self):
        requests = [self.request(method='get'), self.request('commit')]
        for extra in ({'binding': self.binding.to_wire()}, {'delivered_records': 0},
                      {'evidence_ref': 'client/claims-zero'}, {'success': True}, {'limit': 0}):
            request = self.request()
            request['body'].update(extra)
            requests.append(request)
        for body in ({}, {'execution_ref': self.binding.execution_id}, [],
                     {'execution_ref': True, 'permission_ref': self.reference}):
            request = self.request()
            request['body'] = body
            requests.append(request)
        before = self.state()
        responses = recovery_http(self, requests)
        self.assertEqual([item['status'] for item in responses], [405] + [400] * (len(requests) - 1))
        self.assertEqual(self.state(), before)

    def test_current_actor_and_exact_operation_permission_are_required(self):
        anonymous, other, wrong = self.request(), self.request(), self.request()
        anonymous['user'], other['user'] = None, self.teacher.pk
        wrong['body']['permission_ref'] = 'recovery/absent'
        before = self.state()
        responses = recovery_http(self, [anonymous, other, wrong])
        self.assertEqual([item['status'] for item in responses], [403, 403, 403])
        self.assertEqual(self.state(), before)
        RecoveryPermission.objects.update(allow_reconcile=False)
        before = self.state()
        response, = recovery_http(self, [self.request()])
        self.assertEqual(response['status'], 403)
        self.assertEqual(self.state(), before)

    def test_revoked_and_expired_permissions_do_not_change_unknown_capacity(self):
        self.quota.reconcile(self.binding, None, 'synthetic/unknown')
        for changes in ({'revoked_at': timezone.now()},
                        {'revoked_at': None, 'expires_at': timezone.now() - timedelta(seconds=1)}):
            RecoveryPermission.objects.update(**changes)
            before = self.state()
            response, = recovery_http(self, [self.request()])
            self.assertEqual(response['status'], 403)
            self.assertEqual(self.state(), before)

    def test_missing_or_altered_retained_intent_cannot_prove_zero(self):
        self.quota.reconcile(self.binding, None, 'synthetic/unknown')
        for document in (None, replace(self.binding, quantity=self.binding.quantity + 1).to_wire()):
            ExportReport.objects.update(binding_document=document)
            before = self.state()
            response, = recovery_http(self, [self.request()])
            self.assertEqual(response['status'], 409)
            self.assertEqual(response['body']['code'], 'DELIVERY_UNKNOWN' if document is None else 'REPORT_MISMATCH')
            self.assertEqual(self.state(), before)
        absent = self.request()
        absent['body']['execution_ref'] = 'execution/absent'
        response, = recovery_http(self, [absent])
        self.assertEqual(response['body'], {'code': 'DELIVERY_UNKNOWN'})

    def test_audit_failure_rolls_back_report_fence_quota_and_event(self):
        self.quota.reconcile(self.binding, None, 'synthetic/unknown')
        before = self.state()
        response, = recovery_http(self, [self.request()], fault='audit')
        self.assertEqual(response['status'], 409)
        self.assertEqual(response['body'], {'code': 'AUDIT_UNAVAILABLE'})
        self.assertEqual(self.state(), before)

    def test_lost_commit_confirmation_is_unknown_then_reconciles_existing_effect(self):
        self.quota.reconcile(self.binding, None, 'synthetic/unknown')
        responses = recovery_http(self, [self.request(), self.request()], fault='confirmation')
        self.assertEqual([item['status'] for item in responses], [409, 200])
        self.assertEqual(responses[0]['body'], {'code': 'DELIVERY_UNKNOWN'})
        self.assertEqual(responses[1]['body']['delivered_records'], 0)
        from export_quota.models import QuotaBucket, QuotaReservation
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaBucket.objects.get().settled, 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)
