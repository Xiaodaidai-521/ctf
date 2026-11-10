"""Real Django request/ASGI ingress with synthetic frames; no database or storage."""
import asyncio
from collections import deque
from dataclasses import replace
from io import BytesIO
import re
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

from django.conf import settings
from django.core.exceptions import RequestDataTooBig, TooManyFilesSent
from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.core.handlers.asgi import ASGIHandler
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.urls import re_path

from data_security.adapters.django.private_ingress import OpenPrivateUploadIngress
from data_security.adapters.django.uploads import BoundedUploadHandler
from data_security.contracts import BASELINE_LIMITS


_PATHS = ('/api/resources/upload', '/api/resources/upload/')
_FEEDBACK = '/api/feedback/00000000-0000-0000-0000-000000000001/attachments/'
_PATTERNS = (re.compile(
    r'/api/feedback/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/attachments/?'),)
_LIMITS = replace(BASELINE_LIMITS, max_bytes=1024, max_text_chars=1024)


def _upload_middleware(get_response):
    return OpenPrivateUploadIngress(get_response, paths=_PATHS, patterns=_PATTERNS, limits=_LIMITS)


class _ObservedBuffer(BytesIO):
    def __init__(self, buffers):
        super().__init__()
        self.peak = 0
        buffers.append(self)

    def write(self, content):
        result = super().write(content)
        self.peak = max(self.peak, self.tell())
        return result


