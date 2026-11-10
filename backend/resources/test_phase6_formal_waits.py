"""6-F02: real owner deadlines across ordinary-startup PostgreSQL waits.

Issue waits in prepare_execution, not claim: the adapter retains prepare's bucket
lock through claim in the same transaction. No transaction or capability is
replaced to manufacture a second wait there. Only persisted deadlines are
shortened; clocks, current owners and the actual lock-taking methods stay real.
"""
from contextlib import ExitStack
from datetime import timedelta
import hashlib
import json
import os
import select
import subprocess
import sys
import time
from unittest.mock import patch

from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuditEvent, AuditLedgerEntry, AuditLedgerLock, AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution
from data_security.contracts import AuditReceipt, BoundedPayload, DeliveryReceipt, EventKind, ProtectionError
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.contracts import QualityState
from export_risk.models import ColumnRiskPermission, EventOutbox, ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision
from tools.data_security import isolation
from users.models import CTFUser

from .models import ExportSource, ExportSourcePermission, Resource
from .test_phase6_formal_delivery import EXPECTED
from .test_phase6_formal_fixtures import FormalResourceFixture, formal_call


_CHILD = '''
import json,sys
from pathlib import Path
sys.path[:0] = [str(Path.cwd()), str(Path.cwd() / 'backend')]
from django.conf import settings
assert sys.argv[1] == 'test_ds_phase1_main'
settings.DATABASES['default']['NAME'] = sys.argv[1]
import django
from django.db import connection, connections
try:
    django.setup()
    assert connection.vendor == 'postgresql'
    assert connection.settings_dict['NAME'] == 'test_ds_phase1_main'
    from resources.test_phase6_formal_waits import invoke_wait
    print(json.dumps(invoke_wait(sys.argv[2], json.loads(sys.argv[3]))), flush=True)
finally:
    connections.close_all()
'''


def _spawn_wait(test, stage):
    # Same clean environment/settings/network fence as formal_call, with two
    # pipe milestones so startup and earlier authenticated reads cannot be the wait.
    env = isolation.clean_env()
    env.update(DATA_SECURITY_CONFIG=str(test.config_path), DATA_SECURITY_ISOLATED_TEST='1',
        DJANGO_SETTINGS_MODULE='tools.data_security.test_settings',
        DS_TEST_PG_PORT=os.environ['DS_TEST_PG_PORT'], DS_TEST_PG_SOCKET=os.environ['DS_TEST_PG_SOCKET'],
        ALLOWED_HOSTS='testserver,localhost', DEBUG='false')
    test.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
    return subprocess.Popen([sys.executable, '-I', '-B', '-c', _CHILD, 'test_ds_phase1_main', stage,
        json.dumps({'user': test.teacher.pk, 'source_ref': test.source_ref, 'permission_ref': test.permission_ref})],
        cwd=isolation.ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)


def _message(test, child):
    readable, _, _ = select.select([child.stdout], [], [], 30)
    test.assertTrue(readable, 'ordinary-startup child did not reach the wait milestone')
    line = child.stdout.readline()
    if not line:
        test.fail('ordinary-startup child exited before the wait: ' + child.stderr.read()[-3000:])
    return json.loads(line)


