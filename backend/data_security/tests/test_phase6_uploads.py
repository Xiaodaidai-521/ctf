"""Real Django multipart parsing; no database, storage or authorization substitute."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from django.conf import settings as django_settings
from django.core.exceptions import RequestDataTooBig, TooManyFilesSent
from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.http import HttpResponse
from django.http.multipartparser import MultiPartParserError
from django.test import RequestFactory, override_settings

from data_security.adapters.django.uploads import BoundedUploadHandler, PrivateUploadBoundary
from data_security.contracts import BASELINE_LIMITS, ContractViolation, ReasonCode
from resources.validators import validate_cover_image, validate_resource_file


class PrivateUploadBoundaryTests(TestCase):
    def setUp(self):
        # Resolve ordinary settings before override_settings wraps LazySettings.
        self.assertEqual(django_settings.DEFAULT_CHARSET, 'utf-8')
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        settings = override_settings(FILE_UPLOAD_MAX_MEMORY_SIZE=1,
            FILE_UPLOAD_TEMP_DIR=temporary.name, DATA_UPLOAD_MAX_NUMBER_FILES=100,
            RESOURCE_MAX_UPLOAD_SIZE=BASELINE_LIMITS.max_bytes)
        settings.enable()
        self.addCleanup(settings.disable)
        disk = patch('django.core.files.uploadhandler.TemporaryUploadedFile',
            side_effect=AssertionError('ordinary disk upload reached'))
        self.disk = disk.start()
        self.addCleanup(disk.stop)
        self.factory = RequestFactory()
        self.limits = replace(BASELINE_LIMITS, max_bytes=1024)
        self.uploads, self.saved = [], []

    def request(self, contents):
        return self.factory.post('/private-upload/', {'files': [
            SimpleUploadedFile('synthetic.txt', content, content_type='text/plain')
            for content in contents]})

    def consume(self, request):
        for upload in request.FILES.getlist('files'):
            self.assertIs(type(upload), InMemoryUploadedFile)
            self.assertFalse(upload.closed)
            self.uploads.append(upload)
            self.saved.append(upload.read())
        return HttpResponse(status=201)

    def parse(self, request, *, view=None, limits=None):
        boundary = PrivateUploadBoundary(view or self.consume, limits=limits or self.limits)
        try:
            return boundary(request)
        finally:
            self.disk.assert_not_called()
            self.assertEqual(list(self.directory.iterdir()), [])
            for handler in request.upload_handlers:
                if isinstance(handler, BoundedUploadHandler):
                    self.assertTrue(all(buffer.closed for buffer in handler.buffers))

    def test_exact_object_limit_and_two_resident_parts_not_a_total_request_limit(self):
        contents = [b'a' * 1024, b'b' * 1024]
        response = self.parse(self.request(contents))
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.saved == contents)
        self.assertEqual([upload.size for upload in self.uploads], [1024, 1024])
        self.assertTrue(all(upload.closed for upload in self.uploads))

    def test_twenty_mib_file_does_not_use_default_memory_threshold_or_disk(self):
        content = b'x' * (20 * 1024 * 1024)
        self.assertEqual(BASELINE_LIMITS.max_bytes, len(content))
        response = self.parse(self.request([content]), limits=BASELINE_LIMITS)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.saved == [content])
        self.assertEqual(self.uploads[0].size, len(content))

    def test_one_byte_over_twenty_mib_rejects_before_view_effects(self):
        request = self.request([b'x' * (20 * 1024 * 1024 + 1)])
        with self.assertRaises(RequestDataTooBig):
            self.parse(request, limits=BASELINE_LIMITS)
        self.assertEqual(self.saved, [])
        self.assertLessEqual(request.upload_handlers[0].size, BASELINE_LIMITS.max_bytes)

    def test_stricter_injected_limit_rejects_second_part_without_partial_success(self):
        request = self.request([b'first', b'x' * 1025])
        with self.assertRaises(RequestDataTooBig):
            self.parse(request)
        self.assertEqual(self.saved, [])
        self.assertEqual(len(request.upload_handlers[0].buffers), 2)

    def test_retained_parts_use_existing_inflight_limit(self):
        for count, limits in ((3, self.limits), (2, replace(self.limits, max_inflight_objects=1))):
            with self.subTest(count=count):
                request = self.request([b'x'] * count)
                with self.assertRaises(TooManyFilesSent):
                    self.parse(request, limits=limits)
                self.assertEqual(self.saved, [])
                self.assertEqual(len(request.upload_handlers[0].buffers), limits.max_inflight_objects)

    def test_part_size_headers_cannot_override_observed_size(self):
        for declared in (b'1', b'99999999', b'-1', b'invalid', None):
            for size in (1024, 1025):
                with self.subTest(declared=declared, size=size):
                    header = b'' if declared is None else b'Content-Length: ' + declared + b'\r\n'
                    body = (b'--boundary\r\nContent-Disposition: form-data; name="files"; '
                        b'filename="synthetic.txt"\r\nContent-Type: text/plain\r\n' + header +
                        b'\r\n' + b'x' * size + b'\r\n--boundary--\r\n')
                    request = self.factory.generic('POST', '/private-upload/', body,
                        content_type='multipart/form-data; boundary=boundary')
                    self.saved.clear()
                    if size == 1024:
                        self.assertEqual(self.parse(request).status_code, 201)
                        self.assertEqual(len(self.saved[0]), size)
                    else:
                        with self.assertRaises(RequestDataTooBig):
                            self.parse(request)
                        self.assertEqual(self.saved, [])

    def test_truncated_multipart_is_not_an_empty_success(self):
        body = (b'--boundary\r\nContent-Disposition: form-data; name="files"; '
            b'filename="synthetic.txt"\r\nContent-Type: text/plain\r\n\r\n' + b'x' * 512)
        request = self.factory.generic('POST', '/private-upload/', body,
            content_type='multipart/form-data; boundary=boundary')
        with self.assertRaises(MultiPartParserError):
            self.parse(request)
        self.assertEqual(self.saved, [])

    def test_transport_failure_closes_active_buffer(self):
        request = self.request([b'x' * (128 * 1024)])
        original = request._stream

        class InterruptedInput:
            reads = 0

            def read(self, size=-1):
                self.reads += 1
                if self.reads == 2:
                    raise OSError('synthetic transport interruption')
                return original.read(size)

        request._stream = InterruptedInput()
        with self.assertRaisesRegex(OSError, 'synthetic transport interruption'):
            self.parse(request, limits=BASELINE_LIMITS)
        self.assertEqual(self.saved, [])
        self.assertEqual(len(request.upload_handlers[0].buffers), 1)

    def test_view_error_still_closes_completed_uploads(self):
        def view(request):
            self.consume(request)
            raise ValueError('synthetic view failure')

        with self.assertRaisesRegex(ValueError, 'synthetic view failure'):
            self.parse(self.request([b'safe synthetic text']), view=view)
        self.assertTrue(self.uploads[0].closed)

    def test_existing_resource_format_and_cover_validation_are_still_consumable(self):
        from rest_framework.exceptions import ValidationError

        def view(request):
            upload = request.FILES['files']
            self.assertIs(validate_resource_file(upload), upload)
            self.assertEqual(upload.tell(), 0)
            self.uploads.append(upload)
            return HttpResponse(status=201)

        self.assertEqual(self.parse(self.request([b'safe synthetic text']), view=view).status_code, 201)
        with self.assertRaises(ValidationError):
            self.parse(self.request([b'<script>synthetic</script>']), view=view)

        from PIL import Image
        image = BytesIO()
        Image.new('RGB', (2, 2)).save(image, format='PNG')
        request = self.factory.post('/private-upload/', {'files': SimpleUploadedFile(
            'synthetic.png', image.getvalue(), content_type='image/png')})

        def cover(request):
            upload = request.FILES['files']
            self.assertIs(validate_cover_image(upload), upload)
            self.assertEqual(upload.tell(), 0)
            return HttpResponse(status=201)

        self.assertEqual(self.parse(request, view=cover).status_code, 201)

    def test_no_file_request_and_empty_file_remain_distinct(self):
        self.assertEqual(self.parse(self.request([])).status_code, 201)
        self.assertEqual(self.saved, [])
        self.assertEqual(self.parse(self.request([b''])).status_code, 201)
        self.assertEqual(self.saved, [b''])
        self.assertEqual(self.uploads[0].size, 0)

    def test_already_parsed_request_cannot_be_rebound(self):
        request = self.request([])
        self.assertEqual(len(request.FILES), 0)
        with self.assertRaises(AttributeError):
            self.parse(request)
        self.assertEqual(self.saved, [])

    def test_limits_are_explicit_not_loaded_from_settings_or_environment(self):
        with self.assertRaises(TypeError):
            PrivateUploadBoundary(self.consume)
        with self.assertRaises(ContractViolation) as raised:
            PrivateUploadBoundary(self.consume, limits=True)(self.request([]))
        self.assertIs(raised.exception.code, ReasonCode.INVALID_TYPE)
