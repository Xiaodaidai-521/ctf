"""HTTP exports reuse B1's complete source, risk, target and delivery authority."""
import os
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from audit.models import SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.django import export_delivery, private_files
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject
from export_quota.models import QuotaBucket

from .models import Resource
from .test_phase6_formal_delivery import EXPECTED
from .test_phase6_formal_fixtures import CONTENT, FormalResourceFixture


class ResourceExportHTTPTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def setUp(self):
        super().setUp()
        self.config['private_files'] = {'private_root': str(self.root), 'project_ref': 'formal-column/synthetic'}
        self.write_config()
        components = assemble(config_path=self.config_path)
        self.entry = components['export_delivery']
        self.sources, self.risks = self.entry.sources, self.entry.risks
        for setting in (patch.object(export_delivery, '_entry', self.entry),
                        patch.object(private_files, '_owners', components['private_uploads']),
                        patch.object(private_files, '_shares', components['file_shares']),
                        patch.dict(os.environ, DATA_SECURITY_CONFIG=str(self.config_path))):
            setting.start()
            self.addCleanup(setting.stop)
        configured = override_settings(ALLOWED_HOSTS=['testserver'],
            MIDDLEWARE=['ctf_backend.security_bootstrap.private_upload_middleware'])
        configured.enable()
        self.addCleanup(configured.disable)
        self.client = APIClient()
        self.client.force_authenticate(self.teacher)

    def original(self):
        response = self.client.post('/api/resources/upload/', {
            'title': '合成资料', 'description': '隔离测试资料', 'resource_type': 'document', 'category': 'security',
            'file': SimpleUploadedFile('synthetic.txt', CONTENT, content_type='text/plain')},
            format='multipart', HTTP_X_FILE_OPERATION_ID=str(uuid4()))
        self.assertEqual(response.status_code, 201, response.data)
        resource = Resource.objects.get(pk=response.data['resource']['id'])
        self.assertEqual(resource.private_files['schema_version'], 'resource.private-upload.v2')
        return resource

    def test_managed_http_original_uses_actual_b1_export_and_authenticated_output(self):
        source_ref, permission_ref, _, _ = self.ready()
        body = {'source_ref': source_ref, 'permission_ref': permission_ref}
        executed = self.client.post('/api/data-security/exports/resources/execute/', body, format='json')
        self.assertEqual(executed.status_code, 200, executed.data)
        self.assertEqual(executed.data['state'], 'logically_delivered')
        self.assertFalse(executed.data['network_delivery_confirmed'])
        self.assertEqual(executed.data['delivered_records'], 2)
        with patch.object(self.entry.sources, 'read_original', side_effect=AssertionError('output reopened original')):
            downloaded = self.client.post('/api/data-security/exports/resources/download/', body, format='json')
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, EXPECTED)
        self.assertFalse(downloaded.streaming)
        self.assertEqual(downloaded['Cache-Control'], 'no-store')
        self.assertNotIn(b'first@example.invalid', downloaded.content)
        self.assertEqual(PrivateFileOperation.objects.get().state, 'committed')
        self.assertEqual(sorted(PrivateObject.objects.values_list('state', flat=True)), ['published', 'verified'])
        self.assertEqual(SecurityAuditRecord.objects.filter(event__kind='delivery').count(), 1)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)

    def test_http_cannot_supply_approval_and_current_source_revocation_blocks_output(self):
        source_ref, permission_ref, _, _ = self.ready()
        body = {'source_ref': source_ref, 'permission_ref': permission_ref}
        rejected = self.client.post('/api/data-security/exports/resources/execute/',
            {**body, 'approved': True, 'binding': {}}, format='json')
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(PrivateObject.objects.filter(state='published').exists())
        self.assertEqual(self.client.post('/api/data-security/exports/resources/execute/', body, format='json').status_code, 200)
        self.ok(self.sources.revoke_permission(user=self.reviewer, permission_ref=permission_ref))
        refused = self.client.post('/api/data-security/exports/resources/download/', body, format='json')
        self.assertEqual(refused.status_code, 503)
        self.assertEqual(refused.data['code'], 'SOURCE_NOT_APPROVED')
        self.assertNotIn(EXPECTED, refused.content)
        self.assertEqual(QuotaBucket.objects.get().settled, 2)
