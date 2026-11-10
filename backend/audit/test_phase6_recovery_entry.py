"""Recovery-only B entry uses the original flow, real quota authority and current user."""
from dataclasses import replace
from datetime import timedelta

from django.contrib.auth.models import Permission
from django.test import TransactionTestCase
from django.utils import timezone

from ctf_backend.security_bootstrap import assemble_export_recovery, assemble_recovery_permissions
from data_security.adapters.persistence.models import ExportReport
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import (
    ActionPlan, Environment, ExecutionBinding, ObjectContext, QuotaReceipt, QuotaState, ReasonCode,
)
from data_security.tests.fixtures import examples
from export_quota.models import QuotaBucket, QuotaReservation
from resources.test_phase6_private_uploads import PrivateResourceUploadFixture
from users.models import CTFUser
from .models import AuthenticatedAuditEntry


class RecoveryEntryTests(PrivateResourceUploadFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.operator = CTFUser.objects.create_user(username='explicit-recovery-operator', role='student')
        self.teacher.user_permissions.add(Permission.objects.get(
            content_type__app_label='security_policies', codename='add_recoverypermission'))
        values = examples()
        self.binding = replace(values[ExecutionBinding], environment='evaluation',
            expires_at=timezone.now() + timedelta(minutes=5))
        context = replace(values[ObjectContext], environment=Environment.EVALUATION,
            object_version=self.binding.asset_version, authorization_ref=self.binding.authorization_id)
        self.reports = DjangoReportRepository(environment=Environment.EVALUATION)
        with DjangoUnitOfWork() as work:
            self.assertIs(self.reports.begin(values[ActionPlan], self.binding, context), True)
            work.commit()
        self.quota = DjangoQuotaPort(environment='evaluation', window_key='recovery-entry', limit=20)
        self.assertIs(type(self.quota.reserve(self.binding)), QuotaReceipt)
        self.assertIs(self.quota.reconcile(self.binding, None, 'synthetic/unknown').state, QuotaState.UNKNOWN)
        owner = assemble_recovery_permissions(config_path=self.config_path)
        self.reference, _ = owner.manage(user=self.teacher, binding=self.binding, operation='grant',
            grantee_id=self.operator.pk, expires_at=timezone.now() + timedelta(minutes=5), allow_reconcile=True)
        self.entry = assemble_export_recovery(config_path=self.config_path, user=self.operator,
            authorization_ref=self.reference, window_key='recovery-entry', limit=20)

    def test_explicit_recovery_entry_fences_and_settles_unknown_once_without_new_reservation(self):
        self.assertEqual(set(self.entry), {'release', 'reconcile'})
        denied = self.entry['release'](self.binding)
        self.assertEqual(denied.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)
        result = self.entry['reconcile'](self.binding)
        self.assertIs(type(result), QuotaReceipt)
        self.assertIs(result.state, QuotaState.COMMITTED)
        self.assertEqual(result.settled_amount, 0)
        self.assertEqual(self.entry['reconcile'](self.binding), result)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(ExportReport.objects.get().state, 'aborted')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.unknown_reserved, bucket.active_reserved, bucket.settled), (0, 0, 0))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
        self.assertEqual(self.uploads.audit.sink.verify('ds.audit.v2').sequence, 3)

    def test_deactivated_actor_after_assembly_cannot_fence_or_release_unknown(self):
        CTFUser.objects.filter(pk=self.operator.pk).update(is_active=False)
        result = self.entry['reconcile'](self.binding)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertEqual(QuotaReservation.objects.get().state, 'unknown')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, self.binding.quantity)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
