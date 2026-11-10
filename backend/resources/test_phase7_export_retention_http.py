"""Synthetic PG/HTTP export retention with real source, risk, target and delivery owners."""
from dataclasses import replace
from datetime import timedelta
import os
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.django import export_delivery, private_files
from data_security.adapters.persistence.models import ExportReport, PrivateObject
from data_security.contracts import (
    Environment, FrozenJSON, ProtectionContext, ProtectionError, Purpose, ReportRecord, Role,
)
from data_security.tests.fixtures import examples
from export_quota.models import QuotaBucket

from .models import Resource
from .test_phase6_formal_delivery import EXPECTED
from .test_phase6_formal_fixtures import CONTENT, FormalResourceFixture


class ResourceExportRetentionHTTPTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def setUp(self):
        super().setUp()
        facts = self.config_path.parent / 'retention-facts'
        facts.mkdir(mode=0o700)
        facts.chmod(0o700)
        self.config['private_files'] = {'private_root': str(self.root), 'project_ref': 'formal-column/synthetic'}
        self.config['export_retention'] = {'scope_ref': 'retention/phase7-http-fixture', 'journal_root': str(facts)}
        self.write_config()
        self.components = assemble(config_path=self.config_path)
        self.entry = self.components['export_delivery']
        self.sources, self.risks = self.entry.sources, self.entry.risks
        self.lifecycle = self.components['export_lifecycle']
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', role=Role.SERVICE,
            environment=Environment.EVALUATION, domain='ctf', purpose=Purpose.STORAGE)
        for setting in (patch.object(export_delivery, '_entry', self.entry),
                        patch.object(private_files, '_owners', self.components['private_uploads']),
                        patch.object(private_files, '_shares', self.components['file_shares']),
                        patch.dict(os.environ, DATA_SECURITY_CONFIG=str(self.config_path)),
                        override_settings(ALLOWED_HOSTS=['testserver'],
                            MIDDLEWARE=['ctf_backend.security_bootstrap.private_upload_middleware'])):
            self.enterContext(setting)
        self.client = APIClient()
        self.client.force_authenticate(self.teacher)

    def original(self):
        response = self.client.post('/api/resources/upload/', {
            'title': '合成保留资料', 'description': '隔离测试资料', 'resource_type': 'document', 'category': 'security',
            'file': SimpleUploadedFile('synthetic.txt', CONTENT, content_type='text/plain')},
            format='multipart', HTTP_X_FILE_OPERATION_ID=str(uuid4()))
        self.assertEqual(response.status_code, 201, response.data)
        resource = Resource.objects.get(pk=response.data['resource']['id'])
        self.assertEqual(resource.private_files['schema_version'], 'resource.private-upload.v2')
        return resource

    def export(self):
        source_ref, permission_ref, _, binding = self.ready()
        inputs = {path.name: path.read_bytes() for path in self.root.glob('*.sealed')}
        body = {'source_ref': source_ref, 'permission_ref': permission_ref}
        response = self.client.post('/api/data-security/exports/resources/execute/', body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['state'], 'logically_delivered')
        self.assertFalse(response.data['network_delivery_confirmed'])
        record = self.lifecycle.reports.read(binding)
        self.assertIsInstance(record, ReportRecord)
        row = ExportReport.objects.get(execution_id=binding.execution_id)
        self.assertEqual(row.retention_scope, self.lifecycle.scope_ref)
        self.assertIsNotNone(row.retention_registration)
        return body, row, record, inputs

    def expired_preview(self, record):
        self.assertIsInstance(self.lifecycle.initialize(self.context), FrozenJSON)
        self.now = record.report.created_at + timedelta(hours=24)
        self.lifecycle.clock = self.components['audit'].sink.clock = lambda: self.now
        approved = self.lifecycle.preview(self.context)
        self.assertIsInstance(approved, FrozenJSON)
        self.assertEqual(len(approved.to_value()['exports']), 1)
        return approved

    def test_real_http_output_is_retired_without_removing_input_or_reissuing_delivery(self):
        body, row, record, inputs = self.export()
        self.assertTrue(inputs)
        downloaded = self.client.post('/api/data-security/exports/resources/download/', body, format='json')
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, EXPECTED)
        self.assertEqual(downloaded['Cache-Control'], 'no-store')
        original_document, original_delivery = row.document, row.delivery_receipt
        target = self.root / (record.stored.object_ref.removeprefix('private/') + '.sealed')
        self.assertTrue(target.exists())
        approved = self.expired_preview(record)
        self.assertEqual(approved.to_value()['exports'][0]['created_at'], record.report.created_at.isoformat())
        self.assertEqual(approved.to_value()['exports'][0]['expires_at'], self.now.isoformat())
        with patch.object(self.components['crypto'], 'open', side_effect=AssertionError('retirement must not decrypt')):
            retired = self.lifecycle.apply(approved, self.context)
        self.assertIsInstance(retired, tuple)
        self.assertEqual(len(retired), 1)
        row.refresh_from_db()
        self.assertEqual(row.state, 'retired')
        self.assertEqual((row.document, row.delivery_receipt), (original_document, original_delivery))
        self.assertEqual(PrivateObject.objects.get(object_ref=record.stored.object_ref).state, 'retired')
        self.assertFalse(target.exists())
        for name, data in inputs.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assertLess(timezone.now(), record.binding.expires_at)
        with patch.object(self.components['crypto'], 'open', side_effect=AssertionError('retired output reopened')):
            refused = self.client.post('/api/data-security/exports/resources/download/', body, format='json')
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.data['code'], 'AUTHORIZATION_DENIED')
        self.assertNotIn(EXPECTED, refused.content)
        repeated = self.client.post('/api/data-security/exports/resources/execute/', body, format='json')
        self.assertEqual(repeated.status_code, 403)
        self.assertEqual(repeated.data['code'], 'AUTHORIZATION_DENIED')
        self.assertFalse(target.exists())
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        self.assertEqual(self.lifecycle.journal.read()['facts'], [row.retention_retirement])

    def test_http_download_is_fenced_while_external_intent_persistence_is_incomplete(self):
        body, row, record, _ = self.export()
        target = self.root / (record.stored.object_ref.removeprefix('private/') + '.sealed')
        original = target.read_bytes()
        original_delivery = row.delivery_receipt
        approved = self.expired_preview(record)
        with patch.object(self.lifecycle.journal, 'save', side_effect=OSError('synthetic retention journal failure')):
            self.assertIsInstance(self.lifecycle.apply(approved, self.context), ProtectionError)
        row.refresh_from_db()
        self.assertEqual(row.state, 'retiring')
        intent = row.retention_retirement
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(PrivateObject.objects.get(object_ref=record.stored.object_ref).state, 'published')
        self.assertEqual(self.lifecycle.journal.read()['facts'], [])
        self.assertLess(timezone.now(), record.binding.expires_at)
        with patch.object(self.components['crypto'], 'open', side_effect=AssertionError('retiring output reopened')):
            refused = self.client.post('/api/data-security/exports/resources/download/', body, format='json')
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.data['code'], 'AUTHORIZATION_DENIED')
        self.assertIsInstance(self.lifecycle.apply(approved, self.context), tuple)
        row.refresh_from_db()
        self.assertEqual(row.state, 'retired')
        self.assertEqual(row.retention_retirement, intent)
        self.assertEqual(row.delivery_receipt, original_delivery)
        self.assertFalse(target.exists())
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
