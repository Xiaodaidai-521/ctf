"""6-F02: normal startup re-fetches real source, risk, target and quota owners."""
from contextlib import ExitStack
from dataclasses import replace
from datetime import timedelta
import hashlib
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution
from data_security.contracts import DeliveryReceipt, ExecutionBinding, ProtectionError, ReasonCode, content_hash
from export_quota.models import QuotaBucket, QuotaReservation
from export_risk.models import ColumnRiskPermission, ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision
from users.models import CTFUser

from .models import ExportSource, ExportSourcePermission
from .test_phase6_formal_fixtures import CONTENT, FormalResourceFixture, create_original, formal_call, source_inputs


EXPECTED = b"Notes,Email\n'=1+1,[EMAIL]\nrecord,[EMAIL]\n"


def invoke_formal(operation, fields):
    from data_security.adapters.django.export_delivery import export_delivery
    from data_security.adapters.persistence.export_delivery import DjangoResourceExports
    from data_security.adapters.persistence.private_store import DjangoPrivateStore
    from data_security.adapters.persistence.quota import DjangoQuotaPort
    from data_security.adapters.persistence.report_records import DjangoReportRepository
    from data_security.adapters.persistence.risk import DjangoRiskPort
    from data_security.application.table_reports import TableReportExecutor
    import export_risk.column_authority as column_authority
    from export_risk.column_authority import ColumnRiskSupplier
    from .export_sources import ResourceExportSources

    entry = export_delivery()
    if operation == 'startup':
        return {'code': entry.code.value} if isinstance(entry, ProtectionError) else {
            'entry': type(entry).__name__, 'source_owner': type(entry.sources).__name__,
            'risk_owner': type(entry.risks).__name__, 'target_owner': type(entry.targets).__name__}
    assert type(entry) is DjangoResourceExports, 'ordinary startup did not compose the real supplier'
    user = CTFUser.objects.get(pk=fields['user'])
    reviewer = CTFUser.objects.get(pk=fields['reviewer'])

    def checked(value):
        assert not isinstance(value, ProtectionError), 'real owner rejected ' + (
            value.code.value if isinstance(value, ProtectionError) else '')
        return value

    if operation == 'full':
        resource = checked(create_original(entry, user))
        source_ref, _ = checked(entry.sources.register(user=user, resource_id=resource.pk, **source_inputs()))
        checked(entry.sources.approve(user=reviewer, source_ref=source_ref))
        permission_ref, _ = checked(entry.sources.grant(user=reviewer, source_ref=source_ref,
            grantee_id=user.pk, expires_at=timezone.now() + timedelta(minutes=20)))
        risk_ref, _ = checked(entry.grant_risk(user=reviewer, source_ref=source_ref,
            expires_at=timezone.now() + timedelta(minutes=20)))
        assessment, decision_id, blocker = checked(entry.admit(user=user, source_ref=source_ref,
            permission_ref=permission_ref, risk_permission_ref=risk_ref))
        assert blocker is not None, 'missing profile was silently executable'
        checked(entry.risks.approve(user=reviewer, permission_ref=risk_ref, decision_id=decision_id))
        binding = checked(entry.bind(user=user, source_ref=source_ref, permission_ref=permission_ref,
                                    risk_permission_ref=risk_ref))
        plan = checked(entry.approve_target(user=reviewer, source_ref=source_ref, requester=user))
        stages = []
        def observe(name, original):
            def recorded(*args, **kwargs):
                stages.append([name, connection.in_atomic_block])
                return original(*args, **kwargs)
            return recorded
        with ExitStack() as stack:
            for owner, method, name in (
                (DjangoReportRepository, 'begin', 'begin'), (DjangoQuotaPort, 'reserve', 'reserve'),
                (DjangoRiskPort, 'issue', 'issue'), (ResourceExportSources, 'load_input', 'input'),
                (TableReportExecutor, 'prepare', 'prepare'), (DjangoReportRepository, 'put', 'put'),
                (DjangoRiskPort, 'consume', 'consume'), (DjangoPrivateStore, 'publish', 'publish'),
                (DjangoQuotaPort, 'commit', 'settle'), (DjangoReportRepository, 'record_delivery', 'receipt'),
            ):
                stack.enter_context(patch.object(owner, method, observe(name, getattr(owner, method))))
            import data_security.adapters.persistence.risk as risk_adapter
            stack.enter_context(patch.object(risk_adapter, 'claim', observe('claim', risk_adapter.claim)))
            receipt = checked(entry.execute(user=user, source_ref=source_ref, permission_ref=permission_ref))
        with patch.object(entry.sources, 'read_original', side_effect=AssertionError('output read reopened original')), \
             patch.object(ColumnRiskSupplier, 'assess', side_effect=AssertionError('output read reassessed risk')), \
             patch.object(column_authority, 'assess_risk', side_effect=AssertionError('output read reran judgment')), \
             patch.object(DjangoRiskPort, 'issue', side_effect=AssertionError('output read issued again')):
            output = checked(entry.open_delivery(user=user, source_ref=source_ref, permission_ref=permission_ref))
        assert output.binary == EXPECTED, 'actual protected CSV output differs'
        return {'source_ref': source_ref, 'permission_ref': permission_ref, 'risk_ref': risk_ref,
            'binding': binding.to_wire(), 'delivery': receipt.to_wire(), 'stages': stages,
            'action': assessment.recommended_action.value, 'source_state': plan.source.source_state,
            'source_approval_ref': plan.source.approval_basis_ref,
            'target_approval_ref': plan.approval.approval_ref,
            'input_hash': hashlib.sha256(CONTENT).hexdigest(), 'output_hash': hashlib.sha256(output.binary).hexdigest()}

    source_ref, permission_ref = fields['source_ref'], fields['permission_ref']
    if operation == 'fault':
        from .test_phase6_formal_failures import invoke_fault
        return invoke_fault(entry, user, reviewer, fields)
    if operation == 'boundary':
        from .test_phase6_formal_boundaries import invoke_boundary
        return invoke_boundary(entry, user, reviewer, fields)
    if operation == 'replay':
        with ExitStack() as stack:
            for owner, method in (
                (entry.sources, 'read_original'), (ColumnRiskSupplier, 'assess'),
                (ColumnRiskSupplier, 'admit'), (column_authority, 'assess_risk'),
                (DjangoRiskPort, 'issue'),
                (DjangoQuotaPort, 'reserve'), (DjangoPrivateStore, 'publish'),
                (TableReportExecutor, 'prepare'), (entry.targets, 'manage'),
            ):
                stack.enter_context(patch.object(owner, method,
                    side_effect=AssertionError('complete-binding replay repeated ' + method)))
            binding = checked(entry.bind(user=user, source_ref=source_ref, permission_ref=permission_ref,
                                         risk_permission_ref=fields['risk_ref']))
            checked(entry.approve_target(user=reviewer, source_ref=source_ref, requester=user))
            result = entry.execute(user=user, source_ref=source_ref, permission_ref=permission_ref)
        return {'binding': binding.to_wire(), 'delivery': checked(result).to_wire()}
    if operation == 'bind':
        value = entry.bind(user=user, source_ref=source_ref, permission_ref=permission_ref,
                           risk_permission_ref=fields['risk_ref'])
    elif operation == 'execute':
        value = entry.execute(user=user, source_ref=source_ref, permission_ref=permission_ref)
    elif operation == 'open':
        with patch.object(entry.sources, 'read_original', side_effect=AssertionError('output read reopened original')), \
             patch.object(ColumnRiskSupplier, 'assess', side_effect=AssertionError('output read reassessed risk')), \
             patch.object(column_authority, 'assess_risk', side_effect=AssertionError('output read reran judgment')):
            value = entry.open_delivery(user=user, source_ref=source_ref, permission_ref=permission_ref)
        if not isinstance(value, ProtectionError):
            assert value.binary == EXPECTED, 'actual protected CSV output differs'
            return {'output_hash': hashlib.sha256(value.binary).hexdigest()}
    else:
        raise AssertionError('unknown formal test operation')
    if isinstance(value, ProtectionError):
        return {'code': value.code.value}
    return {('binding' if isinstance(value, ExecutionBinding) else 'delivery'): value.to_wire()}


class FormalDeliveryTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def state(self, *, include_audit=True):
        models = (ExportSource, ExportSourcePermission, ColumnRiskPermission, RiskDecision,
                  IdempotencyRecord, ExecutionAuthorizationRecord, ExportPlanApproval, ExportReport,
                  PrivateObject, QuotaExecution, QuotaReservation, QuotaBucket)
        if include_audit:
            models += (AuthenticatedAuditEntry, SecurityAuditRecord)
        return tuple(list(model.objects.order_by('pk').values()) for model in models)

    def full(self):
        return formal_call(self, 'full')

    def test_ordinary_startup_is_closed_without_explicit_delivery_configuration(self):
        del self.config['export_delivery']
        self.write_config()
        before = self.state()
        self.assertEqual(formal_call(self, 'startup'), {'code': 'SOURCE_NOT_APPROVED'})
        self.assertEqual(self.state(), before)

    def test_ordinary_startup_composes_complete_actual_owner_chain_and_single_delivery(self):
        startup = formal_call(self, 'startup')
        self.assertEqual(startup, {'entry': 'DjangoResourceExports', 'source_owner': 'ResourceExportSources',
            'risk_owner': 'ColumnRiskOwner', 'target_owner': 'ExportPlanOwner'})
        value = self.full()
        binding = ExecutionBinding.from_wire(value['binding'])
        receipt = DeliveryReceipt.from_wire(value['delivery'])
        self.assertEqual(receipt.binding, binding)
        self.assertEqual(receipt.delivered_records, 2)
        self.assertEqual(value['action'], 'require_approval')
        self.assertEqual(value['source_state'], 'not-declared')
        self.assertNotEqual(value['source_approval_ref'], value['target_approval_ref'])
        self.assertEqual(value['stages'], [
            ['begin', True], ['reserve', True], ['issue', False], ['claim', True],
            ['input', False], ['prepare', False], ['put', False], ['consume', True],
            ['publish', True], ['settle', True], ['receipt', True]])
        self.assertEqual((ExportSource.objects.count(), ExportSourcePermission.objects.count(),
            ColumnRiskPermission.objects.count(), RiskDecision.objects.count(),
            ExecutionAuthorizationRecord.objects.count(), ExportPlanApproval.objects.count(),
            ExportReport.objects.count(), QuotaReservation.objects.count()), (1,) * 8)
        self.assertEqual(RiskDecision.objects.get().action, 'require_approval')
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
        self.assertEqual(QuotaReservation.objects.get().state, 'committed')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 0, 2))
        self.assertEqual(sorted(PrivateObject.objects.values_list('state', flat=True)), ['published', 'verified'])
        report = ExportReport.objects.get()
        self.assertEqual(report.document['plan']['input_hash'], value['input_hash'])
        self.assertEqual(report.document['report']['output_hash'], value['output_hash'])
        self.assertEqual(value['output_hash'], hashlib.sha256(EXPECTED).hexdigest())
        decision_key = 'ds-risk/' + content_hash({'request': vars(self.entry._load(user=self.teacher,
            source_ref=value['source_ref'], permission_ref=value['permission_ref'])[1]),
            'scope': binding.scope, 'domain': binding.domain_ref, 'policy': binding.policy_binding})
        self.assertEqual(IdempotencyRecord.objects.get(key=decision_key).result_ref, binding.decision_id)
        self.assertEqual(IdempotencyRecord.objects.count(), 2)
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        self.assertEqual(self.gateway.sink.verify('ds.audit.v2').chain_version, 'ds.audit.v2')
        for path in self.root.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(CONTENT, path.read_bytes())
            self.assertNotIn(b'first@example.invalid', path.read_bytes())
            self.assertNotIn(b'second@example.invalid', path.read_bytes())

    def test_complete_binding_replay_after_fresh_startup_never_reopens_or_reassesses_or_resettles(self):
        value = self.full()
        before = self.state()
        replay = formal_call(self, 'replay', source_ref=value['source_ref'],
            permission_ref=value['permission_ref'], risk_ref=value['risk_ref'])
        self.assertEqual(replay, {'binding': value['binding'], 'delivery': value['delivery']})
        self.assertEqual(self.state(), before)

    def test_missing_profile_pending_approval_cannot_bind_or_reserve(self):
        source_ref, permission_ref = self.approved_source()
        risk_ref, _ = self.ok(self.entry.grant_risk(user=self.reviewer, source_ref=source_ref,
            expires_at=timezone.now() + timedelta(minutes=10)))
        before = self.state()
        self.assertEqual(formal_call(self, 'bind', source_ref=source_ref, permission_ref=permission_ref,
            risk_ref=risk_ref), {'code': 'AUTHORIZATION_DENIED'})
        self.assertIsNone(ExportSource.objects.get().execution_document)
        self.assertEqual(RiskDecision.objects.get().action, 'require_approval')
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(ExportPlanApproval.objects.exists())
        self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertEqual(self.state()[0:3], before[0:3])

    def test_source_permission_and_target_approval_do_not_substitute_for_current_risk_use(self):
        source_ref, permission_ref, _, _ = self.ready()
        permission = self.teacher.user_permissions.get(codename='use_columnriskpermission')
        self.teacher.user_permissions.remove(permission)
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(self.state(), before)
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())

    def test_current_source_risk_and_target_revocation_before_reserve_have_no_new_effect(self):
        source_ref, permission_ref, risk_ref, binding = self.ready()
        owned = self.ok(self.entry._bound(user=self.teacher, source_ref=source_ref, permission_ref=permission_ref))
        self.ok(self.entry.targets.manage(user=self.reviewer, operation='revoke', plan=owned.plan,
            binding=binding, context=owned.context))
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(self.state(), before)
        self.ok(self.risks.revoke(user=self.reviewer, permission_ref=risk_ref))
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(self.state(), before)
        self.ok(self.sources.revoke_permission(user=self.reviewer, permission_ref=permission_ref))
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'SOURCE_NOT_APPROVED'})
        self.assertEqual(self.state(), before)
        self.assertFalse(QuotaReservation.objects.exists())

    def test_different_retained_complete_binding_and_risk_reference_conflict_before_effects(self):
        source_ref, permission_ref, risk_ref, binding = self.ready()
        self.assertEqual(formal_call(self, 'bind', source_ref=source_ref, permission_ref=permission_ref,
            risk_ref='risk-use/other'), {'code': 'IDEMPOTENCY_CONFLICT'})
        row = ExportSource.objects.get(source_ref=source_ref)
        changed = replace(binding, reservation_id='reservation/other').to_wire()
        ExportSource.objects.filter(pk=row.pk).update(execution_document={**row.execution_document, 'binding': changed})
        before = self.state()
        self.assertEqual(formal_call(self, 'execute', source_ref=source_ref, permission_ref=permission_ref),
                         {'code': 'REPORT_MISMATCH'})
        self.assertEqual(self.state(), before)
        self.assertFalse(QuotaReservation.objects.exists())
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())

    def test_current_source_risk_and_requester_are_required_for_delivered_output_without_new_business_state(self):
        value = self.full()
        before = self.state(include_audit=False)
        self.assertEqual(formal_call(self, 'open', source_ref=value['source_ref'],
            permission_ref=value['permission_ref']), {'output_hash': value['output_hash']})
        self.assertEqual(self.state(include_audit=False), before)
        self.ok(self.risks.revoke(user=self.reviewer, permission_ref=value['risk_ref']))
        before = self.state()
        self.assertEqual(formal_call(self, 'open', source_ref=value['source_ref'],
            permission_ref=value['permission_ref']), {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(self.state(), before)
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
        before = self.state()
        self.assertEqual(formal_call(self, 'open', source_ref=value['source_ref'],
            permission_ref=value['permission_ref']), {'code': 'AUTHORIZATION_DENIED'})
        self.assertEqual(self.state(), before)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), 1)
