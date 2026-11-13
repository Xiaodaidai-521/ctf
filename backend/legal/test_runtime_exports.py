"""Exercise the real runtime report export with disposable keys, files and users."""
from datetime import timedelta
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLedgerEntry
from audit.services import AuditLedgerService
from data_security.adapters.persistence import fields
from data_security.runtime.crypto import MAGIC
from data_security.runtime.fields import RuntimeFieldStorage
from learning_paths.models import LearningPath
from users.models import CTFUser, CourseDataGrant

from .models import LegalAnalysisTask, LegalFactSnapshot, LegalReport, LegalReportExport
from .services import report_exports
from .services.compliance_orchestrator import ComplianceOrchestrator


class RuntimeReportExportTests(TestCase):
    def setUp(self):
        original = fields._adapter
        self.addCleanup(fields.bind_field_storage, original)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'security'
        override = override_settings(DATA_PROTECTION_ENABLED=True, DATA_SECURITY_FORMAL_MODE=False,
            DATA_PROTECTION_ROOT=self.root, DATA_PROTECTION_KEY_FILE=self.root / 'storage.key')
        override.enable()
        self.addCleanup(override.disable)
        fields.bind_field_storage(RuntimeFieldStorage())
        self.actor = CTFUser.objects.create_user(username='export-admin', role='admin')
        self.other = CTFUser.objects.create_user(username='export-other-admin', role='admin')
        self.student = CTFUser.objects.create_user(username='export-student')
        self.client = APIClient()
        self.client.force_authenticate(self.actor)
        self.report = LegalReport.objects.create(generated_by=self.actor,
            title='Report owner@example.com', summary='Phone 13812345678',
            content='Keep this finding. owner@example.com 13812345678 110101199001011234 token=secret-value '
                    'JSON {"token": "quoted secret value"} and authorization: Bearer bearer-secret')

    def export(self, report=None, query=''):
        return self.client.post(f'/api/legal/reports/{(report or self.report).pk}/export/{query}', {}, format='json')

    def download(self, record):
        return self.client.get(f'/api/legal/reports/{record.report_id}/export-file/{record.pk}/')

    def test_http_export_redacts_encrypts_and_records_actual_file(self):
        response = self.export()
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        record = LegalReportExport.objects.get()
        self.assertEqual(response['X-Export-ID'], str(record.pk))
        content = response.content
        self.assertIn(b'Keep this finding.', content)
        for marker in (b'owner@example.com', b'13812345678', b'110101199001011234', b'secret-value',
                       b'quoted secret value', b'bearer-secret'):
            self.assertNotIn(marker, content)
        stored = report_exports.artifact_path(record).read_bytes()
        self.assertTrue(stored.startswith(MAGIC))
        self.assertNotIn(b'Keep this finding.', stored)
        self.assertEqual(report_exports.read_artifact(record), content)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'exported')
        self.assertEqual(self.report.content, '')
        self.assertIn('owner@example.com', self.report.read_protected('content'))
        self.assertEqual(AuditLedgerEntry.objects.filter(event_category='report_export').count(), 2)
        self.assertTrue(AuditLedgerService.verify_chain().is_valid)
        listing = self.client.get('/api/data-security/exports/records/').json()
        self.assertEqual(len(listing['items']), 1)
        self.assertTrue(listing['items'][0]['can_download'])
        self.assertEqual(listing['items'][0]['protection'], {'redaction': 'completed', 'storage': 'encrypted'})
        self.assertEqual(self.download(record).content, content)

    def test_role_and_subject_must_both_authorize_generation(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.export().status_code, 404)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.export().status_code, 403)
        self.assertFalse(LegalReportExport.objects.exists())

    def test_export_is_bound_to_requesting_actor_and_report(self):
        self.assertEqual(self.export().status_code, 200)
        record = LegalReportExport.objects.get()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.download(record).status_code, 404)
        self.assertEqual(self.client.get('/api/data-security/exports/records/').json()['items'], [])
        self.client.force_authenticate(self.actor)
        other_report = LegalReport.objects.create(generated_by=self.actor, title='Other', content='Other')
        response = self.client.get(f'/api/legal/reports/{other_report.pk}/export-file/{record.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_current_course_grant_is_rechecked_after_generation(self):
        course = LearningPath.objects.create(title='Export course')
        grant = CourseDataGrant.objects.create(actor=self.actor, student=self.student, course=course, granted_by=self.actor,
            expires_at=timezone.now() + timedelta(hours=1))
        report = LegalReport.objects.create(generated_by=self.student, title='Student report', content='Private source')
        self.assertEqual(self.export(report).status_code, 404)
        self.assertEqual(self.export(report, f'?course={course.pk}').status_code, 200)
        record = LegalReportExport.objects.get()
        self.assertEqual(self.download(record).status_code, 200)
        grant.active = False
        grant.save(update_fields=['active'])
        self.assertEqual(self.download(record).status_code, 404)
        self.assertEqual(self.client.get('/api/data-security/exports/records/').json()['items'], [])

    def test_role_revocation_and_expiry_block_existing_exports(self):
        self.assertEqual(self.export().status_code, 200)
        record = LegalReportExport.objects.get()
        CTFUser.objects.filter(pk=self.actor.pk).update(role='student')
        self.assertEqual(self.download(record).status_code, 403)
        CTFUser.objects.filter(pk=self.actor.pk).update(role='admin')
        LegalReportExport.objects.filter(pk=record.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.download(record).status_code, 404)

    def test_fact_subject_scope_takes_precedence_over_task_creator(self):
        task = LegalAnalysisTask.objects.create(created_by=self.actor, title='Course review', input_text='Input')
        LegalFactSnapshot.objects.create(analysis_task=task, confirmed_by=self.actor,
            scope={'subject_user_id': self.student.pk}, source_kind='automated',
            preview_hash='a' * 64, snapshot_hash='b' * 64)
        report = LegalReport.objects.create(task=task, generated_by=self.actor, title='Review', content='Finding')
        self.assertEqual(self.export(report).status_code, 404)
        course = LearningPath.objects.create(title='Fact course')
        CourseDataGrant.objects.create(actor=self.actor, student=self.student, course=course,
            granted_by=self.actor, expires_at=timezone.now() + timedelta(hours=1))
        self.assertEqual(self.export(report, f'?course={course.pk}').status_code, 200)

    def test_ciphertext_damage_is_never_reported_as_completed_or_delivered(self):
        self.assertEqual(self.export().status_code, 200)
        record = LegalReportExport.objects.get()
        path = report_exports.artifact_path(record)
        content = path.read_bytes()
        path.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
        initial_audits = AuditLedgerEntry.objects.count()
        self.assertEqual(self.download(record).status_code, 503)
        self.assertEqual(AuditLedgerEntry.objects.count(), initial_audits)
        row = self.client.get('/api/data-security/exports/records/').json()['items'][0]
        self.assertFalse(row['can_download'])
        self.assertEqual(row['protection'], {'redaction': 'unknown', 'storage': 'unknown'})

    def test_changed_metadata_cannot_authenticate_file(self):
        self.assertEqual(self.export().status_code, 200)
        record = LegalReportExport.objects.get()
        LegalReportExport.objects.filter(pk=record.pk).update(byte_size=record.byte_size + 1)
        self.assertEqual(self.download(record).status_code, 503)

    def test_generation_audit_failure_rolls_back_status_record_and_file(self):
        with patch.object(report_exports, 'audit', side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.export().status_code, 503)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'draft')
        self.assertFalse(LegalReportExport.objects.exists())
        self.assertEqual(list((self.root / 'report-exports').glob('*.bin')), [])

    def test_download_audit_failure_never_delivers_plaintext(self):
        self.assertEqual(self.export().status_code, 200)
        record = LegalReportExport.objects.get()
        with patch.object(report_exports, 'audit', side_effect=RuntimeError('unavailable')):
            response = self.download(record)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'Keep this finding.', response.content)

    def test_custom_payload_and_malformed_reference_are_rejected(self):
        response = self.client.post(f'/api/legal/reports/{self.report.pk}/export/',
            {'content': 'unreviewed'}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.get(f'/api/legal/reports/{self.report.pk}/export-file/{"-" * 36}/')
        self.assertEqual(response.status_code, 404)

    def test_formal_mode_never_uses_runtime_export_shortcut(self):
        with override_settings(DATA_SECURITY_FORMAL_MODE=True):
            self.assertEqual(self.export().status_code, 409)
        self.assertFalse(LegalReportExport.objects.exists())

    def test_failed_analysis_redacts_exception_without_losing_protected_input(self):
        task = LegalAnalysisTask.objects.create(created_by=self.actor, title='Failure',
            input_text='Retain this input owner@example.com')
        orchestrator = ComplianceOrchestrator()
        orchestrator._mark_failed(task=task, actor=self.actor,
            error=RuntimeError('Provider error owner@example.com token=secret-value'))
        task.refresh_from_db()
        self.assertEqual(task.status, 'failed')
        self.assertNotIn('owner@example.com', task.error_message)
        self.assertNotIn('secret-value', task.error_message)
        self.assertEqual(task.read_protected('input_text'), 'Retain this input owner@example.com')
