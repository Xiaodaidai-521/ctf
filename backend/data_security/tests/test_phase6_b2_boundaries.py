"""B2 database-free orchestration and HTTP boundary checks; not persistence acceptance."""
import asyncio
import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from ctf_backend.security_bootstrap import guard_private_upload_asgi
from data_security.adapters.django import export_delivery, private_files
from data_security.application.crypto_service import CryptoService
from data_security.application.private_files import PrivateFilePreparation
from data_security.contracts import (
    BASELINE_LIMITS, BoundedPayload, ContractViolation, DeliveryReceipt, Environment,
    FileUploadOperation, MediaType, ObjectContext, PayloadKind, ProtectionError, ReasonCode, StoredObject,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key
from data_security.tests.private_store_memory import MemoryPrivateStore


class ManagedPreparationBoundaryTests(TestCase):
    def setUp(self):
        self.context, self.operation = examples()[ObjectContext], examples()[FileUploadOperation]
        self.crypto = CryptoService(keys=FakeKeys(), service_identity='private-upload/test',
            random_bytes=os.urandom, environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.records, self.blobs = {}, {}
        self.store = MemoryPrivateStore(records=self.records, blobs=self.blobs,
            crypto=self.crypto, environment=Environment.TEST)
        self.operations = Mock()
        self.operations.retained.return_value = None
        self.preparation = PrivateFilePreparation(crypto=self.crypto, data_key=reference_key(),
            store=self.store, limits=BASELINE_LIMITS, operations=self.operations)
        self.payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
            media_type=MediaType.BINARY, text=None, tree=None, binary=b'b2 synthetic input', limits=BASELINE_LIMITS)

    def test_stage_precedes_write_and_confirm_follows_full_verification(self):
        calls = []
        self.operations.stage.side_effect = lambda *args: calls.append('stage')
        self.operations.confirm.side_effect = lambda *args: calls.append('confirm')
        write, verify = self.store.write_candidate, self.store.verify

        def written(*args):
            calls.append('write')
            return write(*args)

        def verified(*args):
            calls.append('verify')
            return verify(*args)

        with patch.object(self.store, 'write_candidate', side_effect=written), \
             patch.object(self.store, 'verify', side_effect=verified):
            result = self.preparation.prepare(self.payload, self.context, operation=self.operation)
        self.assertIs(type(result), StoredObject)
        self.assertEqual(result.state, 'verified')
        self.assertEqual(calls, ['stage', 'write', 'verify', 'confirm'])
        self.assertNotIn(self.payload.binary, self.blobs[result.object_ref])

    def test_retained_success_and_unknown_never_encrypt_again(self):
        stored = self.preparation.prepare(self.payload, self.context)
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.DELIVERY_UNKNOWN,
            retryable=False, trace_id='b2/retained-unknown')
        for retained in (stored, failure):
            with self.subTest(kind=type(retained).__name__):
                self.operations.reset_mock()
                self.operations.retained.return_value = retained
                with patch.object(self.crypto, 'seal', side_effect=AssertionError('reencrypted retained input')):
                    result = self.preparation.prepare(self.payload, self.context, operation=self.operation)
                self.assertIs(result, retained)
                self.operations.stage.assert_not_called()
                self.assertEqual(self.operations.confirm.call_count, int(retained is stored))

    def test_failed_intention_registration_prevents_any_ciphertext_write(self):
        self.operations.stage.side_effect = ContractViolation(ReasonCode.DELIVERY_UNKNOWN)
        with patch.object(self.store, 'write_candidate', side_effect=AssertionError('write before retained intent')):
            result = self.preparation.prepare(self.payload, self.context, operation=self.operation)
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(self.blobs, {})
        self.operations.confirm.assert_not_called()

    def test_confirm_refusal_preserves_ciphertext_without_publication_or_automatic_cleanup(self):
        self.operations.confirm.side_effect = ContractViolation(ReasonCode.DELIVERY_UNKNOWN)
        result = self.preparation.prepare(self.payload, self.context, operation=self.operation)
        self.assertEqual(result.code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(len(self.blobs), 1)
        self.assertEqual([stored.state for _, stored in self.records.values()], ['verified'])


class PrivateFileHTTPBoundaryTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(pk=7, role='teacher', is_authenticated=True)

    def test_operation_header_requires_canonical_uuid(self):
        operation_id = '01234567-89ab-4cde-8f01-23456789abcd'
        for raw in ('', 'bad', operation_id.upper(), '{' + operation_id + '}', operation_id.replace('-', '')):
            request = self.factory.post('/upload/', HTTP_X_FILE_OPERATION_ID=raw)
            self.assertEqual(private_files.upload_operation_id(request).code, ReasonCode.INVALID_VALUE)
        request = self.factory.post('/upload/', HTTP_X_FILE_OPERATION_ID=operation_id)
        self.assertEqual(str(private_files.upload_operation_id(request)), operation_id)

    def test_invalid_operation_header_rejects_before_body_parsing_or_owner(self):
        from resources.views import ResourceUploadView
        from feedback_center.views import FeedbackAttachmentUploadView

        for view, kwargs in ((ResourceUploadView, {}),
                (FeedbackAttachmentUploadView, {'feedback_id': uuid4()})):
            with self.subTest(view=view.__name__):
                request = self.factory.post('/upload/', b'not multipart', content_type='application/octet-stream')
                force_authenticate(request, self.user)
                owner = Mock(side_effect=AssertionError('invalid retry id reached owner'))
                with patch.object(private_files, '_owners', {'resources': owner, 'feedback': owner}), \
                     patch('rest_framework.request.Request._load_data_and_files', side_effect=AssertionError('body parsed')):
                    response = view.as_view()(request, **kwargs)
                self.assertEqual(response.status_code, 400)
                owner.create.assert_not_called()

    def test_operation_response_never_serializes_server_only_intention(self):
        operation = examples()[FileUploadOperation]
        response = private_files.operation_response(operation, uuid4())
        self.assertEqual(set(response.data), {'operation_id', 'state', 'result_id', 'network_delivery_confirmed'})
        self.assertFalse(response.data['network_delivery_confirmed'])
        self.assertNotIn(operation.object_uuid, str(response.data))

    def test_export_rejects_client_bindings_and_only_forwards_two_references(self):
        owner = Mock()
        for data in ({}, {'source_ref': 'source/1'},
                {'source_ref': 'source/1', 'permission_ref': 'permission/1', 'binding': {}},
                {'source_ref': 'x' * 161, 'permission_ref': 'permission/1'}, []):
            request = self.factory.post('/exports/', data, format='json')
            force_authenticate(request, self.user)
            with patch.object(export_delivery, '_entry', owner):
                response = export_delivery.resource_export(request, operation='execute')
            self.assertEqual(response.status_code, 400)
        owner.execute.assert_not_called()
        receipt = examples()[DeliveryReceipt]
        owner.execute.return_value = receipt
        request = self.factory.post('/exports/', {'source_ref': 'source/1', 'permission_ref': 'permission/1'}, format='json')
        force_authenticate(request, self.user)
        with patch.object(export_delivery, '_entry', owner):
            response = export_delivery.resource_export(request, operation='execute')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['network_delivery_confirmed'])
        self.assertEqual(response.data['execution_ref'], receipt.binding.execution_id)
        owner.execute.assert_called_once_with(user=self.user, source_ref='source/1', permission_ref='permission/1')

    def test_export_download_delegates_to_existing_delivery_owner(self):
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
            media_type=MediaType.CSV, text=None, tree=None, binary=b'value\n[EMAIL]\n', limits=BASELINE_LIMITS)
        owner = Mock()
        owner.open_delivery.return_value = payload
        request = self.factory.post('/exports/', {'source_ref': 'source/1', 'permission_ref': 'permission/1'}, format='json')
        force_authenticate(request, self.user)
        with patch.object(export_delivery, '_entry', owner):
            response = export_delivery.resource_export(request, operation='download')
        self.assertEqual(response.content, payload.binary)
        self.assertFalse(response.streaming)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertIn('export.csv', response['Content-Disposition'])
        owner.open_delivery.assert_called_once_with(user=self.user, source_ref='source/1', permission_ref='permission/1')
        owner.execute.assert_not_called()

    def test_formal_reference_bodies_are_bounded_even_for_closed_or_invalid_operations(self):
        async def run(path, owners):
            application = AsyncMock(side_effect=AssertionError('default ASGI handler reached'))
            receive = AsyncMock(return_value={'type': 'http.request', 'body': b'x' * 65537})
            send = AsyncMock()
            with patch.dict(os.environ, DATA_SECURITY_CONFIG='/synthetic/already-validated.json'), \
                 patch.object(private_files, '_owners', owners), \
                 patch('django.core.handlers.asgi.tempfile.SpooledTemporaryFile', side_effect=AssertionError('disk spool')):
                await guard_private_upload_asgi(application)(
                    {'type': 'http', 'method': 'POST', 'path': path, 'headers': [], 'root_path': ''}, receive, send)
            self.assertEqual(send.await_args_list[0].args[0]['status'], 413)
            self.assertEqual(send.await_args_list[-1].args[0]['body'], b'')
            application.assert_not_awaited()

        paths = ('/api/data-security/exports/resources/INVALID/',
            '/api/data-security/files/shares/00000000-0000-0000-0000-000000000001/',
            '/api/resources/file-operations/00000000-0000-0000-0000-000000000001/')
        with override_settings(MIDDLEWARE=[]):
            for path in paths:
                for owners in ({}, {'resources': object()}):
                    with self.subTest(path=path, bound=bool(owners)):
                        asyncio.run(run(path, owners))
