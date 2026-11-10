"""B2 HTTP fixtures use real composition and PostgreSQL; never the small-check runner."""
import json
import os
from unittest.mock import patch
from uuid import uuid4

from django.test import override_settings
from rest_framework.test import APIClient

from ctf_backend.security_bootstrap import assemble
from data_security.adapters.django import private_files as http_files
from users.models import CTFUser

from .test_phase6_private_uploads import PrivateResourceUploadFixture


class PrivateFileHTTPFixture(PrivateResourceUploadFixture):
    def setUp(self):
        super().setUp()
        self.config['private_files'] = {'private_root': str(self.root), 'project_ref': 'resource-upload/synthetic'}
        self.config_path.write_text(json.dumps(self.config))
        self.components = assemble(config_path=self.config_path)
        self.uploads = self.components['private_uploads']['resources']
        self.preparation = self.uploads.prepare.__self__
        self.shares = self.components['file_shares']
        owners = patch.object(http_files, '_owners', self.components['private_uploads'])
        shares = patch.object(http_files, '_shares', self.shares)
        environment = patch.dict(os.environ, DATA_SECURITY_CONFIG=str(self.config_path))
        for setting in (owners, shares, environment):
            setting.start()
            self.addCleanup(setting.stop)
        settings = override_settings(
            ALLOWED_HOSTS=['testserver', 'localhost'],
            MIDDLEWARE=['ctf_backend.security_bootstrap.private_upload_middleware'],
            DATA_SECURITY_FORMAL_MODE=True,
        )
        settings.enable()
        self.addCleanup(settings.disable)
        self.client = APIClient()
        self.client.force_authenticate(self.teacher)
        self.other = CTFUser.objects.create_user(username='b2-other', role='student')
        self.reviewer = CTFUser.objects.create_user(username='b2-reviewer', role='teacher', is_staff=True)
        self.operation_id = uuid4()

    def upload(self, *, operation_id=None, data=None):
        with patch('django.core.files.uploadhandler.TemporaryUploadedFile',
                   side_effect=AssertionError('ordinary upload spool reached')), \
             patch('django.core.files.storage.FileSystemStorage._save',
                   side_effect=AssertionError('ordinary FileField save reached')):
            return self.client.post('/api/resources/upload/', data or self.data(), format='multipart',
                HTTP_X_FILE_OPERATION_ID=str(operation_id or self.operation_id))

    def operation(self, *, cleanup=False, operation_id=None):
        path = f'/api/resources/file-operations/{operation_id or self.operation_id}/'
        return (self.client.delete if cleanup else self.client.post)(path)

    def share(self, resource, *, operation_id=None, cover=False):
        return self.client.post(f'/api/resources/{resource.pk}/' + ('cover/' if cover else '') + 'shares/',
            HTTP_X_FILE_OPERATION_ID=str(operation_id or uuid4()))
