"""Resource HTTP lifecycle on isolated PostgreSQL; original ACLs remain authoritative."""
from datetime import timedelta
import json
import os
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import SecurityAuditRecord
from data_security.adapters.django import private_files as http_files
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateFileShare, PrivateObject
from data_security.contracts import ProtectionError, ReasonCode
from tools.data_security import isolation
from users.models import CTFUser

from .models import Resource
from .test_phase6_b2_fixtures import PrivateFileHTTPFixture


class PrivateResourceHTTPTests(PrivateFileHTTPFixture, TransactionTestCase):
    def test_upload_original_cover_download_and_cleanup_leave_no_plaintext_file(self):
        response = self.upload(data=self.data(cover=True))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['operation_id'], str(self.operation_id))
        resource = Resource.objects.get()
        operation = PrivateFileOperation.objects.get()
        self.assertEqual((resource.file.name, resource.cover_image.name, resource.status), ('', '', 'pending'))
        self.assertEqual(resource.private_files['schema_version'], 'resource.private-upload.v2')
        self.assertNotEqual(str(operation.object_uuid), str(self.operation_id))
        self.assertEqual((operation.state, operation.result_ref), ('committed', str(resource.pk)))
        for route, expected in (('download', self.content), ('cover/download', self.cover_bytes)):
            downloaded = self.client.get(f'/api/resources/{resource.pk}/{route}/')
            self.assertEqual(downloaded.status_code, 200)
            self.assertFalse(downloaded.streaming)
            self.assertEqual(downloaded.content, expected)
            self.assertEqual(downloaded['Cache-Control'], 'no-store')
            self.assertEqual(downloaded['X-Content-Type-Options'], 'nosniff')
        observed = self.operation()
        self.assertEqual(set(observed.data), {'operation_id', 'state', 'result_id', 'network_delivery_confirmed'})
        self.assertFalse(observed.data['network_delivery_confirmed'])
        self.assertEqual(list(self.media.iterdir()), [])
        for path in self.root.glob('*.sealed'):
            self.assertNotIn(self.content, path.read_bytes())
            self.assertNotIn(self.cover_bytes, path.read_bytes())
        self.assertEqual(self.operation(cleanup=True).data['state'], 'cleaned')
        self.assertEqual(self.operation(cleanup=True).data['state'], 'cleaned')
        self.assertEqual(list(self.root.glob('*.sealed')), [])
        self.assertEqual(PrivateObject.objects.filter(state='retired').count(), 2)
        self.assertEqual(PrivateFileOperation.objects.get().result_ref, str(resource.pk))
        self.assertEqual(self.client.get(f'/api/resources/{resource.pk}/download/').status_code, 403)
        self.assertFalse(SecurityAuditRecord.objects.filter(event__kind='delivery').exists())

    def test_approved_resource_and_link_possession_do_not_authorize_other_reader(self):
        self.assertEqual(self.upload().status_code, 201)
        resource = Resource.objects.get()
        Resource.objects.filter(pk=resource.pk).update(status='approved')
        shared = self.share(resource)
        self.assertEqual(shared.status_code, 201, shared.data)
        self.client.force_authenticate(self.other)
        for path in (f'/api/resources/{resource.pk}/download/', shared.data['download_url']):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(self.content, response.content)
        self.client.force_authenticate(self.reviewer)
        self.assertEqual(self.client.get(shared.data['download_url']).content, self.content)
        self.assertEqual(self.client.delete(shared.data['download_url']).status_code, 403)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(f'/api/resources/{resource.pk}/download/').content, self.content)
        self.assertFalse(PrivateObject.objects.filter(state='published').exists())

    def test_share_idempotency_revocation_and_expiry(self):
        self.assertEqual(self.upload().status_code, 201)
        resource, operation_id = Resource.objects.get(), uuid4()
        first = self.share(resource, operation_id=operation_id)
        second = self.share(resource, operation_id=operation_id)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data, second.data)
        self.assertEqual(PrivateFileShare.objects.count(), 1)
        url = first.data['download_url']
        self.assertEqual(self.client.get(url).content, self.content)
        with patch.object(self.shares, 'clock', return_value=timezone.now() + timedelta(minutes=6)):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.share(resource, operation_id=operation_id).status_code, 403)

    def test_share_create_cannot_reuse_operation_for_another_target(self):
        self.assertEqual(self.upload(data=self.data(cover=True)).status_code, 201)
        resource, operation_id = Resource.objects.get(), uuid4()
        self.assertEqual(self.share(resource, operation_id=operation_id).status_code, 201)
        result = self.share(resource, operation_id=operation_id, cover=True)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data['code'], 'IDEMPOTENCY_CONFLICT')
        self.assertEqual(PrivateFileShare.objects.count(), 1)

    def test_expiry_and_revocation_after_download_wait_block_all_bytes(self):
        self.assertEqual(self.upload().status_code, 201)
        resource = Resource.objects.get()
        for kind in ('expiry', 'revocation'):
            with self.subTest(kind=kind):
                shared = self.share(resource)
                original = self.uploads.open_download
                future = timezone.now() + timedelta(minutes=6)

                def change_after_read(**kwargs):
                    payload = original(**kwargs)
                    self.assertNotIsInstance(payload, ProtectionError)
                    if kind == 'revocation':
                        PrivateFileShare.objects.filter(share_id=shared.data['share_id']).update(revoked_at=timezone.now())
                    else:
                        self.shares.clock = lambda: future
                    return payload

                with patch.object(self.shares, 'clock', wraps=self.shares.clock), \
                     patch.object(self.uploads, 'open_download', side_effect=change_after_read):
                    response = self.client.get(shared.data['download_url'])
                self.assertEqual(response.status_code, 403)
                self.assertNotIn(self.content, response.content)

    def test_current_user_revocation_during_audit_wait_blocks_download(self):
        self.assertEqual(self.upload().status_code, 201)
        resource = Resource.objects.get()
        record = self.uploads.audit.record

        def revoke_after_audit(event, durability):
            receipt = record(event, durability)
            if event.algorithm_versions == ('private-download.authorized.v1',):
                CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
            return receipt

        with patch.object(self.uploads.audit, 'record', side_effect=revoke_after_audit):
            response = self.client.get(f'/api/resources/{resource.pk}/download/')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(self.content, response.content)
        self.assertFalse(SecurityAuditRecord.objects.filter(event__algorithm_versions=['private-download.authorized.v1']).exists())

    def test_audit_refusal_blocks_download_share_and_cleanup(self):
        self.assertEqual(self.upload().status_code, 201)
        resource = Resource.objects.get()
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
            retryable=False, trace_id='b2/synthetic-audit-refusal')
        with patch.object(self.uploads.audit, 'record', return_value=failure):
            for response in (self.client.get(f'/api/resources/{resource.pk}/download/'),
                             self.share(resource), self.operation(cleanup=True)):
                self.assertEqual(response.status_code, 409)
                self.assertNotIn(self.content, response.content)
        self.assertEqual(PrivateFileOperation.objects.get().state, 'committed')
        self.assertFalse(PrivateFileShare.objects.exists())
        self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, before)

    def test_ciphertext_and_share_document_tampering_never_return_original(self):
        self.assertEqual(self.upload().status_code, 201)
        resource = Resource.objects.get()
        shared = self.share(resource)
        share = PrivateFileShare.objects.get()
        document = {**share.document, 'expires_at': (timezone.now() + timedelta(days=1)).isoformat()}
        PrivateFileShare.objects.filter(pk=share.pk).update(document=document)
        response = self.client.get(shared.data['download_url'])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'AUDIT_UNAVAILABLE')
        path = next(self.root.glob('*.sealed'))
        encoded = path.read_bytes()
        path.write_bytes(encoded[:-1])
        response = self.client.get(f'/api/resources/{resource.pk}/download/')
        self.assertEqual(response.status_code, 409)
        self.assertNotIn(self.content, response.content)
        self.assertEqual(PrivateObject.objects.get().state, 'verified')

    def test_retiring_source_revokes_existing_share_without_deleting_share_evidence(self):
        self.assertEqual(self.upload().status_code, 201)
        shared = self.share(Resource.objects.get())
        self.assertEqual(self.operation(cleanup=True).data['state'], 'cleaned')
        self.assertEqual(self.client.get(shared.data['download_url']).status_code, 403)
        self.assertEqual(PrivateFileShare.objects.count(), 1)
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(Resource.objects.count(), 1)

    def test_formal_missing_capability_does_not_reach_legacy_filefield(self):
        self.assertEqual(self.upload().status_code, 201)
        resource = Resource.objects.get()
        with patch.object(http_files, '_owners', {}), \
             patch('django.db.models.fields.files.FieldFile.open', side_effect=AssertionError('legacy read')):
            self.assertEqual(self.upload().status_code, 503)
            self.assertEqual(self.client.get(f'/api/resources/{resource.pk}/download/').status_code, 503)
        self.assertEqual(Resource.objects.count(), 1)
        self.assertEqual(list(self.media.iterdir()), [])

    def test_operation_is_scoped_to_actor_even_when_other_actor_is_staff(self):
        self.assertEqual(self.upload().status_code, 201)
        self.client.force_authenticate(self.reviewer)
        self.assertEqual(self.operation().data['code'], 'DELIVERY_UNKNOWN')
        self.assertEqual(self.operation(cleanup=True).data['code'], 'DELIVERY_UNKNOWN')
        self.assertEqual(PrivateFileOperation.objects.get().state, 'committed')
        self.assertEqual(len(list(self.root.glob('*.sealed'))), 1)

    def test_ordinary_startup_http_lifecycle_without_test_capability_injection(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
        env = isolation.clean_env()
        env.update(DATA_SECURITY_CONFIG=str(self.config_path), DATA_SECURITY_ISOLATED_TEST='1',
            DJANGO_SETTINGS_MODULE='tools.data_security.test_settings',
            DS_TEST_PG_PORT=os.environ['DS_TEST_PG_PORT'], DS_TEST_PG_SOCKET=os.environ['DS_TEST_PG_SOCKET'],
            ALLOWED_HOSTS='testserver,localhost', DEBUG='false')
        code = '''
import json,sys
from pathlib import Path
sys.path[:0] = [str(Path.cwd()), str(Path.cwd() / 'backend')]
from django.conf import settings
settings.DATABASES['default']['NAME'] = 'test_ds_phase1_main'
import django
django.setup()
from resources.test_phase6_b2_http import ordinary_http_lifecycle
print(json.dumps(ordinary_http_lifecycle(int(sys.argv[1]))))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(self.teacher.pk)],
            cwd=isolation.ROOT, env=env, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace')[-3000:])
        value = json.loads(result.stdout)
        self.assertEqual(value, {'upload': 201, 'download': 200, 'share': 201, 'share_read': 200,
            'cleanup': 'cleaned', 'retired_read': 403, 'guessed_media': 404,
            'network_delivery_confirmed': False})


def ordinary_http_lifecycle(user_id):
    """Called only after the child ran the actual AppConfig.ready startup."""
    client, operation_id = APIClient(), uuid4()
    client.force_authenticate(CTFUser.objects.get(pk=user_id))
    content = b'b2 ordinary startup private original'
    with patch('django.core.files.storage.FileSystemStorage._save', side_effect=AssertionError('plaintext save')):
        upload = client.post('/api/resources/upload/', {'title': '合成资料', 'description': '隔离测试资料',
            'resource_type': 'document', 'category': 'security',
            'file': SimpleUploadedFile('synthetic.txt', content, content_type='text/plain')},
            format='multipart', secure=True, HTTP_X_FILE_OPERATION_ID=str(operation_id))
    assert upload.status_code == 201, upload.data
    operation = PrivateFileOperation.objects.get(operation_ref__endswith=str(operation_id))
    url = f'/api/resources/{operation.result_ref}/download/'
    downloaded = client.get(url, secure=True)
    assert downloaded.content == content
    shared = client.post(f'/api/resources/{operation.result_ref}/shares/', secure=True, HTTP_X_FILE_OPERATION_ID=str(uuid4()))
    assert shared.status_code == 201, shared.data
    read = client.get(shared.data['download_url'], secure=True)
    assert read.content == content
    cleaned = client.delete(f'/api/resources/file-operations/{operation_id}/', secure=True)
    return {'upload': upload.status_code, 'download': downloaded.status_code, 'share': shared.status_code,
        'share_read': read.status_code, 'cleanup': cleaned.data['state'],
        'retired_read': client.get(url, secure=True).status_code,
        'guessed_media': client.get('/media/resources/files/synthetic.txt', secure=True).status_code,
        'network_delivery_confirmed': cleaned.data['network_delivery_confirmed']}
