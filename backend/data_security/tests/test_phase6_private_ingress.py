"""Closed ingress never consumes private bytes; unbound behavior stays unchanged."""
import asyncio
import os
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

from django.conf import settings
from django.test import RequestFactory, override_settings

from ctf_backend.security_bootstrap import guard_private_upload_asgi, private_upload_middleware
from data_security.adapters.django.private_ingress import ClosedPrivateUploadIngress


class PrivateIngressTests(TestCase):
    def setUp(self):
        self.assertEqual(settings.DEFAULT_CHARSET, 'utf-8')
        self.paths = ('/api/resources/upload', '/api/resources/upload/')
        self.factory = RequestFactory()

    def test_wsgi_refuses_both_paths_before_body_or_inner_middleware(self):
        application = Mock(side_effect=AssertionError('inner middleware reached'))
        ingress = ClosedPrivateUploadIngress(application, paths=self.paths)
        for path in self.paths:
            request = self.factory.post(path, b'synthetic private body', content_type='application/octet-stream')
            request._stream = Mock()
            request._stream.read.side_effect = AssertionError('request body read')
            response = ingress(request)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.content, b'')
            self.assertEqual(response['Cache-Control'], 'no-store')
            self.assertFalse(request._read_started)
            request._stream.read.assert_not_called()
        application.assert_not_called()

    def test_wsgi_other_paths_preserve_original_response_and_request(self):
        result = object()
        application = Mock(return_value=result)
        request = self.factory.get('/api/resources/12/download/')
        self.assertIs(ClosedPrivateUploadIngress(application, paths=self.paths)(request), result)
        application.assert_called_once_with(request)

    def test_asgi_refuses_before_receive_and_default_disk_spool(self):
        async def run():
            application = AsyncMock(side_effect=AssertionError('Django handler reached'))
            receive = AsyncMock(side_effect=AssertionError('body received'))
            ingress = ClosedPrivateUploadIngress(application, paths=self.paths)
            for path in self.paths:
                send = AsyncMock()
                await ingress.asgi({'type': 'http', 'path': path, 'method': 'POST'}, receive, send)
                self.assertEqual([call.args[0] for call in send.await_args_list], [
                    {'type': 'http.response.start', 'status': 503,
                     'headers': [(b'cache-control', b'no-store'), (b'content-length', b'0')]},
                    {'type': 'http.response.body', 'body': b''}])
            receive.assert_not_awaited()
            application.assert_not_awaited()

        with patch('django.core.handlers.asgi.tempfile.SpooledTemporaryFile',
                   side_effect=AssertionError('default ASGI spool reached')):
            asyncio.run(run())

    def test_asgi_mount_and_force_script_name_match_django_path_info(self):
        async def run(scope):
            application, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
            await ClosedPrivateUploadIngress(application, paths=self.paths).asgi(scope, receive, send)
            self.assertEqual(send.await_args_list[0].args[0]['status'], 503)
            application.assert_not_awaited()
            receive.assert_not_awaited()

        asyncio.run(run({'type': 'http', 'path': '/mounted/api/resources/upload/', 'root_path': '/mounted'}))
        with override_settings(FORCE_SCRIPT_NAME='/forced'):
            asyncio.run(run({'type': 'http', 'path': '/forced/api/resources/upload/', 'root_path': '/ignored'}))

    def test_asgi_other_paths_and_non_http_scopes_are_not_reinterpreted(self):
        async def run():
            for scope in ({'type': 'http', 'path': '/api/resources/9/download/'},
                          {'type': 'lifespan'}, {'type': 'websocket', 'path': '/ws/chat/'}):
                application, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
                await ClosedPrivateUploadIngress(application, paths=self.paths).asgi(scope, receive, send)
                application.assert_awaited_once_with(scope, receive, send)
                receive.assert_not_awaited()
                send.assert_not_awaited()
        asyncio.run(run())

    def test_asgi_send_failure_propagates_without_reading_or_retrying(self):
        async def run():
            application, receive = AsyncMock(), AsyncMock()
            send = AsyncMock(side_effect=OSError('synthetic closed connection'))
            with self.assertRaises(OSError):
                await ClosedPrivateUploadIngress(application, paths=self.paths).asgi(
                    {'type': 'http', 'path': self.paths[1]}, receive, send)
            self.assertEqual(send.await_count, 1)
            application.assert_not_awaited()
            receive.assert_not_awaited()
        asyncio.run(run())

    def test_feedback_pattern_refuses_wsgi_before_body(self):
        path = '/api/feedback/00000000-0000-0000-0000-000000000001/attachments/'
        application = Mock(side_effect=AssertionError('inner reached'))
        with patch.dict(os.environ, {'DATA_SECURITY_CONFIG': '/synthetic/already-validated.json'}):
            ingress = private_upload_middleware(application)
            for target in (path, path.rstrip('/')):
                request = self.factory.post(target, b'synthetic body', content_type='application/octet-stream')
                request._stream = Mock()
                request._stream.read.side_effect = AssertionError('body read')
                response = ingress(request)
                self.assertEqual((response.status_code, response.content), (503, b''))
                self.assertEqual(response['Cache-Control'], 'no-store')
                self.assertFalse(request._read_started)
                request._stream.read.assert_not_called()
        application.assert_not_called()

    def test_feedback_pattern_refuses_asgi_mounts_and_forced_prefix_before_receive(self):
        path = '/api/feedback/00000000-0000-0000-0000-000000000001/attachments/'

        async def run(prefix, root):
            application, receive = AsyncMock(), AsyncMock(side_effect=AssertionError('body received'))
            with patch.dict(os.environ, {'DATA_SECURITY_CONFIG': '/synthetic/already-validated.json'}):
                ingress = guard_private_upload_asgi(application)
            for target in (path, path.rstrip('/')):
                send = AsyncMock()
                await ingress({'type': 'http', 'path': prefix + target, 'root_path': root}, receive, send)
                self.assertEqual([call.args[0] for call in send.await_args_list], [
                    {'type': 'http.response.start', 'status': 503,
                     'headers': [(b'cache-control', b'no-store'), (b'content-length', b'0')]},
                    {'type': 'http.response.body', 'body': b''}])
            receive.assert_not_awaited()
            application.assert_not_awaited()

        with patch('django.core.handlers.asgi.tempfile.SpooledTemporaryFile', side_effect=AssertionError('disk spool')):
            asyncio.run(run('', ''))
            asyncio.run(run('/mounted', '/mounted'))
            with override_settings(FORCE_SCRIPT_NAME='/forced'):
                asyncio.run(run('/forced', '/ignored'))

    def test_feedback_pattern_does_not_close_detail_download_or_lookalike_routes(self):
        base = '/api/feedback/00000000-0000-0000-0000-000000000001/'
        targets = (base, base + 'evidence/', base + 'attachments/not-a-real-id/download/',
                   base + 'attachments/extra', '/prefix' + base + 'attachments/',
                   '/api/feedback/not-a-uuid/attachments/')

        async def run():
            for target in targets:
                result = object()
                application = Mock(return_value=result)
                async_application, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
                request = self.factory.get(target)
                scope = {'type': 'http', 'path': target}
                with patch.dict(os.environ, {'DATA_SECURITY_CONFIG': '/synthetic/already-validated.json'}):
                    self.assertIs(private_upload_middleware(application)(request), result)
                    await guard_private_upload_asgi(async_application)(scope, receive, send)
                application.assert_called_once_with(request)
                async_application.assert_awaited_once_with(scope, receive, send)
                receive.assert_not_awaited()
                send.assert_not_awaited()
        asyncio.run(run())

    def test_unbound_bootstrap_returns_original_applications(self):
        application = Mock()
        with patch.dict(os.environ, {}, clear=True):
            self.assertIs(private_upload_middleware(application), application)
            self.assertIs(guard_private_upload_asgi(application), application)

    def test_formal_bootstrap_wraps_both_transports_without_loading_owner(self):
        application = Mock(side_effect=AssertionError('inner reached'))
        # Configuration validation occurs during startup, not on each request.
        with patch.dict(os.environ, {'DATA_SECURITY_CONFIG': '/synthetic/already-validated.json'}):
            wrapped = private_upload_middleware(application)
            self.assertEqual(wrapped(self.factory.post(self.paths[1])).status_code, 503)
            asgi = guard_private_upload_asgi(application)
        self.assertIsInstance(asgi.__self__, ClosedPrivateUploadIngress)
        self.assertEqual(asgi.__self__.paths, self.paths)
        application.assert_not_called()
