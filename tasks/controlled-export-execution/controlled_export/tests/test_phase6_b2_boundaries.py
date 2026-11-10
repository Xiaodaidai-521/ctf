"""Independent executor composition and real HTTP parsing without database access."""
import asyncio
from dataclasses import replace
import json
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

from controlled_export.storage import PrivateStorage
from controlled_export.errors import ControlledExportError
from controlled_export_service.security_bootstrap import (
    guard_private_upload_asgi, private_upload_middleware, start_application,
)
from data_security.contracts import BASELINE_LIMITS, ContractViolation
from data_security.tests.phase3_fixtures import configuration

from .helpers import INTERNAL_KEY


class ExecutorPrivateBoundaryTests(TestCase):
    def setUp(self):
        files = configuration(providers=())
        self.path, original, refs, _, _ = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        self.root = self.path.parent / 'sealed'
        self.root.mkdir(mode=0o700)
        self.legacy = self.path.parent / 'legacy'
        self.legacy.mkdir(mode=0o700)
        self.config = {'schema_version': 'ds.executor-preparation.v1', 'environment': 'evaluation',
            'key_manifest': original['key_manifest'], 'data_key': refs['data_key'].to_wire(),
            'private_root': str(self.root), 'project_ref': 'executor/b2-synthetic',
            'limits': BASELINE_LIMITS.to_wire()}
        self.path.write_text(json.dumps(self.config))
        self.configured = override_settings(CONTROLLED_EXPORT_PRIVATE_MODE=True,
            CONTROLLED_EXPORT_PRIVATE_CONFIG=str(self.path), CONTROLLED_EXPORT_PRIVATE_PREPARATION=None,
            CONTROLLED_EXPORT_PRIVATE_ROOT=self.legacy, CONTROLLED_EXPORT_ENVIRONMENT='evaluation',
            CONTROLLED_EXPORT_INTERNAL_KEY=INTERNAL_KEY, EXECUTION_AUTHORITY_HMAC_SECRET='synthetic-authority',
            SECRET_KEY='synthetic-framework', ALLOWED_HOSTS=['testserver'],
            MIDDLEWARE=['controlled_export_service.security_bootstrap.private_upload_middleware'],
            FILE_UPLOAD_MAX_MEMORY_SIZE=1)
        self.configured.enable()
        self.addCleanup(self.configured.disable)

    def test_config_composes_only_preparation_and_observation_without_io(self):
        from django.conf import settings

        start_application()
        components = settings.CONTROLLED_EXPORT_PRIVATE_PREPARATION
        self.assertEqual(set(components), {'execute', 'observe', 'reconcile', 'limits'})
        self.assertTrue(all(callable(components[name]) for name in ('execute', 'observe', 'reconcile')))
        self.assertEqual(list(self.root.iterdir()), [])
        with self.assertRaises(ControlledExportError) as error:
            PrivateStorage()
        self.assertEqual(error.exception.code, 'LEGACY_STORAGE_DISABLED')
        self.assertEqual(list(self.legacy.iterdir()), [])

    def test_configuration_cannot_open_production_or_skip_service_credentials(self):
        for changes in ({'CONTROLLED_EXPORT_ENVIRONMENT': 'production'},
                        {'CONTROLLED_EXPORT_INTERNAL_KEY': ''},
                        {'EXECUTION_AUTHORITY_HMAC_SECRET': ''}):
            with self.subTest(changes=tuple(changes)), override_settings(**changes), self.assertRaises(ContractViolation):
                start_application()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_encrypted_root_cannot_overlap_legacy_storage(self):
        self.config['private_root'] = str(self.legacy)
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            start_application()
        self.assertEqual(list(self.legacy.iterdir()), [])

    def test_unbound_baseline_preserves_original_wsgi_and_asgi_applications(self):
        application = Mock()
        with override_settings(CONTROLLED_EXPORT_PRIVATE_MODE=False, CONTROLLED_EXPORT_PRIVATE_PREPARATION=None):
            self.assertIs(private_upload_middleware(application), application)
            self.assertIs(guard_private_upload_asgi(application), application)

    def test_formal_missing_capability_and_legacy_shares_close_before_wsgi_body(self):
        application = Mock(side_effect=AssertionError('closed downstream reached'))
        for path in ('/api/controlled-export/executions/', '/api/controlled-export/shares/',
                     '/api/controlled-export/shares/' + str(uuid4()) + '/download/',
                     '/api/controlled-export/deliveries/' + str(uuid4()) + '/result/'):
            request = RequestFactory().post(path, b'original', content_type='application/octet-stream')
            with patch.object(request._stream, 'read', side_effect=AssertionError('closed body read')):
                self.assertEqual(private_upload_middleware(application)(request).status_code, 503)
        application.assert_not_called()

    def _asgi(self, path, body, *, content_type='application/octet-stream', headers=()):
        application = AsyncMock(side_effect=AssertionError('default ASGI spool reached'))
        pending = [{'type': 'http.request', 'body': body}]

        async def receive():
            if pending:
                return pending.pop()
            await asyncio.Future()

        receive, send = AsyncMock(side_effect=receive), AsyncMock()
        scope = {'type': 'http', 'method': 'POST', 'path': path, 'root_path': '',
            'server': ('testserver', 80), 'query_string': b'', 'headers': [
                (b'content-type', content_type.encode()), (b'content-length', str(len(body)).encode()), *headers]}
        with patch('django.core.handlers.asgi.tempfile.SpooledTemporaryFile', side_effect=AssertionError('ASGI disk spool')), \
             patch('django.core.files.uploadhandler.TemporaryUploadedFile', side_effect=AssertionError('multipart disk spool')):
            asyncio.run(guard_private_upload_asgi(application)(scope, receive, send))
        application.assert_not_awaited()
        return receive, [call.args[0] for call in send.await_args_list]

    def test_closed_asgi_upload_and_share_do_not_receive_any_body(self):
        for path in ('/api/controlled-export/executions/', '/api/controlled-export/shares/'):
            receive, messages = self._asgi(path, b'original')
            receive.assert_not_awaited()
            self.assertEqual(messages[0]['status'], 503)
            self.assertEqual(messages[-1]['body'], b'')

    def test_enabled_asgi_multipart_is_in_memory_and_reaches_injected_executor(self):
        execute = Mock(return_value=({'status': 'prepared'}, False))
        components = {'execute': execute, 'limits': replace(BASELINE_LIMITS, max_bytes=1024, max_text_chars=1024)}
        body = encode_multipart(BOUNDARY, {'authorization': '{}', 'plan': '{}',
            'file': SimpleUploadedFile('synthetic.csv', b'a,b\n1,2\n', content_type='text/csv')})
        headers = [(b'x-internal-authorization', ('Bearer ' + INTERNAL_KEY).encode()),
            (b'x-caller-id', b'b2-synthetic-service'), (b'x-authorization-signature', b'0' * 64),
            (b'idempotency-key', b'b2-private')]
        with override_settings(CONTROLLED_EXPORT_PRIVATE_PREPARATION=components):
            _, messages = self._asgi('/api/controlled-export/executions/', body,
                content_type=MULTIPART_CONTENT, headers=headers)
        self.assertEqual(messages[0]['status'], 201)
        self.assertEqual(execute.call_args.kwargs['content'], b'a,b\n1,2\n')
        self.assertEqual(execute.call_args.kwargs['caller_id'], 'b2-synthetic-service')
        value = json.loads(b''.join(message.get('body', b'') for message in messages))
        self.assertEqual(value, {'status': 'prepared', 'idempotent_replay': False})

    def test_reference_observation_rejects_oversize_body_without_disk_spool(self):
        _, messages = self._asgi('/api/controlled-export/executions/' + str(uuid4()) + '/preparation/', b'x' * 65537)
        self.assertEqual(messages[0]['status'], 413)
        self.assertEqual(messages[-1]['body'], b'')
