"""Current authority after the final real PostgreSQL ledger wait, through B."""
from contextlib import ExitStack
from datetime import timedelta
import hashlib
import json
import os
import subprocess
import sys
import time
from unittest.mock import patch

from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuditEvent, AuditLedgerEntry, AuditLedgerLock, AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution
from data_security.contracts import (
    AuditReceipt, BoundedPayload, DeliveryReceipt, Environment, EventKind, Outlet,
    PolicyStatus, ProtectionContext, ProtectionError, Purpose, Role,
)
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.models import ColumnRiskPermission, EventOutbox, ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision
from tools.data_security import isolation
from users.models import CTFUser

from .models import ExportSource, ExportSourcePermission, Resource
from .test_phase6_formal_delivery import EXPECTED
from .test_phase6_formal_fixtures import FormalResourceFixture, formal_call
from .test_phase6_formal_waits import _message


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
    from resources.test_phase6_formal_final_gate import invoke_final_gate
    print(json.dumps(invoke_final_gate(sys.argv[2], json.loads(sys.argv[3]))), flush=True)
finally:
    connections.close_all()
'''


def invoke_final_gate(stage, fields):
    from data_security.adapters.django.export_delivery import export_delivery
    from data_security.adapters.persistence.audit import DjangoAuditSink
    from data_security.adapters.persistence.export_delivery import DjangoResourceExports
    from data_security.adapters.persistence.private_store import DjangoPrivateStore
    from data_security.adapters.persistence.quota import DjangoQuotaPort
    from data_security.adapters.persistence.report_records import DjangoReportRepository
    from data_security.adapters.persistence.risk import DjangoRiskPort
    from data_security.application.crypto_service import CryptoService
    from data_security.application.table_reports import TableReportExecutor
    import data_security.adapters.persistence.risk as risk_adapter
    import export_risk.column_authority as column_authority

    entry = export_delivery()
    assert type(entry) is DjangoResourceExports
    user = CTFUser.objects.get(pk=fields['user'])
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_backend_pid()')
        pid = cursor.fetchone()[0]
    # A new short source grant is issued only after ordinary startup. Its signed
    # deadline is never rewritten, unlike the mutable execution deadline below.
    print(json.dumps({'phase': 'started', 'pid': pid}), flush=True)
    fields.update(json.loads(sys.stdin.readline()))
    committing = stage == 'commit_authorization'
    counts = dict.fromkeys(('reserve', 'issue', 'claim', 'original', 'prepare', 'put',
                           'consume', 'publish', 'settle', 'receipt', 'recheck_delivered'), 0)
    opened, append_confirmed, paused = False, False, False
    event_id = None

    def pause():
        nonlocal paused
        assert not paused
        paused = True
        print(json.dumps({'phase': 'ready', 'pid': pid, 'atomic': connection.in_atomic_block}), flush=True)
        assert sys.stdin.readline() == 'resume\n'

    def observed(name, original):
        def actual(*args, **kwargs):
            counts[name] += 1
            return original(*args, **kwargs)
        return actual

    consume = DjangoRiskPort.consume

    def consuming(self, binding):
        counts['consume'] += 1
        assert committing and connection.in_atomic_block
        pause()
        return consume(self, binding)

    open_file = CryptoService.open

    def opening(self, envelope, context, key):
        nonlocal opened
        assert not connection.in_atomic_block
        result = open_file(self, envelope, context, key)
        if not committing and context.field_ref == 'resources/export':
            assert type(result) is BoundedPayload and result.binary == EXPECTED
            opened = True
            pause()
        return result

    append = DjangoAuditSink.append

    def appending(self, event, durability):
        nonlocal append_confirmed, event_id
        assert connection.in_atomic_block
        assert event.kind is (EventKind.DELIVERY if committing else EventKind.AUTHORIZATION)
        if committing:
            assert counts['publish'] == counts['settle'] == 1
            assert ExecutionAuthorizationRecord.objects.get().state == 'consumed'
            assert QuotaReservation.objects.get().state == 'committed'
            assert QuotaBucket.objects.get().settled == 2
            assert PrivateObject.objects.filter(state='published').count() == 1
            assert ExportReport.objects.get().delivery_receipt is None
        else:
            assert opened and not any(counts[name] for name in counts if name != 'recheck_delivered')
            assert event.correlation_ref.startswith('read/')
        event_id = event.event_id
        print(json.dumps({'phase': 'append', 'pid': pid, 'atomic': True}), flush=True)
        result = append(self, event, durability)
        assert type(result) is AuditReceipt and result.chain_version == 'ds.audit.v2'
        assert AuthenticatedAuditEntry.objects.filter(record__event_id=event_id).exists()
        append_confirmed = True
        return result

    with ExitStack() as stack:
        for owner, name, label in (
            (DjangoQuotaPort, 'reserve', 'reserve'), (DjangoRiskPort, 'issue', 'issue'),
            (risk_adapter, 'claim', 'claim'), (entry.sources, 'read_original', 'original'),
            (TableReportExecutor, 'prepare', 'prepare'), (DjangoReportRepository, 'put', 'put'),
            (DjangoPrivateStore, 'publish', 'publish'), (DjangoQuotaPort, 'commit', 'settle'),
            (DjangoReportRepository, 'record_delivery', 'receipt'),
            (DjangoRiskPort, 'recheck_delivered', 'recheck_delivered'),
        ):
            stack.enter_context(patch.object(owner, name, observed(label, getattr(owner, name))))
        stack.enter_context(patch.object(column_authority, 'assess_risk', side_effect=AssertionError('risk reassessed')))
        stack.enter_context(patch.object(DjangoRiskPort, 'consume', consuming))
        stack.enter_context(patch.object(CryptoService, 'open', opening))
        stack.enter_context(patch.object(DjangoAuditSink, 'append', appending))
        operation = entry.execute if committing else entry.open_delivery
        result = operation(user=user, source_ref=fields['source_ref'], permission_ref=fields['permission_ref'])
    assert paused and append_confirmed
    # Retain only safe result metadata even when a red test exposes a wrongly
    # successful receipt/plaintext. The parent still requires exact denial.
    return {'result_type': type(result).__name__,
        'code': result.code.value if isinstance(result, ProtectionError) else None,
        'returned_bytes': len(result.binary) if type(result) is BoundedPayload else 0,
        'delivered_records': result.delivered_records if type(result) is DeliveryReceipt else None,
        'event_id': event_id, 'counts': counts, 'append_confirmed': append_confirmed}


class FormalFinalGateTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def state(self):
        return tuple(list(model._base_manager.order_by('pk').values()) for model in (
            Resource, ExportSource, ExportSourcePermission, ColumnRiskPermission, RiskDecision,
            IdempotencyRecord, ExecutionAuthorizationRecord, EventOutbox, ExportPlanApproval,
            ExportReport, PrivateObject, QuotaExecution, QuotaReservation, QuotaBucket,
            AuditEvent, AuditLedgerEntry, SecurityAuditRecord, AuthenticatedAuditEntry, AuditLedgerLock))

    def final_wait(self, stage):
        source_ref, permission_ref, _, execution = self.ready()
        committing = stage == 'commit_authorization'
        if not committing:
            delivered = formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref)
            self.assertEqual(DeliveryReceipt.from_wire(delivered['delivery']).binding, execution)
        catalog = assemble(config_path=self.config_path)['catalog']
        env = isolation.clean_env()
        env.update(DATA_SECURITY_CONFIG=str(self.config_path), DATA_SECURITY_ISOLATED_TEST='1',
            DJANGO_SETTINGS_MODULE='tools.data_security.test_settings',
            DS_TEST_PG_PORT=os.environ['DS_TEST_PG_PORT'], DS_TEST_PG_SOCKET=os.environ['DS_TEST_PG_SOCKET'],
            ALLOWED_HOSTS='testserver,localhost', DEBUG='false')
        command = [sys.executable, '-I', '-B', '-c', _CHILD, 'test_ds_phase1_main', stage,
            json.dumps({'user': self.teacher.pk, 'source_ref': source_ref, 'permission_ref': permission_ref})]
        with subprocess.Popen(command, cwd=isolation.ROOT, env=env, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
            try:
                started = _message(self, child)
                self.assertEqual(started['phase'], 'started')
                until = None
                if stage == 'open_source':
                    until = timezone.now() + timedelta(seconds=30)
                    permission_ref, _ = self.ok(self.sources.grant(user=self.reviewer, source_ref=source_ref,
                        grantee_id=self.teacher.pk, expires_at=until))
                    self.assertEqual(ExportSourcePermission.objects.get(authorization_ref=permission_ref).expires_at, until)
                child.stdin.write(json.dumps({'permission_ref': permission_ref}) + '\n')
                child.stdin.flush()
                ready = _message(self, child)
                self.assertEqual((ready['phase'], ready['pid'], ready['atomic']), ('ready', started['pid'], committing))
                if committing:
                    until = timezone.now() + timedelta(seconds=3)
                    authority = ExecutionAuthorizationRecord.objects.get(authorization_id=execution.authorization_id)
                    self.assertLess(until, authority.valid_until)
                    self.assertEqual(ExecutionAuthorizationRecord.objects.filter(pk=authority.pk).update(valid_until=until), 1)
                elif until is not None:
                    self.assertLess(until, ExecutionAuthorizationRecord.objects.get().valid_until)
                if until is not None:
                    self.assertLess(until, execution.expires_at)
                before, files = self.state(), {path.name: path.read_bytes() for path in self.root.iterdir()}
                audit = self.ok(self.gateway.sink.verify('ds.audit.v2'))
                with transaction.atomic():
                    AuditLedgerLock.objects.select_for_update().get(key='v2:' + self.gateway.sink.chain_identity[:40])
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_backend_pid()')
                        main_pid = cursor.fetchone()[0]
                    self.assertNotEqual(main_pid, ready['pid'])
                    child.stdin.write('resume\n')
                    child.stdin.flush()
                    self.assertEqual(_message(self, child), {'phase': 'append', 'pid': ready['pid'], 'atomic': True})
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
                    self.assertTrue(blocked)
                    self.assertIn('audit_auditledgerlock', query)
                    self.assertIn('FOR UPDATE', query)
                    self.assertIsNone(child.poll())
                    if stage == 'open_policy':
                        principal = ProtectionContext(schema_version=ProtectionContext.SCHEMA,
                            actor_ref='user/' + str(self.policy_admin.pk), authorization_ref='authorization/isolated-policy-manager',
                            scope_refs=('policy/manage',), environment=Environment.EVALUATION, domain='ctf',
                            outlet=Outlet.API, purpose=Purpose.SECURITY_AUDIT, role=Role.ADMIN,
                            object_ref='policy/isolated', object_version=self.binding.protection_version,
                            source_ref=None, source_version=None, source_hash=None, trace_id='policy/retire-during-read')
                        retired = self.ok(catalog.retire(self.binding, principal))
                        self.assertIs(retired.status, PolicyStatus.RETIRED)
                        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='policy',
                            event__correlation_ref=principal.trace_id).count(), 2)
                        before = self.state()  # The actual management events are allowed; no read event is.
                    else:
                        self.assertLess(query_start, until)
                        self.assertLess(observed_at, until)
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT pg_sleep(GREATEST(0, EXTRACT(EPOCH FROM '
                                           '(%s::timestamptz - clock_timestamp())) + 0.05))', [until])
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT clock_timestamp()')
                        release_after = cursor.fetchone()[0]
                    if until is not None:
                        self.assertGreater(release_after, until)
                output, error = child.communicate(timeout=30)
            finally:
                if child.poll() is None:
                    child.kill()
        self.assertEqual(child.returncode, 0, 'ordinary final-gate child failed: ' + error[-3000:])
        result = json.loads(output)
        print('PG_GATE_EVIDENCE ' + json.dumps({'stage': stage, 'main_pid': main_pid, 'worker_pid': ready['pid'],
            'table': 'audit_auditledgerlock', 'wait_event_type': wait, 'blocking_pids': blockers,
            'query_sha256': hashlib.sha256(query.encode()).hexdigest(), 'query_start': query_start.isoformat(),
            'observed_at': observed_at.isoformat(), 'expires_at': until.isoformat() if until else None,
            'release_after': release_after.isoformat(), **result}), file=sys.__stdout__, flush=True)
        self.assertEqual(result['result_type'], 'ProtectionError')
        self.assertEqual(result['code'], {'open_source': 'AUTHORIZATION_EXPIRED', 'open_policy': 'POLICY_NOT_APPROVED',
                                         'commit_authorization': 'AUTHORIZATION_DENIED'}[stage])
        self.assertEqual(result['returned_bytes'], 0)
        self.assertEqual(self.state(), before)
        self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, files)
        self.assertEqual(self.gateway.sink.verify('ds.audit.v2'), audit)
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id=result['event_id']).exists())
        if committing:
            self.assertEqual(result['counts'], {name: int(name != 'receipt') for name in result['counts']})
            self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
            self.assertEqual(QuotaReservation.objects.get().state, 'reserved')
            bucket = QuotaBucket.objects.get()
            self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (2, 0, 0))
            self.assertIsNone(QuotaExecution.objects.get().terminal_receipt)
            self.assertIsNone(ExportReport.objects.get().delivery_receipt)
            self.assertEqual(PrivateObject.objects.filter(state='published').count(), 0)
        else:
            self.assertFalse(any(value for name, value in result['counts'].items() if name != 'recheck_delivered'))
            self.assertEqual(result['counts']['recheck_delivered'], 1)
            self.assertEqual(ExportReport.objects.get().delivery_receipt, delivered['delivery'])
            self.assertEqual(QuotaReservation.objects.get().state, 'committed')
            self.assertEqual(QuotaBucket.objects.get().settled, 2)
            self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        if stage == 'open_policy':
            self.assertIs(catalog.repository.read(self.binding).status, PolicyStatus.RETIRED)

    def test_open_rechecks_new_short_source_permission_after_final_ledger_wait(self):
        self.final_wait('open_source')

    def test_open_rechecks_policy_retired_during_final_ledger_wait(self):
        self.final_wait('open_policy')

    def test_commit_rechecks_consumed_authorization_after_actual_settlement_and_final_ledger_wait(self):
        self.final_wait('commit_authorization')