class OpenPrivateIngressTests(TestCase):
    def setUp(self):
        self.assertEqual(settings.DEFAULT_CHARSET, 'utf-8')
        self.requests, self.uploads, self.saved = [], [], []
        self.body_buffers, self.upload_buffers = [], []
        self.factory = RequestFactory()
        self.budget = _LIMITS.max_bytes * _LIMITS.max_inflight_objects + _LIMITS.max_text_chars
        self.application = AsyncMock(side_effect=AssertionError('original ASGI application reached'))
        self.ingress = OpenPrivateUploadIngress(self.application,
            paths=_PATHS, patterns=_PATTERNS, limits=_LIMITS)
        self.default_read_body = ASGIHandler.read_body

        class URLs:
            urlpatterns = [
                re_path(r'^api/resources/upload/?$', self.consume),
                re_path(r'^api/feedback/[0-9a-f-]+/attachments/?$', self.consume),
            ]

        configured = override_settings(ROOT_URLCONF=URLs,
            MIDDLEWARE=[__name__ + '._upload_middleware'], FORCE_SCRIPT_NAME=None,
            FILE_UPLOAD_MAX_MEMORY_SIZE=1, DATA_UPLOAD_MAX_NUMBER_FILES=100,
            ALLOWED_HOSTS=['testserver'], DEBUG=False)
        configured.enable()
        self.addCleanup(configured.disable)
        for target in ('django.core.handlers.asgi.tempfile.SpooledTemporaryFile',
                       'django.core.files.uploadhandler.TemporaryUploadedFile',
                       'django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection'):
            guarded = patch(target, side_effect=AssertionError('disk spool or database reached'))
            mock = guarded.start()
            self.addCleanup(guarded.stop)
            self.addCleanup(mock.assert_not_called)
        for target, buffers in (
            ('data_security.adapters.django.private_ingress.BytesIO', self.body_buffers),
            ('data_security.adapters.django.uploads.BytesIO', self.upload_buffers),
        ):
            observed = patch(target, side_effect=lambda buffers=buffers: _ObservedBuffer(buffers))
            observed.start()
            self.addCleanup(observed.stop)

    def tearDown(self):
        self.assertTrue(all(buffer.closed for buffer in self.body_buffers + self.upload_buffers))
        self.assertTrue(all(buffer.peak <= self.budget for buffer in self.body_buffers))
        self.assertTrue(all(buffer.peak <= _LIMITS.max_bytes for buffer in self.upload_buffers))
        self.assertIs(ASGIHandler.read_body, self.default_read_body)
        self.assertEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 1)

    def consume(self, request):
        self.requests.append(request)
        self.assertEqual(len(request.upload_handlers), 1)
        self.assertIsInstance(request.upload_handlers[0], BoundedUploadHandler)
        if request.content_type == 'application/octet-stream':
            self.saved.append(request.read())
        else:
            uploads = request.FILES.getlist('files')
            for upload in uploads:
                self.assertIs(type(upload), InMemoryUploadedFile)
                self.assertFalse(upload.closed)
            self.uploads.extend(uploads)
            self.saved.extend(upload.read() for upload in uploads)
        return HttpResponse(b'accepted', status=201)

    def multipart(self, contents, **fields):
        return encode_multipart(BOUNDARY, {'files': [
            SimpleUploadedFile('synthetic.txt', content, content_type='text/plain')
            for content in contents], **fields})

    def scope(self, body, *, path=_PATHS[1], content_type=MULTIPART_CONTENT):
        return {'type': 'http', 'method': 'POST', 'path': path, 'root_path': '',
                'server': ('testserver', 80), 'query_string': b'', 'headers': [
                    (b'content-type', content_type.encode('ascii')),
                    (b'content-length', str(len(body)).encode('ascii'))]}

    def frames(self, body):
        return [{'type': 'http.request', 'body': body[start:start + 257],
                 'more_body': start + 257 < len(body)}
                for start in range(0, max(1, len(body)), 257)]

    def exchange(self, scope, messages, *, ingress=None, send=None):
        pending = deque(messages)

        async def receive():
            if pending:
                message = pending.popleft()
                if isinstance(message, BaseException):
                    raise message
                return message
            # Django's normal disconnect listener waits until response completion.
            await asyncio.Future()

        self.receive = AsyncMock(side_effect=receive)
        self.send = send if send is not None else AsyncMock()
        asyncio.run((ingress or self.ingress).asgi(scope, self.receive, self.send))
        return [call.args[0] for call in self.send.await_args_list]

    def test_limits_are_required_and_baseline_object_caps_are_unchanged(self):
        with self.assertRaises(TypeError):
            OpenPrivateUploadIngress(Mock(), paths=_PATHS)
        self.assertEqual(BASELINE_LIMITS.max_bytes, 20 * 1024 * 1024)
        self.assertEqual(BASELINE_LIMITS.max_inflight_objects, 2)

    def test_wsgi_selected_paths_patterns_and_mounts_use_existing_boundary(self):
        contents = [b'a' * _LIMITS.max_bytes, b'b' * _LIMITS.max_bytes]
        body = self.multipart(contents)
        ingress = OpenPrivateUploadIngress(self.consume, paths=_PATHS, patterns=_PATTERNS, limits=_LIMITS)
        for prefix in ('', '/mounted'):
            for path in (*_PATHS, _FEEDBACK, _FEEDBACK.rstrip('/')):
                with self.subTest(prefix=prefix, path=path):
                    self.saved.clear()
                    request = self.factory.generic('POST', path, body,
                        content_type=MULTIPART_CONTENT, SCRIPT_NAME=prefix)
                    self.assertEqual(request.path, prefix + path)
                    self.assertEqual(ingress(request).status_code, 201)
                    self.assertEqual(self.saved, contents)
                    self.assertTrue(all(upload.closed for upload in self.uploads))
        self.assertEqual(self.body_buffers, [])

    def test_wsgi_other_paths_preserve_request_handlers_and_response(self):
        response = object()
        application = Mock(return_value=response)
        ingress = OpenPrivateUploadIngress(application, paths=_PATHS, patterns=_PATTERNS, limits=_LIMITS)
        for path in ('/ordinary/', _FEEDBACK + 'extra', '/prefix' + _PATHS[1],
                     '/api/feedback/not-a-uuid/attachments/'):
            request = self.factory.post(path)
            handlers = request.upload_handlers
            request._stream = Mock()
            request._stream.read.side_effect = AssertionError('unselected body read')
            self.assertIs(ingress(request), response)
            self.assertIs(request.upload_handlers, handlers)
            application.assert_called_with(request)
            request._stream.read.assert_not_called()
        self.assertEqual(self.body_buffers + self.upload_buffers, [])

    def test_wsgi_keeps_per_object_and_retained_part_limits(self):
        ingress = OpenPrivateUploadIngress(self.consume, paths=_PATHS, limits=_LIMITS)
        for contents, error in (([b'x' * 1025], RequestDataTooBig), ([b'x'] * 3, TooManyFilesSent)):
            with self.subTest(error=error):
                request = self.factory.generic('POST', _PATHS[1], self.multipart(contents),
                    content_type=MULTIPART_CONTENT)
                with self.assertRaises(error):
                    ingress(request)
                self.assertEqual(self.saved, [])
                self.assertLessEqual(len(request.upload_handlers[0].buffers), _LIMITS.max_inflight_objects)
                self.assertTrue(all(buffer.closed for buffer in request.upload_handlers[0].buffers))

    def test_asgi_real_multipart_frames_use_memory_and_close_after_response(self):
        contents = [b'a' * 1024, b'b' * 1024]
        body = self.multipart(contents)
        messages = self.exchange(self.scope(body), self.frames(body))
        self.assertEqual(messages[0]['status'], 201)
        self.assertEqual(messages[-1]['body'], b'accepted')
        self.assertEqual(self.saved, contents)
        self.assertEqual(len(self.body_buffers), 1)
        self.assertEqual(self.body_buffers[0].peak, len(body))
        self.assertEqual(self.ingress._asgi_handler.max_body_bytes, self.budget)
        self.assertEqual(len(self.upload_buffers), 2)
        self.assertTrue(all(upload.closed for upload in self.uploads))
        self.application.assert_not_awaited()

    def test_asgi_object_and_part_limits_still_apply_after_body_admission(self):
        for contents in ([b'x' * 1025], [b'x'] * 3):
            with self.subTest(sizes=[len(content) for content in contents]):
                body = self.multipart(contents)
                self.assertLess(len(body), self.budget)
                messages = self.exchange(self.scope(body), self.frames(body))
                self.assertEqual(messages[0]['status'], 400)
                self.assertEqual(self.saved, [])
                handler = self.requests[-1].upload_handlers[0]
                self.assertLessEqual(len(handler.buffers), _LIMITS.max_inflight_objects)
                self.assertTrue(all(buffer.closed for buffer in handler.buffers))

    def test_asgi_exact_total_budget_includes_multipart_text_and_metadata(self):
        contents = [b'a' * 1024, b'b' * 1024]
        padding = self.budget - len(self.multipart(contents, note=''))
        self.assertGreater(padding, 0)
        exact = self.multipart(contents, note='t' * padding)
        self.assertEqual(len(exact), self.budget)
        self.assertEqual(self.exchange(self.scope(exact), self.frames(exact))[0]['status'], 201)
        self.assertEqual(self.saved, contents)
        self.assertEqual(self.requests[0].POST['note'], 't' * padding)
        self.requests.clear()
        self.saved.clear()
        excess = self.multipart(contents, note='t' * (padding + 1))
        self.assertEqual(len(excess), self.budget + 1)
        messages = self.exchange(self.scope(excess), self.frames(excess))
        self.assertEqual(messages, [
            {'type': 'http.response.start', 'status': 413,
             'headers': [(b'cache-control', b'no-store'), (b'content-length', b'0')]},
            {'type': 'http.response.body', 'body': b''}])
        self.assertEqual(self.requests, [])
        self.assertEqual(self.saved, [])

    def test_asgi_observed_frames_not_content_length_control_admission(self):
        for declared in (None, b'0', b'1', b'999999999', b'invalid'):
            with self.subTest(declared=declared):
                scope = self.scope(b'', content_type='application/octet-stream')
                scope['headers'] = [header for header in scope['headers'] if header[0] != b'content-length']
                if declared is not None:
                    scope['headers'].append((b'content-length', declared))
                messages = self.exchange(scope, [
                    {'type': 'http.request', 'body': b'x' * (self.budget - 1), 'more_body': True},
                    {'type': 'http.request', 'body': b'xx', 'more_body': True},
                    {'type': 'http.request', 'body': b'unread', 'more_body': False}])
                self.assertEqual(messages[0]['status'], 413)
                self.assertEqual(self.receive.await_count, 2)
                self.assertEqual(self.body_buffers[-1].peak, self.budget - 1)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.upload_buffers, [])
        self.application.assert_not_awaited()

    def test_asgi_oversized_first_frame_is_not_copied_to_buffer(self):
        body = b'x' * (self.budget + 1)
        messages = self.exchange(self.scope(body), [
            {'type': 'http.request', 'body': body, 'more_body': False}])
        self.assertEqual(messages[0]['status'], 413)
        self.assertEqual(self.body_buffers[0].peak, 0)
        self.assertTrue(self.body_buffers[0].closed)
        self.assertEqual(self.requests, [])

    def test_asgi_empty_frames_and_exact_raw_budget_are_usable(self):
        for body in (b'', b'x' * self.budget):
            with self.subTest(size=len(body)):
                messages = self.exchange(self.scope(body, content_type='application/octet-stream'), [
                    {'type': 'http.request', 'body': b'', 'more_body': True}, *self.frames(body)])
                self.assertEqual(messages[0]['status'], 201)
                self.assertEqual(self.saved[-1], body)
                self.assertTrue(self.body_buffers[-1].closed)

    def test_asgi_disconnect_closes_partial_body_without_view_or_response(self):
        messages = self.exchange(self.scope(b'x' * 100), [
            {'type': 'http.request', 'body': b'partial', 'more_body': True},
            {'type': 'http.disconnect'}])
        self.assertEqual(messages, [])
        self.assertEqual(self.receive.await_count, 2)
        self.assertEqual(self.body_buffers[0].peak, len(b'partial'))
        self.assertTrue(self.body_buffers[0].closed)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.upload_buffers, [])

    def test_asgi_receive_error_and_cancellation_close_partial_memory(self):
        for error in (OSError('synthetic interrupted transport'), asyncio.CancelledError()):
            with self.subTest(error=type(error)):
                with self.assertRaises(type(error)):
                    self.exchange(self.scope(b'x' * 100), [
                        {'type': 'http.request', 'body': b'partial', 'more_body': True}, error])
                self.assertTrue(self.body_buffers[-1].closed)
                self.send.assert_not_awaited()
                self.assertEqual(self.requests, [])
                self.assertEqual(self.upload_buffers, [])

    def test_asgi_rejection_send_failure_propagates_after_memory_is_closed(self):
        body = b'x' * (self.budget + 1)
        send = AsyncMock(side_effect=OSError('synthetic send failure'))
        with self.assertRaisesRegex(OSError, 'synthetic send failure'):
            self.exchange(self.scope(body), self.frames(body), send=send)
        send.assert_awaited_once()
        self.assertTrue(self.body_buffers[0].closed)
        self.assertEqual(self.requests, [])

    def test_asgi_path_patterns_mounts_and_forced_prefix_match_django_request(self):
        body = self.multipart([b'synthetic'])
        for forced, prefix, root in ((None, '', ''), (None, '/mounted', '/mounted'),
                                     ('/forced', '/forced', '/ignored')):
            with override_settings(FORCE_SCRIPT_NAME=forced):
                for path in (*_PATHS, _FEEDBACK, _FEEDBACK.rstrip('/')):
                    with self.subTest(forced=forced, path=path):
                        scope = self.scope(body, path=prefix + path)
                        scope['root_path'] = root
                        self.assertEqual(self.exchange(scope, self.frames(body))[0]['status'], 201)
                        self.assertEqual(self.requests[-1].path_info, path)
                        self.assertEqual(self.saved[-1], b'synthetic')
                        self.assertTrue(self.body_buffers[-1].closed)
        self.application.assert_not_awaited()

    def test_asgi_unselected_and_non_http_are_transparent_without_handler_creation(self):
        application = AsyncMock()
        ingress = OpenPrivateUploadIngress(application, paths=_PATHS, patterns=_PATTERNS, limits=_LIMITS)
        for scope in ({'type': 'http', 'path': '/ordinary/'},
                      {'type': 'http', 'path': _FEEDBACK + 'extra'},
                      {'type': 'http', 'path': '/prefix' + _PATHS[1]},
                      {'type': 'lifespan'}, {'type': 'websocket', 'path': _PATHS[1]}):
            self.exchange(scope, [], ingress=ingress)
            application.assert_awaited_with(scope, self.receive, self.send)
            self.receive.assert_not_awaited()
            self.send.assert_not_awaited()
        self.assertIsNone(ingress._asgi_handler)
        self.assertEqual(self.body_buffers + self.upload_buffers, [])
