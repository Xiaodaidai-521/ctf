"""B1 regressions for new conditional issuance and committed target handoff.

Revoking a reviewer's current authority must stop NEW approval issuance, not
invalidate the source approvals or risk grants they validly issued earlier.
"""
from contextlib import ExitStack
from datetime import timedelta
import hashlib
import json
import os
import subprocess
import sys
import time
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuditEvent, AuditLedgerEntry, AuditLedgerLock, AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution
from data_security.contracts import ActionPlan, AuditReceipt, DeliveryReceipt, Durability, ProtectionError, content_hash
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.contracts import Disposition, QualityState
from export_risk.models import ColumnRiskPermission, EventOutbox, ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision
from tools.data_security import isolation
from users.models import CTFUser

from .models import ExportSource, ExportSourcePermission, Resource
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
    from resources.test_phase6_formal_approval_edges import invoke_approval_edge
    print(json.dumps(invoke_approval_edge(sys.argv[2], json.loads(sys.argv[3]))), flush=True)
finally:
    connections.close_all()
'''


def _spawn_approval(test, case):
    # Preserve formal_call's original settings and installed network guard.
    env = isolation.clean_env()
    env.update(DATA_SECURITY_CONFIG=str(test.config_path), DATA_SECURITY_ISOLATED_TEST='1',
        DJANGO_SETTINGS_MODULE='tools.data_security.test_settings',
        DS_TEST_PG_PORT=os.environ['DS_TEST_PG_PORT'], DS_TEST_PG_SOCKET=os.environ['DS_TEST_PG_SOCKET'],
        ALLOWED_HOSTS='testserver,localhost', DEBUG='false')
    test.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
    return subprocess.Popen([sys.executable, '-I', '-B', '-c', _CHILD, 'test_ds_phase1_main', case,
        json.dumps({'user': test.teacher.pk, 'reviewer': test.reviewer.pk, 'source_ref': test.source_ref,
                    'risk_ref': test.risk_ref, 'decision_id': test.decision_id})],
        cwd=isolation.ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)


def invoke_approval_edge(case, fields):
    """Use only the entry assembled by django.setup; wrappers call actual owners."""
    from data_security.adapters.django.export_delivery import export_delivery
    from data_security.adapters.persistence.export_delivery import DjangoResourceExports

    entry = export_delivery()
    assert type(entry) is DjangoResourceExports, 'ordinary startup did not assemble the delivery owner'
    user = CTFUser.objects.get(pk=fields['user'])
    reviewer = CTFUser.objects.get(pk=fields['reviewer'])
    if case == 'risk-approve':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_backend_pid()')
            pid = cursor.fetchone()[0]
        print(json.dumps({'phase': 'ready', 'pid': pid, 'atomic': connection.in_atomic_block}), flush=True)
        assert sys.stdin.readline() == 'resume\n', 'parent did not release the approval checkpoint'
        result = entry.risks.approve(user=reviewer, permission_ref=fields['risk_ref'],
                                     decision_id=fields['decision_id'])
        if isinstance(result, ProtectionError):
            return {'code': result.code.value}
        assert type(result) is AuditReceipt and result.chain_version == 'ds.audit.v2'
        assert AuthenticatedAuditEntry.objects.filter(record__event_id=result.event_id).exists()
        return {'code': 'APPROVED'}

    assert case in ('source-save', 'source-ack'), 'unknown approval edge'
    manage, retain, save = entry.targets.manage, entry.sources.retain_target, ExportSource.save
    references, hits = [], []

    def managed(**kwargs):
        result = manage(**kwargs)
        assert not isinstance(result, ProtectionError), 'actual target owner did not approve'
        plan, receipt = result
        assert type(plan) is ActionPlan and type(receipt) is AuditReceipt
        assert receipt.chain_version == 'ds.audit.v2' and receipt.durability is Durability.LEDGER_CONFIRMED
        assert connection.get_autocommit() and not connection.in_atomic_block, 'target A has not committed'
        reference = plan.approval.approval_ref
        assert receipt.event_id == reference + '/approve'
        assert ExportPlanApproval.objects.get(approval_ref=reference).document == plan.approval.to_wire()
        assert AuthenticatedAuditEntry.objects.filter(record__event_id=receipt.event_id).exists()
        references.append(reference)
        return result

    def fail_pointer_save(row, *args, **kwargs):
        if row.source_ref == fields['source_ref'] and kwargs.get('update_fields') == ['target_approval_ref']:
            assert len(references) == 1 and row.target_approval_ref == references[0]
            assert connection.in_atomic_block, 'source pointer write did not enter the actual transaction'
            hits.append(case)
            raise DatabaseError('synthetic source target pointer save failed')
        return save(row, *args, **kwargs)

    def lose_pointer_ack(**kwargs):
        reference = retain(**kwargs)
        assert references == [reference], 'actual source owner did not retain target A'
        assert connection.get_autocommit() and not connection.in_atomic_block
        assert ExportSource.objects.get(source_ref=fields['source_ref']).target_approval_ref == reference
        hits.append(case)
        raise DatabaseError('synthetic committed source target pointer acknowledgement lost')

    with ExitStack() as stack:
        stack.enter_context(patch.object(entry.targets, 'manage', side_effect=managed))
        if case == 'source-save':
            stack.enter_context(patch.object(ExportSource, 'save', fail_pointer_save))
        else:
            stack.enter_context(patch.object(entry.sources, 'retain_target', side_effect=lose_pointer_ack))
        result = entry.approve_target(user=reviewer, source_ref=fields['source_ref'], requester=user)
    assert len(references) == 1 and hits == [case], 'committed target/source fault was not reached exactly once'
    assert isinstance(result, ProtectionError), 'source handoff fault was reported as success'
    return {'code': result.code.value, 'trace_id': result.trace_id, 'approval_ref': references[0], 'hits': hits}


class FormalApprovalEdgeTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def setUp(self):
        super().setUp()
        self.source_ref, self.permission_ref = self.approved_source()
        self.risk_ref, _ = self.ok(self.entry.grant_risk(user=self.reviewer, source_ref=self.source_ref,
            expires_at=timezone.now() + timedelta(minutes=20)))
        assessment, self.decision_id, blocker = self.ok(self.entry.admit(user=self.teacher,
            source_ref=self.source_ref, permission_ref=self.permission_ref, risk_permission_ref=self.risk_ref))
        self.assertEqual(assessment.recommended_action.value, 'require_approval')
        self.assertIsNotNone(blocker)
        self.assertIs(blocker.disposition, Disposition.REQUIRE_APPROVAL)
        source, request, _, supplier, _, _ = self.ok(self.entry._load(user=self.teacher,
            source_ref=self.source_ref, permission_ref=self.permission_ref, risk_permission_ref=self.risk_ref))
        permission = ColumnRiskPermission.objects.get(permission_ref=self.risk_ref)
        self.assertEqual(source.document['risk_inputs'], {})
        self.assertEqual(permission.grant_document['binding']['risk_inputs'], {})
        self.assertEqual(permission.grant_document['binding']['request'], source.document['request'])
        self.assertEqual((supplier._profile.asset_version, supplier._profile.coverage,
            supplier._profile.status, supplier._profile.protection_level),
            (request.asset_version, QualityState.MISSING, 'unknown', 'unknown'))
        self.assertEqual(self.binding.risk_version, 'policy-m0')
        self.assertEqual(permission.grant_document['initial_disposition'], 'require_approval')
        self.assertEqual((assessment.profile_id, assessment.feature_set_version), ('', ''))
        self.assertEqual((permission.state, permission.approval_document, permission.approval_event_id),
                         ('pending', None, ''))
        self.assertEqual(RiskDecision.objects.get().decision_id, self.decision_id)
        self.assertTrue(AuthenticatedAuditEntry.objects.filter(record__event_id=permission.grant_event_id).exists())
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id=self.risk_ref + '/approve').exists())

    def state(self):
        return {model: list(model._base_manager.order_by('pk').values()) for model in (
            Resource, ExportSource, ExportSourcePermission, ColumnRiskPermission, RiskDecision,
            IdempotencyRecord, ExecutionAuthorizationRecord, EventOutbox, ExportPlanApproval,
            ExportReport, PrivateObject, QuotaExecution, QuotaReservation, QuotaBucket,
            AuditEvent, AuditLedgerEntry, SecurityAuditRecord, AuthenticatedAuditEntry, AuditLedgerLock)}

    def reviewer_change_during_decision_wait(self, change):
        capability = 'export_risk.change_columnriskpermission'
        permission = Permission.objects.get(content_type__app_label='export_risk', codename='change_columnriskpermission')
        reviewer = CTFUser.objects.get(pk=self.reviewer.pk)
        self.assertTrue(reviewer.is_active and reviewer.has_perm(capability))
        self.assertFalse(reviewer.is_superuser)
        self.assertTrue(reviewer.user_permissions.filter(pk=permission.pk).exists())
        before = self.state()
        files = {path.name: path.read_bytes() for path in self.root.iterdir()}
        audit = self.ok(self.gateway.sink.verify('ds.audit.v2'))
        table = RiskDecision._meta.db_table
        with _spawn_approval(self, 'risk-approve') as child:
            try:
                ready = _message(self, child)
                self.assertEqual((ready['phase'], ready['atomic']), ('ready', False))
                with transaction.atomic():
                    decision = RiskDecision.objects.select_for_update().get(decision_id=self.decision_id)
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_backend_pid()')
                        main_pid = cursor.fetchone()[0]
                    self.assertNotEqual(main_pid, ready['pid'])
                    child.stdin.write('resume\n')
                    child.stdin.flush()
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
                    self.assertTrue(blocked, 'new approval never waited on the parent PostgreSQL PID')
                    self.assertTrue(query.startswith('SELECT ') and 'FROM "' + table + '"' in query and
                                    'FOR UPDATE' in query, 'wait was not the exact RiskDecision SELECT FOR UPDATE')
                    self.assertIsNone(child.poll())
                    # Change only current Django reviewer facts, while the real decision lock is held.
                    if change == 'permission-removed':
                        reviewer.user_permissions.remove(permission)
                    else:
                        self.assertEqual(CTFUser.objects.filter(pk=reviewer.pk).update(is_active=False), 1)
                    current = CTFUser.objects.get(pk=reviewer.pk)
                    self.assertEqual(current.is_active, change == 'permission-removed')
                    self.assertEqual(current.user_permissions.filter(pk=permission.pk).exists(), change == 'deactivated')
                    self.assertFalse(current.has_perm(capability))
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT clock_timestamp()')
                        changed_at = cursor.fetchone()[0]
                    self.assertLess(query_start, observed_at)
                    self.assertLess(observed_at, changed_at)
                    self.assertLess(changed_at, decision.valid_until)
                    self.assertIsNone(child.poll())
                # Emit evidence before the expected red assertion; never print SQL or business bodies.
                print('PG_LOCK_EVIDENCE ' + json.dumps({'stage': 'new-conditional-approval', 'change': change,
                    'method': 'ColumnRiskOwner.approve', 'main_pid': main_pid, 'worker_pid': ready['pid'],
                    'table': table, 'query_sha256': hashlib.sha256(query.encode()).hexdigest(),
                    'wait_event_type': wait, 'blocking_pids': blockers, 'query_start': query_start.isoformat(),
                    'observed_at': observed_at.isoformat(), 'owner_changed_at': changed_at.isoformat(),
                    'worker_alive_before_release': True}), file=sys.__stdout__, flush=True)
                output, error = child.communicate(timeout=30)
            finally:
                if child.poll() is None:
                    child.kill()
        self.assertEqual(child.returncode, 0, 'ordinary approval child failed: ' + error[-3000:])
        result = json.loads(output)
        print('PG_APPROVAL_EVIDENCE ' + json.dumps({'case': change, 'result_code': result['code'],
            'permission_state': ColumnRiskPermission.objects.get(permission_ref=self.risk_ref).state,
            'approval_event_exists': SecurityAuditRecord.objects.filter(event_id=self.risk_ref + '/approve').exists()}),
            file=sys.__stdout__, flush=True)
        self.assertEqual(result['code'], 'AUTHORIZATION_DENIED')
        self.assertTrue(self.state() == before, 'denied new approval changed retained business/audit state')
        self.assertTrue({path.name: path.read_bytes() for path in self.root.iterdir()} == files)
        self.assertEqual(self.gateway.sink.verify('ds.audit.v2'), audit)
        current = ColumnRiskPermission.objects.get(permission_ref=self.risk_ref)
        self.assertEqual((current.state, current.approval_document, current.approval_event_id), ('pending', None, ''))
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id=self.risk_ref + '/approve').exists())
        self.assertFalse(CTFUser.objects.get(pk=self.reviewer.pk).has_perm(capability))
        self.assertEqual((RiskDecision.objects.count(), IdempotencyRecord.objects.count()), (1, 1))
        for model in (ExportPlanApproval, ExecutionAuthorizationRecord, ExportReport, QuotaExecution,
                      QuotaReservation, QuotaBucket):
            self.assertFalse(model.objects.exists(), model.__name__ + ' unexpectedly created')

    def test_new_conditional_approval_rechecks_removed_reviewer_permission_after_decision_wait(self):
        self.reviewer_change_during_decision_wait('permission-removed')

    def test_new_conditional_approval_rechecks_deactivated_reviewer_after_decision_wait(self):
        self.reviewer_change_during_decision_wait('deactivated')

    def target_pointer_failure(self, case):
        receipt = self.ok(self.risks.approve(user=self.reviewer, permission_ref=self.risk_ref,
                                           decision_id=self.decision_id))
        self.assertEqual(receipt.chain_version, 'ds.audit.v2')
        binding = self.ok(self.entry.bind(user=self.teacher, source_ref=self.source_ref,
            permission_ref=self.permission_ref, risk_permission_ref=self.risk_ref))
        expected = self.state()
        self.assertFalse(expected[ExportPlanApproval])
        files = {path.name: path.read_bytes() for path in self.root.iterdir()}
        previous_audit = self.ok(self.gateway.sink.verify('ds.audit.v2'))
        with _spawn_approval(self, case) as child:
            try:
                output, error = child.communicate(timeout=90)
            finally:
                if child.poll() is None:
                    child.kill()
        self.assertEqual(child.returncode, 0, 'ordinary target approval child failed: ' + error[-3000:])
        result = json.loads(output)
        self.assertEqual(result['hits'], [case])
        self.assertEqual(result['code'], 'DELIVERY_UNKNOWN')
        approval = ExportPlanApproval.objects.get()
        self.assertEqual(approval.approval_ref, result['approval_ref'])
        self.assertEqual((approval.document['requested_by'], approval.document['approved_by']),
                         (binding.subject_ref, 'user/' + str(self.reviewer.pk)))
        self.assertEqual(approval.binding_hash, content_hash(binding))
        self.assertEqual(approval.plan_hash, approval.document['content_hash'])
        self.assertIsNone(approval.revoked_at)
        event = SecurityAuditRecord.objects.get(event_id=approval.approval_ref + '/approve')
        self.assertEqual((event.event['kind'], event.event['object_ref']), ('authorization', approval.approval_ref))
        self.assertEqual(event.event['algorithm_versions'], ['export-plan-approval.v1', 'approve'])
        self.assertTrue(AuthenticatedAuditEntry.objects.filter(record=event).exists())
        approval_audit = self.ok(self.gateway.sink.verify('ds.audit.v2'))
        self.assertEqual((approval_audit.chain_version, approval_audit.event_id, approval_audit.sequence),
                         ('ds.audit.v2', event.event_id, previous_audit.sequence + 1))
        current = self.state()
        for model in (ExportPlanApproval, AuditEvent, SecurityAuditRecord, AuthenticatedAuditEntry):
            self.assertEqual(len(current[model]), len(expected[model]) + 1, model.__name__ + ' did not add exactly A')
            expected[model].append(current[model][-1])
        if case == 'source-ack':
            expected[ExportSource][0]['target_approval_ref'] = approval.approval_ref
        self.assertTrue(current == expected, 'source handoff fault changed unrelated business state')
        self.assertEqual(ExportSource.objects.get().target_approval_ref,
                         approval.approval_ref if case == 'source-ack' else '')
        self.assertTrue({path.name: path.read_bytes() for path in self.root.iterdir()} == files)
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())
        print('PG_APPROVAL_EVIDENCE ' + json.dumps({'case': case, 'fault_hits': len(result['hits']),
            'target_approvals': ExportPlanApproval.objects.count(), 'approval_chain': approval_audit.chain_version,
            'source_pointer_saved': bool(ExportSource.objects.get().target_approval_ref),
            'returned_trace_matches_committed_approval': result['trace_id'] == approval.approval_ref}),
            file=sys.__stdout__, flush=True)
        self.assertEqual(result['trace_id'], approval.approval_ref,
                         'the returned trace must retain committed target A, not a source-stage label')

        expected[ExportSource][0]['target_approval_ref'] = result['trace_id']
        for _ in range(2):
            # Existing ordinary-startup helper forbids manage/write_permission during real reconciliation.
            recovered = formal_call(self, 'boundary', case='target-reconcile', source_ref=self.source_ref,
                permission_ref=self.permission_ref, approval_ref=result['trace_id'])
            self.assertEqual(recovered, {'approval_ref': approval.approval_ref})
            self.assertTrue(self.state() == expected, 'reconciliation changed more than the exact source pointer')
            self.assertEqual(self.gateway.sink.verify('ds.audit.v2'), approval_audit)
            self.assertTrue({path.name: path.read_bytes() for path in self.root.iterdir()} == files)

        delivered = formal_call(self, 'execute', source_ref=self.source_ref, permission_ref=self.permission_ref)
        delivery = DeliveryReceipt.from_wire(delivered['delivery'])
        self.assertEqual(delivery.binding, binding)
        self.assertEqual(delivery.delivered_records, 2)
        self.assertTrue(list(ExportPlanApproval.objects.order_by('pk').values()) == expected[ExportPlanApproval])
        self.assertEqual(SecurityAuditRecord.objects.filter(
            event__algorithm_versions=['export-plan-approval.v1', 'approve']).count(), 1)
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        self.assertEqual((ColumnRiskPermission.objects.get().state, RiskDecision.objects.get().decision_id),
                         ('approved', self.decision_id))
        authorization = ExecutionAuthorizationRecord.objects.get()
        self.assertEqual((authorization.authorization_id, authorization.state), (binding.authorization_id, 'consumed'))
        self.assertIsNotNone(authorization.consumed_at)
        report = ExportReport.objects.get()
        self.assertEqual((report.execution_id, report.state), (binding.execution_id, 'prepared'))
        self.assertTrue(report.delivery_receipt == delivered['delivery'])
        reservation = QuotaReservation.objects.get()
        self.assertEqual((reservation.reservation_id, reservation.state), (binding.reservation_id, 'committed'))
        quota = QuotaExecution.objects.get()
        self.assertEqual((quota.reservation_id, quota.terminal_operation), (binding.reservation_id, 'commit'))
        self.assertIsNotNone(quota.terminal_receipt)
        self.assertIsNone(quota.unknown_receipt)
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 0, 2))
        self.assertEqual(sorted(PrivateObject.objects.values_list('state', flat=True)), ['published', 'verified'])
        self.assertEqual(IdempotencyRecord.objects.count(), 2)
        self.assertEqual(self.gateway.sink.verify('ds.audit.v2'), delivery.audit)

    def test_target_source_pointer_save_failure_recovers_returned_approval_trace(self):
        self.target_pointer_failure('source-save')

    def test_target_source_pointer_acknowledgement_loss_recovers_returned_approval_trace(self):
        self.target_pointer_failure('source-ack')
