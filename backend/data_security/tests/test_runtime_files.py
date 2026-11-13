"""Normal application file writes use real authenticated encrypted storage."""
from io import BytesIO
from pathlib import Path
import secrets
import tempfile
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import RequestDataTooBig
from django.http import Http404
from django.http.multipartparser import MultiPartParser
from django.test import TestCase, RequestFactory, SimpleTestCase, override_settings
from django.test.client import encode_multipart
from PIL import Image
from rest_framework.test import APIClient

from data_security.adapters.django.private_files import bind_private_files
from data_security.runtime.crypto import MAGIC, RuntimeCipher
from data_security.runtime.media import serve_public_media
from data_security.runtime.storage import EncryptedFileSystemStorage, migrate_private_files
from data_security.runtime.uploads import PrivateMemoryUploadHandler
from feedback_center.models import FeedbackAttachment, FeedbackTicket
from resources.models import Resource
from resources.serializers import ResourceSerializer
from users.models import CTFUser


@override_settings(ROOT_URLCONF='ctf_backend.urls')
class RuntimePrivateFileTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ctf-private-files-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.media = self.root / 'media'
        self.media.mkdir()
        options = override_settings(DATA_PROTECTION_ENABLED=True,
            DATA_PROTECTION_ROOT=self.root / 'private', MEDIA_ROOT=self.media)
        options.enable()
        self.addCleanup(options.disable)
        cipher = patch('data_security.runtime.storage.get_cipher', return_value=RuntimeCipher(secrets.token_bytes(64)))
        cipher.start()
        self.addCleanup(cipher.stop)
        bind_private_files(None)
        self.addCleanup(bind_private_files, None)
        self.owner = CTFUser.objects.create_user(username='files-owner', role='teacher')
        self.student = CTFUser.objects.create_user(username='files-student')
        self.other = CTFUser.objects.create_user(username='files-other')
        self.client = APIClient()

    def resource(self, **changes):
        values = dict(title='Private course document', description='Course material',
            category='security', resource_type='document', uploader=self.owner,
            file=SimpleUploadedFile('personal-name.txt', b'email: student@example.invalid\n'), status='approved')
        values.update(changes)
        return Resource.objects.create(**values)

    def response_bytes(self, response):
        value = b''.join(response.streaming_content)
        response.close()
        return value

    def assert_encrypted(self, file, expected):
        raw = Path(file.path).read_bytes()
        self.assertTrue(raw.startswith(MAGIC))
        self.assertNotIn(expected, raw)
        self.assertFalse((self.media / file.name).exists())
        with file.open('rb') as stream:
            self.assertEqual(stream.read(), expected)
        self.assertEqual(file.storage.protection_status(file.name)['storage'], 'encrypted')

    def test_resource_and_cover_bytes_are_encrypted_and_authorized_downloads_work(self):
        png = BytesIO()
        Image.new('RGB', (2, 2), 'red').save(png, format='PNG')
        resource = self.resource(cover_image=SimpleUploadedFile('cover.png', png.getvalue(), content_type='image/png'))
        self.assertNotIn('personal-name', resource.file.name)
        self.assert_encrypted(resource.file, b'email: student@example.invalid\n')
        self.assert_encrypted(resource.cover_image, png.getvalue())
        self.assertIn('/api/resources/', resource.cover_image.url)
        self.assertNotIn('/media/', str(ResourceSerializer(resource).data))
        self.assertIn(self.client.get(f'/api/resources/{resource.pk}/download/').status_code, (401, 403))
        self.client.force_authenticate(self.student)
        response = self.client.get(f'/api/resources/{resource.pk}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.response_bytes(response), b'email: student@example.invalid\n')
        response = self.client.get(f'/api/resources/{resource.pk}/cover/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(self.response_bytes(response), png.getvalue())

    def test_pending_file_and_cover_are_not_available_to_other_students(self):
        resource = self.resource(status='pending', cover_image=ContentFile(b'cover bytes', name='cover.png'))
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f'/api/resources/{resource.pk}/download/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/resources/{resource.pk}/cover/download/').status_code, 404)

    def test_legacy_cover_also_uses_authenticated_downloads(self):
        with override_settings(DATA_PROTECTION_ENABLED=False):
            resource = self.resource(cover_image=ContentFile(b'legacy cover', name='cover.png'))
            data = ResourceSerializer(resource).data
            self.assertIsNone(data['cover_image'])
            self.assertEqual(data['cover_url'], f'/api/resources/{resource.pk}/cover/download/')
            self.assertIn(self.client.get(data['cover_url']).status_code, (401, 403))
            self.client.force_authenticate(self.student)
            response = self.client.get(data['cover_url'])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.response_bytes(response), b'legacy cover')

    def test_feedback_attachment_is_encrypted_and_other_accounts_are_denied(self):
        ticket = FeedbackTicket.objects.create(submitter=self.student, student=self.student,
            submitter_role='student', client_request_id='encrypted-file', request_fingerprint='1' * 64,
            category='content', issue_type='incorrect', dispute='Example feedback')
        attachment = FeedbackAttachment.objects.create(ticket=ticket, uploaded_by=self.student,
            file=ContentFile(b'private feedback evidence', name='evidence.txt'), original_name='evidence.txt', size=25)
        self.assert_encrypted(attachment.file, b'private feedback evidence')
        url = f'/api/feedback/{ticket.feedback_id}/attachments/{attachment.attachment_id}/download/'
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.student)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.response_bytes(response), b'private feedback evidence')

    @override_settings(FILE_UPLOAD_HANDLERS=['data_security.runtime.uploads.PrivateMemoryUploadHandler'],
                       FILE_UPLOAD_MAX_MEMORY_SIZE=1)
    def test_feedback_http_upload_is_encrypted_and_staff_visibility_is_preserved(self):
        ticket = FeedbackTicket.objects.create(submitter=self.student, student=self.student,
            submitter_role='student', client_request_id='http-encrypted-file', request_fingerprint='2' * 64,
            category='content', issue_type='incorrect', dispute='Example feedback')
        url = f'/api/feedback/{ticket.feedback_id}/attachments/'
        self.client.force_authenticate(self.owner)
        with patch('django.core.files.uploadhandler.TemporaryUploadedFile',
                   side_effect=AssertionError('Plaintext upload reached the temporary filesystem')):
            response = self.client.post(url, {'file': SimpleUploadedFile('staff.txt', b'staff evidence',
                content_type='text/plain'), 'visibility': 'staff'}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        attachment = FeedbackAttachment.objects.get()
        self.assert_encrypted(attachment.file, b'staff evidence')
        self.assertEqual(response.data['protection']['file']['storage'], 'encrypted')
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(url + str(attachment.attachment_id) + '/download/').status_code, 403)

    def test_tampering_and_cross_file_ciphertext_swaps_fail_closed(self):
        first, second = self.resource(), self.resource()
        first_path, second_path = Path(first.file.path), Path(second.file.path)
        first_path.write_bytes(second_path.read_bytes())
        self.assertEqual(first.file.storage.protection_status(first.file.name)['storage'], 'unknown')
        with self.assertRaisesRegex(ValueError, 'CIPHERTEXT_INVALID'):
            first.file.open('rb')
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f'/api/resources/{first.pk}/download/').status_code, 404)

    def test_legacy_migration_is_repeatable_and_preserves_names_and_bytes(self):
        with override_settings(DATA_PROTECTION_ENABLED=False):
            resource = self.resource()
        name = resource.file.name
        self.assertTrue((self.media / name).exists())
        self.assertEqual(migrate_private_files()['legacy'], 1)
        self.assertTrue((self.media / name).exists())
        self.assertEqual(migrate_private_files(apply=True)['migrated'], 1)
        self.assertEqual(migrate_private_files(apply=True)['encrypted'], 1)
        resource.refresh_from_db()
        self.assertEqual(resource.file.name, name)
        self.assert_encrypted(resource.file, b'email: student@example.invalid\n')

    def test_legacy_source_is_kept_when_existing_encrypted_copy_disagrees(self):
        with override_settings(DATA_PROTECTION_ENABLED=False):
            resource = self.resource()
        resource.file.storage._write_exact(resource.file.name, b'different bytes')
        self.assertEqual(migrate_private_files(apply=True)['failed'], 1)
        self.assertTrue((self.media / resource.file.name).exists())

    def test_failed_migration_write_keeps_legacy_source_and_can_be_retried(self):
        with override_settings(DATA_PROTECTION_ENABLED=False):
            resource = self.resource()
        storage = resource.file.storage
        storage._prepare_directory(storage._path(resource.file.name).parent)
        with patch('data_security.runtime.storage.os.fsync', side_effect=OSError('simulated full disk')):
            self.assertEqual(migrate_private_files(apply=True)['failed'], 1)
        self.assertFalse(storage._path(resource.file.name).exists())
        self.assertTrue((self.media / resource.file.name).exists())
        self.assertEqual(migrate_private_files(apply=True)['migrated'], 1)
        self.assert_encrypted(resource.file, b'email: student@example.invalid\n')

    def test_public_media_cannot_serve_private_namespaces_or_legacy_files(self):
        for namespace in ('resources', 'resource_covers', 'feedback_evidence'):
            for path in (namespace + '/file.txt', 'public/../' + namespace + '/file.txt',
                         '//' + namespace + '/file.txt', namespace.upper() + '/file.txt',
                         'public\\..\\' + namespace + '\\file.txt'):
                with self.subTest(path=path), self.assertRaises(Http404):
                    serve_public_media(RequestFactory().get('/media/' + path),
                        path, document_root=self.media)

    def test_private_names_keep_only_file_type_suffix(self):
        resource = self.resource(file=ContentFile(b'example', name='notes.alice@example.invalid.txt'))
        self.assertTrue(resource.file.name.endswith('.txt'))
        self.assertNotIn('alice', resource.file.name)
        self.assertNotIn('example', resource.file.name)

    @override_settings(FILE_UPLOAD_HANDLERS=['data_security.runtime.uploads.PrivateMemoryUploadHandler'],
                       FILE_UPLOAD_MAX_MEMORY_SIZE=1)
    def test_http_upload_is_encrypted_without_plaintext_temporary_files_and_rejects_oversize(self):
        self.client.force_authenticate(self.owner)

        def upload():
            return self.client.post('/api/resources/upload/', dict(title='Protected upload',
                description='Course material', resource_type='document', category='security',
                file=SimpleUploadedFile('notes.txt', b'private course text', content_type='text/plain')),
                format='multipart')

        with patch('django.core.files.uploadhandler.TemporaryUploadedFile',
                   side_effect=AssertionError('Plaintext upload reached the temporary filesystem')):
            response = upload()
        self.assertEqual(response.status_code, 201, response.data)
        resource = Resource.objects.get()
        self.assert_encrypted(resource.file, b'private course text')
        with override_settings(DATA_PROTECTION_MAX_UPLOAD_BYTES=1):
            response = upload()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Resource.objects.count(), 1)

    def test_invalid_storage_paths_are_rejected(self):
        storage = EncryptedFileSystemStorage()
        for name in ('../file', '/absolute/file', 'C:/outside/file'):
            with self.assertRaises(Exception):
                storage.open(name)


class PrivateUploadLimitTests(SimpleTestCase):
    @override_settings(DATA_PROTECTION_MAX_UPLOAD_BYTES=10)
    def test_streaming_limit_rejects_entire_request_after_an_earlier_file_completed(self):
        body = encode_multipart('private-boundary', {
            'file': SimpleUploadedFile('first.txt', b'123456'),
            'cover': SimpleUploadedFile('second.txt', b'789012'),
        })
        # A declared length cannot replace checking the actual bytes received.
        parser = MultiPartParser({'CONTENT_TYPE': 'multipart/form-data; boundary=private-boundary',
                                  'CONTENT_LENGTH': '1'}, BytesIO(body), [PrivateMemoryUploadHandler()])
        with self.assertRaises(RequestDataTooBig):
            parser.parse()