def invoke_wait(stage, fields):
    """Called only after django.setup; wrap genuine methods, not B capabilities."""
    from data_security.adapters.django.export_delivery import export_delivery
    from data_security.adapters.persistence.audit import DjangoAuditSink
    from data_security.adapters.persistence.export_delivery import DjangoResourceExports
    from data_security.adapters.persistence.private_store import DjangoPrivateStore
    from data_security.adapters.persistence.quota import DjangoQuotaPort
    from data_security.adapters.persistence.report_records import DjangoReportRepository
    from data_security.adapters.persistence.risk import DjangoRiskPort
    from data_security.application.crypto_service import CryptoService
    import data_security.adapters.persistence.risk as risk_adapter
    import export_risk.column_authority as column_authority
    from export_risk.column_authority import ColumnRiskSupplier

    entry = export_delivery()
    assert type(entry) is DjangoResourceExports, 'ordinary startup did not assemble the real delivery owner'
    user = CTFUser.objects.get(pk=fields['user'])
    steps, io = [], []
    paused = False
    attempt_event_id = None
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_backend_pid()')
        pid = cursor.fetchone()[0]

    def pause():
        nonlocal paused
        assert not paused, 'wait checkpoint repeated'
        paused = True
        print(json.dumps({'phase': 'ready', 'stage': stage, 'pid': pid,
                          'atomic': connection.in_atomic_block}), flush=True)
        assert sys.stdin.readline() == 'resume\n', 'parent did not release the checkpoint'

    def entering(method, **evidence):
        print(json.dumps({'phase': 'enter', 'stage': stage, 'pid': pid, 'method': method,
                          'atomic': connection.in_atomic_block, **evidence}), flush=True)

    def observed(name, method):
        def actual(*args, **kwargs):
            steps.append([name, connection.in_atomic_block])
            if stage == 'issue_prepare' and name == 'prepare_execution':
                entering(name)
            elif stage == 'consume' and name == 'recheck_execution' and paused:
                entering(name)
            return method(*args, **kwargs)
        return actual

    issue, consume = DjangoRiskPort.issue, DjangoRiskPort.consume

    def issuing(self, binding):
        steps.append(['issue', connection.in_atomic_block])
        if stage == 'issue_prepare':
            pause()
        return issue(self, binding)

    def consuming(self, binding):
        steps.append(['consume', connection.in_atomic_block])
        if stage == 'consume':
            pause()
        return consume(self, binding)

    def outside_locks(name, method):
        def actual(*args, **kwargs):
            assert not connection.in_atomic_block, name + ' ran under delivery locks'
            io.append(name)
            return method(*args, **kwargs)
        return actual

    original_read, open_file = entry.sources.read_original, CryptoService.open

    def read_original(*args, **kwargs):
        assert stage == 'consume', 'denied issue/output read reopened the original'
        assert not connection.in_atomic_block, 'original read ran under delivery locks'
        io.append('original')
        return original_read(*args, **kwargs)

    def opened(self, envelope, context, key):
        assert not connection.in_atomic_block, 'file open ran under delivery locks'
        io.append('open')
        payload = open_file(self, envelope, context, key)
        if stage == 'open_last_append' and context.field_ref == 'resources/export':
            assert type(payload) is BoundedPayload and payload.binary == EXPECTED
            steps.append(['opened', connection.in_atomic_block])
            pause()  # Earlier ledger reads and full output authentication are finished.
        return payload

    append = DjangoAuditSink.append

    def appended(self, event, durability):
        nonlocal attempt_event_id
        steps.append(['append', connection.in_atomic_block])
        if stage == 'open_last_append':
            assert event.kind is EventKind.AUTHORIZATION and event.correlation_ref.startswith('read/')
            attempt_event_id = event.event_id
            entering('audit_append', event_id=event.event_id)
        receipt = append(self, event, durability)
        assert type(receipt) is AuditReceipt and receipt.chain_version == 'ds.audit.v2'
        assert AuthenticatedAuditEntry.objects.filter(record__event_id=event.event_id).exists()
        steps.append(['append_confirmed', connection.in_atomic_block])
        return receipt

    with ExitStack() as stack:
        for name in ('prepare_execution', 'claim', 'recheck_execution', 'recheck_delivered', 'consume'):
            label = 'consume_authorization' if name == 'consume' else name
            stack.enter_context(patch.object(risk_adapter, name, observed(label, getattr(risk_adapter, name))))
        for owner, name, label in (
            (DjangoQuotaPort, 'reserve', 'reserve'), (DjangoQuotaPort, 'commit', 'settle'),
            (DjangoPrivateStore, 'publish', 'publish'), (DjangoReportRepository, 'record_delivery', 'receipt'),
        ):
            stack.enter_context(patch.object(owner, name, observed(label, getattr(owner, name))))
        stack.enter_context(patch.object(DjangoRiskPort, 'issue', issuing))
        stack.enter_context(patch.object(DjangoRiskPort, 'consume', consuming))
        stack.enter_context(patch.object(entry.sources, 'read_original', read_original))
        stack.enter_context(patch.object(CryptoService, 'open', opened))
        stack.enter_context(patch.object(CryptoService, 'seal', outside_locks('seal', CryptoService.seal)))
        stack.enter_context(patch.object(DjangoPrivateStore, '_read_file', outside_locks('file', DjangoPrivateStore._read_file)))
        stack.enter_context(patch.object(DjangoAuditSink, 'append', appended))
        if stage == 'open_last_append':
            for owner, name in ((ColumnRiskSupplier, 'assess'), (column_authority, 'assess_risk')):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError('output read reassessed risk')))
            result = entry.open_delivery(user=user, source_ref=fields['source_ref'], permission_ref=fields['permission_ref'])
        else:
            result = entry.execute(user=user, source_ref=fields['source_ref'], permission_ref=fields['permission_ref'])
    assert isinstance(result, ProtectionError), 'expired execution returned a delivery or plaintext'
    assert paused, 'wait stage was not reached: ' + result.code.value
    return {'code': result.code.value, 'steps': steps, 'io': io, 'attempt_event_id': attempt_event_id}


class FormalDeliveryWaitTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def setUp(self):
        super().setUp()
        self.source_ref, self.permission_ref, self.risk_ref, self.execution = self.ready()
        source, request, _, supplier, _, _ = self.ok(self.entry._load(
            user=self.teacher, source_ref=self.source_ref, permission_ref=self.permission_ref))
        permission = ColumnRiskPermission.objects.get(permission_ref=self.risk_ref)
        self.assertEqual(source.document['risk_inputs'], {})
        self.assertEqual(permission.grant_document['binding']['risk_inputs'], {})
        self.assertEqual(permission.grant_document['binding']['request'], source.document['request'])
        self.assertEqual((supplier._profile.asset_version, supplier._profile.coverage,
            supplier._profile.status, supplier._profile.protection_level),
            (request.asset_version, QualityState.MISSING, 'unknown', 'unknown'))
        self.assertEqual(self.execution.policy_binding.risk_version, 'policy-m0')
        self.assertEqual(permission.grant_document['initial_disposition'], 'require_approval')
        assessment = permission.grant_document['assessment']
        self.assertEqual((assessment['profile_id'], assessment['feature_set_version']), ('', ''))
        self.assertEqual(RiskDecision.objects.get(decision_id=self.execution.decision_id).action, 'require_approval')
        self.assertEqual(permission.state, 'approved')
        self.assertEqual(permission.approval_document['approved_by'], 'user/' + str(self.reviewer.pk))
        self.assertNotEqual(permission.approval_document['approved_by'], request.subject_id)
        self.assertEqual(ExportPlanApproval.objects.get(approval_ref=source.target_approval_ref)
            .document['approved_by'], 'user/' + str(self.reviewer.pk))

    def state(self):
        return tuple(list(model._base_manager.order_by('pk').values()) for model in (
            Resource, ExportSource, ExportSourcePermission, ColumnRiskPermission, RiskDecision,
            IdempotencyRecord, ExecutionAuthorizationRecord, EventOutbox, ExportPlanApproval,
            ExportReport, PrivateObject, QuotaExecution, QuotaReservation, QuotaBucket,
            AuditEvent, AuditLedgerEntry, SecurityAuditRecord, AuthenticatedAuditEntry, AuditLedgerLock))

    def wait_for_expiry(self, stage):
        table = 'audit_auditledgerlock' if stage == 'open_last_append' else 'export_quota_quotabucket'
        method = {'issue_prepare': 'prepare_execution', 'consume': 'recheck_execution',
                  'open_last_append': 'audit_append'}[stage]
        with _spawn_wait(self, stage) as child:
            try:
                ready = _message(self, child)
                self.assertEqual((ready['phase'], ready['stage'], ready['atomic']),
                                 ('ready', stage, stage == 'consume'))
                # Set the real stored deadline only after expensive startup/preparation.
                # Do not rewrite immutable owner grants, fingerprints or binding documents.
                until = timezone.now() + timedelta(seconds=3)
                if stage == 'issue_prepare':
                    rows, field = QuotaReservation.objects.filter(reservation_id=self.execution.reservation_id), 'expires_at'
                else:
                    rows, field = ExecutionAuthorizationRecord.objects.filter(
                        authorization_id=self.execution.authorization_id), 'valid_until'
                self.assertLess(until, rows.values_list(field, flat=True).get())
                self.assertLess(until, self.execution.expires_at)
                self.assertEqual(rows.update(**{field: until}), 1)
                before = self.state()
                files = {path.name: path.read_bytes() for path in self.root.iterdir()}
                audit = self.ok(self.gateway.sink.verify('ds.audit.v2'))
                with transaction.atomic():
                    if stage == 'open_last_append':
                        AuditLedgerLock.objects.select_for_update().get(key='v2:' + self.gateway.sink.chain_identity[:40])
                    else:
                        reservation = QuotaReservation.objects.get(reservation_id=self.execution.reservation_id)
                        QuotaBucket.objects.select_for_update().get(pk=reservation.bucket_id)
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_backend_pid()')
                        main_pid = cursor.fetchone()[0]
                    self.assertNotEqual(main_pid, ready['pid'])
                    child.stdin.write('resume\n')
                    child.stdin.flush()
                    entered = _message(self, child)
                    self.assertEqual((entered['phase'], entered['stage'], entered['pid'], entered['method'], entered['atomic']),
                                     ('enter', stage, ready['pid'], method, True))
                    limit, blocked = time.monotonic() + 10, False
                    while time.monotonic() < limit:
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT pg_stat_clear_snapshot()')
                            cursor.execute('SELECT wait_event_type, query, query_start, pg_blocking_pids(pid), '
                                           'clock_timestamp() FROM pg_stat_activity WHERE pid = %s', [ready['pid']])
                            activity = cursor.fetchone()
                        if activity is not None:
                            wait, query, query_start, blockers, observed_at = activity
                            blocked = wait == 'Lock' and main_pid in blockers
                            if blocked:
                                break
                        time.sleep(0.01)
                    self.assertTrue(blocked, stage + ' never waited on the main PostgreSQL connection')
                    self.assertIn(table, query)
                    self.assertIn('FOR UPDATE', query)
                    self.assertLess(query_start, until, 'target lock query began after expiry')
                    self.assertLess(observed_at, until, 'actual blocked wait must be observed before expiry')
                    self.assertIsNone(child.poll())
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_sleep(GREATEST(0, EXTRACT(EPOCH FROM '
                                       '(%s::timestamptz - clock_timestamp())) + 0.05))', [until])
                        cursor.execute('SELECT clock_timestamp()')
                        releasing_at = cursor.fetchone()[0]
                    self.assertGreater(releasing_at, until, 'parent must retain the lock past expiry')
                output, error = child.communicate(timeout=30)
            finally:
                if child.poll() is None:
                    child.kill()  # Failed assertions/timeouts must not strand a connection or held transaction.
        self.assertEqual(child.returncode, 0, 'ordinary wait child failed: ' + error[-3000:])
        result = json.loads(output)
        self.assertEqual(result['code'], 'AUTHORIZATION_DENIED')
        self.assertEqual(self.state(), before)
        self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, files)
        self.assertEqual(self.gateway.sink.verify('ds.audit.v2'), audit)
        # Keep only safe lock metadata in the log; successful test stdout is otherwise discarded.
        print('PG_LOCK_EVIDENCE ' + json.dumps({'stage': stage, 'method': method, 'main_pid': main_pid,
            'worker_pid': ready['pid'], 'table': table, 'query_sha256': hashlib.sha256(query.encode()).hexdigest(),
            'wait_event_type': wait, 'blocking_pids': blockers, 'query_start': query_start.isoformat(),
            'observed_at': observed_at.isoformat(), 'expires_at': until.isoformat(),
            'release_after': releasing_at.isoformat()}), file=sys.__stdout__, flush=True)
        return result

    def test_issue_prepare_bucket_wait_rejects_expired_hold_before_claim(self):
        result = self.wait_for_expiry('issue_prepare')
        self.assertEqual(result['steps'], [['reserve', True], ['issue', False], ['prepare_execution', True]])
        self.assertEqual(result['io'], [])
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertFalse(IdempotencyRecord.objects.filter(operation='prepare_execution').exists())
        report = ExportReport.objects.get()
        self.assertEqual(report.state, 'preparing')
        self.assertIsNone(report.document)
        self.assertIsNone(report.delivery_receipt)
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (2, 0, 0))
        self.assertIsNone(QuotaExecution.objects.get().terminal_receipt)
        self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())

    def test_consume_bucket_wait_rejects_expired_authorization_without_settlement(self):
        result = self.wait_for_expiry('consume')
        self.assertEqual(result['steps'], [['reserve', True], ['issue', False], ['prepare_execution', True],
            ['claim', True], ['recheck_execution', True], ['consume', True], ['recheck_execution', True]])
        self.assertEqual(result['io'].count('original'), 1)
        self.assertEqual(result['io'].count('seal'), 1)
        self.assertIn('open', result['io'])
        authorization = ExecutionAuthorizationRecord.objects.get()
        self.assertEqual(authorization.state, 'claiming')
        self.assertIsNone(authorization.consumed_at)
        report = ExportReport.objects.get()
        self.assertEqual(report.state, 'prepared')
        self.assertIsNotNone(report.document)
        self.assertIsNone(report.delivery_receipt)
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (2, 0, 0))
        self.assertIsNone(QuotaExecution.objects.get().terminal_receipt)
        self.assertEqual(list(PrivateObject.objects.order_by('pk').values_list('state', flat=True)), ['verified', 'verified'])
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())

    def test_open_last_append_ledger_wait_rejects_expired_consumed_authorization_without_effects(self):
        completed = formal_call(self, 'execute', source_ref=self.source_ref, permission_ref=self.permission_ref)
        receipt = DeliveryReceipt.from_wire(completed['delivery'])
        self.assertEqual(receipt.binding, self.execution)
        self.assertEqual(receipt.delivered_records, 2)
        result = self.wait_for_expiry('open_last_append')
        self.assertEqual(result['steps'], [['opened', False], ['recheck_delivered', True], ['append', True],
                                          ['append_confirmed', True], ['recheck_delivered', True]])
        self.assertEqual(result['io'], ['file', 'open'])
        self.assertIsNotNone(result['attempt_event_id'])
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id=result['attempt_event_id']).exists())
        self.assertEqual(ExportReport.objects.get().delivery_receipt, completed['delivery'])
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 0, 2))
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        self.assertEqual(self.gateway.sink.verify('ds.audit.v2'), receipt.audit)
