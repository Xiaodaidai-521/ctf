"""Real API regressions for review access, preview contracts and list costs."""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from data_security.tests import test_runtime_files as runtime_file_tests
from data_security.runtime.storage import EncryptedFileSystemStorage
from users.models import CTFUser


class ResourceLogicFixTests(TestCase):
    setUp = runtime_file_tests.RuntimePrivateFileTests.setUp
    resource = runtime_file_tests.RuntimePrivateFileTests.resource
    response_bytes = runtime_file_tests.RuntimePrivateFileTests.response_bytes

    def test_pending_original_is_available_to_admin_and_uploader_only(self):
        admin = CTFUser.objects.create_user(username='review-admin', role='admin')
        resource = self.resource(status='pending')
        url = f'/api/resources/{resource.pk}/download/'
        for user in (admin, self.owner):
            self.client.force_authenticate(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.response_bytes(response), b'email: student@example.invalid\n')
        for user in (self.student, self.other):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_image_detail_exposes_safe_name_and_inline_type(self):
        png = BytesIO()
        Image.new('RGB', (2, 2), 'red').save(png, format='PNG')
        resource = self.resource(file=SimpleUploadedFile('private-person.png', png.getvalue(), content_type='image/png'))
        self.client.force_authenticate(self.student)
        detail = self.client.get(f'/api/resources/{resource.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['file_type'], '.png')
        self.assertEqual(detail.data['file_name'], f'resource-{resource.pk}.png')
        self.assertNotIn('private-person', str(detail.data))
        download = self.client.get(detail.data['file_url'])
        self.assertEqual(download['Content-Type'], 'image/png')
        self.assertIn('inline', download['Content-Disposition'])
        self.assertEqual(self.response_bytes(download), png.getvalue())

    def test_reserved_video_preview_url_preserves_authorization_context(self):
        resource = self.resource(resource_type='video', is_tutoring_reserved=True,
            file=SimpleUploadedFile('video.mp4', b'synthetic-video', content_type='video/mp4'))
        self.client.force_authenticate(self.student)
        detail = self.client.get(f'/api/resources/{resource.pk}/', {'highlight_resource': resource.pk})
        self.assertEqual(detail.status_code, 200)
        self.assertIn(f'highlight_resource={resource.pk}', detail.data['file_url'])
        response = self.client.get(detail.data['file_url'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'video/mp4')
        self.assertEqual(self.response_bytes(response), b'synthetic-video')
        self.assertEqual(self.client.get(f'/api/resources/{resource.pk}/download/').status_code, 404)

    def test_anonymous_list_does_not_open_or_decrypt_resource_files(self):
        for index in range(3):
            self.resource(file=SimpleUploadedFile(f'large-{index}.txt', b'x' * 1024 * 1024))
        with patch.object(EncryptedFileSystemStorage, '_open', side_effect=AssertionError('List read full file')):
            response = self.client.get('/api/resources/')
        self.assertEqual(response.status_code, 200)
        for item in response.data.get('results', response.data):
            self.assertEqual(item['protection']['file']['storage'], 'encrypted')

    def test_list_projection_does_not_disable_download_authentication(self):
        resource = self.resource()
        path = Path(resource.file.path)
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        self.assertEqual(self.client.get('/api/resources/').status_code, 200)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f'/api/resources/{resource.pk}/download/').status_code, 404)

    def test_script_capable_legacy_file_is_not_served_inline(self):
        resource = self.resource(file=SimpleUploadedFile('unsafe.svg', b'<svg onload="alert(1)"/>'))
        self.client.force_authenticate(self.student)
        response = self.client.get(f'/api/resources/{resource.pk}/download/')
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment', response['Content-Disposition'])
        self.response_bytes(response)

    def test_anonymous_detail_does_not_offer_authenticated_file_or_cover_urls(self):
        resource = self.resource(cover_image=SimpleUploadedFile('cover.png', b'synthetic-cover'))
        response = self.client.get(f'/api/resources/{resource.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['file_url'])
        self.assertIsNone(response.data['cover_url'])
