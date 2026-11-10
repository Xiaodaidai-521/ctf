"""A live formal preparation owner cannot be adopted by a second normal startup."""
from contextlib import ExitStack
import json
import os
import select
import subprocess
import sys
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution
from data_security.contracts import DeliveryReceipt, ProtectionError, ReasonCode
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.models import ColumnRiskPermission, ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision
from tools.data_security import isolation
from users.models import CTFUser

from .models import ExportSource, ExportSourcePermission
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
    from resources.test_phase6_formal_competition import invoke_competition
    print(json.dumps(invoke_competition(sys.argv[2], json.loads(sys.argv[3]))), flush=True)
finally:
    connections.close_all()
'''


def invoke_competition(mode, fields):
    from data_security.adapters.django.export_delivery import export_delivery
    from data_security.adapters.persistence.export_delivery import DjangoResourceExports
    from data_security.adapters.persistence.private_store import DjangoPrivateStore
    from data_security.adapters.persistence.quota import DjangoQuotaPort
    from data_security.adapters.persistence.report_records import DjangoReportRepository
    from data_security.adapters.persistence.risk import DjangoRiskPort
    from data_security.application.table_reports import TableReportExecutor
    import data_security.adapters.persistence.risk as risk_adapter
    import export_risk.column_authority as column_authority

    entry = export_delivery()
    assert type(entry) is DjangoResourceExports
    user = CTFUser.objects.get(pk=fields['user'])
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_backend_pid()')
        pid = cursor.fetchone()[0]
    begun = []
    counts = dict.fromkeys(('reserve', 'issue', 'claim', 'original', 'prepare', 'put', 'publish', 'settle', 'judgment'), 0)
    begin, issue = DjangoReportRepository.begin, DjangoRiskPort.issue

    def starting(self, *args):
        result = begin(self, *args)
        assert type(result) is bool
        begun.append(result)
        return result

    def issuing(self, binding):
        counts['issue'] += 1
        if mode == 'winner':
            assert not connection.in_atomic_block and begun == [True]
            assert QuotaReservation.objects.get().state == 'reserved'
            assert not ExecutionAuthorizationRecord.objects.exists()
            print(json.dumps({'phase': 'reserved', 'pid': pid, 'atomic': False}), flush=True)
            assert sys.stdin.readline() == 'resume\n'
        return issue(self, binding)

    def observed(name, original):
        def actual(*args, **kwargs):
            counts[name] += 1
            return original(*args, **kwargs)
        return actual

    with ExitStack() as stack:
        stack.enter_context(patch.object(DjangoReportRepository, 'begin', starting))
        stack.enter_context(patch.object(DjangoRiskPort, 'issue', issuing))
        for owner, method, name in (
            (DjangoQuotaPort, 'reserve', 'reserve'), (risk_adapter, 'claim', 'claim'),
            (entry.sources, 'read_original', 'original'), (TableReportExecutor, 'prepare', 'prepare'),
            (DjangoReportRepository, 'put', 'put'), (DjangoPrivateStore, 'publish', 'publish'),
            (DjangoQuotaPort, 'commit', 'settle'), (column_authority, 'assess_risk', 'judgment'),
        ):
            stack.enter_context(patch.object(owner, method, observed(name, getattr(owner, method))))
        result = entry.execute(user=user, source_ref=fields['source_ref'], permission_ref=fields['permission_ref'])
    if mode == 'winner':
        assert type(result) is DeliveryReceipt and begun == [True]
        assert counts == {name: int(name != 'judgment') for name in counts}
        return {'pid': pid, 'delivery': result.to_wire(), 'counts': counts}
    assert mode == 'competitor' and begun == [False]
    assert isinstance(result, ProtectionError) and result.code is ReasonCode.DELIVERY_UNKNOWN
    assert not any(counts.values()), 'competing preparation repeated a business stage'
    return {'pid': pid, 'code': result.code.value, 'begun': begun, 'counts': counts}


class FormalPreparationCompetitionTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def state(self):
        return tuple(list(model.objects.order_by('pk').values()) for model in (
            ExportSource, ExportSourcePermission, ColumnRiskPermission, RiskDecision, IdempotencyRecord,
            ExecutionAuthorizationRecord, ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution,
            QuotaReservation, QuotaBucket, AuthenticatedAuditEntry, SecurityAuditRecord))

    def test_concurrent_ordinary_startups_keep_one_live_preparation_owner_and_one_settlement(self):
        source_ref, permission_ref, risk_ref, execution = self.ready()
        env = isolation.clean_env()
        env.update(DATA_SECURITY_CONFIG=str(self.config_path), DATA_SECURITY_ISOLATED_TEST='1',
            DJANGO_SETTINGS_MODULE='tools.data_security.test_settings',
            DS_TEST_PG_PORT=os.environ['DS_TEST_PG_PORT'], DS_TEST_PG_SOCKET=os.environ['DS_TEST_PG_SOCKET'],
            ALLOWED_HOSTS='testserver,localhost', DEBUG='false')
        self.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
        command = [sys.executable, '-I', '-B', '-c', _CHILD, 'test_ds_phase1_main']
        fields = json.dumps({'user': self.teacher.pk, 'source_ref': source_ref, 'permission_ref': permission_ref})
        with subprocess.Popen(command + ['winner', fields], cwd=isolation.ROOT, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
            try:
                readable, _, _ = select.select([child.stdout], [], [], 60)
                self.assertTrue(readable, 'first ordinary startup did not reach its committed reservation')
                ready = json.loads(child.stdout.readline())
                self.assertEqual((ready['phase'], ready['atomic']), ('reserved', False))
                self.assertIsNone(child.poll())
                self.assertEqual(ExportReport.objects.get().state, 'preparing')
                self.assertEqual(QuotaReservation.objects.count(), 1)
                self.assertEqual(QuotaBucket.objects.get().active_reserved, execution.quantity)
                self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
                before = self.state()
                files = {path.name: path.read_bytes() for path in self.root.iterdir()}
                competing = subprocess.run(command + ['competitor', fields], cwd=isolation.ROOT, env=env,
                    capture_output=True, text=True, timeout=90)
                self.assertEqual(competing.returncode, 0, competing.stderr[-3000:])
                loser = json.loads(competing.stdout)
                self.assertEqual(loser['code'], 'DELIVERY_UNKNOWN')
                self.assertEqual(loser['begun'], [False])
                self.assertNotEqual(loser['pid'], ready['pid'])
                self.assertIsNone(child.poll())
                self.assertEqual(self.state(), before)
                self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, files)
                output, error = child.communicate('resume\n', timeout=90)
            finally:
                if child.poll() is None:
                    child.kill()
        self.assertEqual(child.returncode, 0, error[-3000:])
        winner = json.loads(output)
        receipt = DeliveryReceipt.from_wire(winner['delivery'])
        self.assertEqual(receipt.binding, execution)
        self.assertEqual(receipt.delivered_records, 2)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), 1)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
        self.assertEqual(RiskDecision.objects.count(), 1)
        self.assertEqual(ExportReport.objects.get().delivery_receipt, winner['delivery'])
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        self.assertEqual(self.gateway.sink.verify('ds.audit.v2'), receipt.audit)
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 0, 2))
        before = self.state()
        replay = formal_call(self, 'replay', source_ref=source_ref, permission_ref=permission_ref, risk_ref=risk_ref)
        self.assertEqual(replay, {'binding': execution.to_wire(), 'delivery': winner['delivery']})
        self.assertEqual(self.state(), before)
        print('PG_COMPETITION_EVIDENCE ' + json.dumps({'winner_pid': winner['pid'], 'competing_pid': loser['pid'],
            'winner_begun': True, 'competing_begun': False, 'winner_counts': winner['counts'],
            'competing_counts': loser['counts'], 'reservations': 1, 'delivered_records': receipt.delivered_records}),
            file=sys.__stdout__, flush=True)
