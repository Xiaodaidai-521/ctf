"""Resource owner with real B, file keys, multipart parsing and isolated PostgreSQL."""
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection
from django.test import TransactionTestCase, override_settings
from PIL import Image
from rest_framework.test import APIRequestFactory, force_authenticate

from ctf_backend.security_bootstrap import assemble_resource_uploads
from data_security.adapters.django.uploads import PrivateUploadBoundary
from data_security.adapters.persistence.models import PrivateObject
from data_security.contracts import (
    BASELINE_LIMITS, CipherEnvelope, ContractViolation, Environment, ObjectContext,
    ProtectionError, ReasonCode, StoredObject,
)
from data_security.tests.phase3_fixtures import configuration
from users.models import CTFUser

from .models import Resource
from .serializers import ResourceSerializer, ResourceUploadSerializer
from .views import ResourceUploadView, resource_download_view


class PrivateResourceUploadFixture:
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        files = configuration(providers=())
        self.config_path, self.config, _, _, _ = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        checkpoints = self.config_path.parent / 'checkpoints'
        checkpoints.mkdir(mode=0o700)
        self.config.update(schema_version='ds.bootstrap.v2',
            policy_repository={'kind': 'file', 'writable': False}, audit_chain={
                'chain_version': 'ds.audit.v2', 'project_ref': 'resource-upload/synthetic',
                'object_uuid': '00000000-0000-0000-0000-000000000001', 'object_version': '1',
                'authorization_ref': 'authorization/synthetic-audit-owner', 'retained_keys': [],
                'checkpoint_root': str(checkpoints), 'checkpoint_ref': None})
        self.config_path.write_text(json.dumps(self.config))
        self.root = self.config_path.parent / 'private'
        self.root.mkdir(mode=0o700)
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.media = Path(media.name)
        settings = override_settings(MEDIA_ROOT=media.name, FILE_UPLOAD_MAX_MEMORY_SIZE=1)
        settings.enable()
        self.addCleanup(settings.disable)
        self.uploads = assemble_resource_uploads(config_path=self.config_path,
            private_root=self.root, project_ref='resource-upload/synthetic')
        self.preparation = self.uploads.prepare.__self__
        self.teacher = CTFUser.objects.create_user(username='private-upload-teacher', role='teacher')
        self.factory = APIRequestFactory()
        self.content = b'synthetic private resource content'

    def data(self, *, cover=False):
        data = dict(title='合成资料', description='隔离测试资料', resource_type='document',
            category='security', file=SimpleUploadedFile('synthetic.txt', self.content, content_type='text/plain'))
        if cover:
            image = BytesIO()
            Image.new('RGB', (2, 2), (30, 60, 90)).save(image, format='PNG')
            self.cover_bytes = image.getvalue()
            data['cover_image'] = SimpleUploadedFile('synthetic.png', self.cover_bytes, content_type='image/png')
        return data

    def post(self, *, data=None, user=None, enabled=True):
        uploads = self.uploads if enabled else None

        class ExplicitPrivateResourceUploadView(ResourceUploadView):
            def get_serializer_context(self):
                return {**super().get_serializer_context(), 'private_uploads': uploads}

        request = self.factory.post('/api/resources/upload/', data or self.data(), format='multipart')
        force_authenticate(request, user=user or self.teacher)
        boundary = PrivateUploadBoundary(ExplicitPrivateResourceUploadView.as_view(), limits=BASELINE_LIMITS)
        with patch('django.core.files.uploadhandler.TemporaryUploadedFile',
                   side_effect=AssertionError('ordinary upload spool reached')), \
             patch('django.core.files.storage.FileSystemStorage._save',
                   side_effect=AssertionError('ordinary FileField save reached')):
            response = boundary(request)
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertTrue(all(buffer.closed for buffer in request.upload_handlers[0].buffers))
        return response

    def stored_context(self, resource, field):
        item = resource.private_files['files'][field]
        context = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})
        return StoredObject.from_wire(item['stored']), context


class PrivateResourceUploadTests(PrivateResourceUploadFixture, TransactionTestCase):
    def test_new_original_and_cover_are_ciphertext_and_resource_has_only_private_references(self):
        response = self.post(data=self.data(cover=True))
        self.assertEqual(response.status_code, 201)
        resource = Resource.objects.get()
        # FileField persists an empty FieldFile as '', including a None cover.
        self.assertEqual((resource.file.name, resource.cover_image.name, resource.status), ('', '', 'pending'))
        self.assertEqual(resource.file_size, len(self.content))
        self.assertEqual(resource.uploader_id, self.teacher.pk)
        self.assertEqual(set(resource.private_files['files']), {'file', 'cover_image'})
        self.assertEqual(PrivateObject.objects.count(), 2)
        identities = []
        for field, expected in (('file', self.content), ('cover_image', self.cover_bytes)):
            stored, context = self.stored_context(resource, field)
            self.assertEqual(stored.state, 'verified')
            self.assertEqual(context.field_ref, 'resources/' + field)
            identities.append(context.object_uuid)
            path = self.root / (stored.object_ref.removeprefix('private/') + '.sealed')
            encoded = path.read_bytes()
            self.assertNotIn(expected, encoded)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            envelope = CipherEnvelope.from_json(encoded)
            opened = self.preparation.crypto.open(envelope, context, envelope.key)
            self.assertIsNot(type(opened), ProtectionError)
            self.assertTrue(opened.binary == expected)
            self.assertEqual(self.preparation.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(identities[0], identities[1])
        public = ResourceSerializer(resource).data
        self.assertNotIn('private_files', public)
        self.assertIsNone(public['file_url'])
        self.assertIsNone(public['cover_url'])
        self.assertIsNone(public['cover_image'])

    def test_current_database_role_and_active_state_override_cached_request_user(self):
        for change in ({'role': 'student'}, {'is_active': False}):
            with self.subTest(change=change):
                CTFUser.objects.filter(pk=self.teacher.pk).update(role='teacher', is_active=True)
                CTFUser.objects.filter(pk=self.teacher.pk).update(**change)
                self.assertEqual(self.post().status_code, 400)
                self.assertEqual(Resource.objects.count(), 0)
                self.assertEqual(PrivateObject.objects.count(), 0)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_client_metadata_cannot_supply_private_references_or_approve_upload(self):
        data = self.data()
        data.update(private_files='forged', status='approved', uploader='9999', file_size='1')
        self.assertEqual(self.post(data=data).status_code, 201)
        resource = Resource.objects.get()
        self.assertEqual(resource.private_files['schema_version'], 'resource.private-upload.v1')
        self.assertEqual(resource.status, 'pending')
        self.assertEqual(resource.file_size, len(self.content))
        self.assertEqual(resource.uploader_id, self.teacher.pk)

    def test_cover_failure_keeps_only_unreadable_original_candidate_and_no_resource(self):
        prepare = self.uploads.prepare
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
            retryable=False, trace_id='resource-upload/synthetic-failure')

        def fail_cover(payload, context):
            return failure if context.field_ref.endswith('cover_image') else prepare(payload, context)

        with patch.object(self.uploads, 'prepare', side_effect=fail_cover):
            self.assertEqual(self.post(data=self.data(cover=True)).status_code, 400)
        self.assertEqual(Resource.objects.count(), 0)
        self.assertEqual(list(PrivateObject.objects.values_list('state', flat=True)), ['verified'])
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_resource_database_failure_does_not_delete_or_publish_durable_ciphertext(self):
        with patch.object(Resource.objects, 'create', side_effect=DatabaseError('synthetic failure')):
            self.assertEqual(self.post().status_code, 400)
        self.assertEqual(Resource.objects.count(), 0)
        self.assertEqual(list(PrivateObject.objects.values_list('state', flat=True)), ['verified'])
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_existing_review_status_does_not_publish_private_original(self):
        self.assertEqual(self.post().status_code, 201)
        resource = Resource.objects.get()
        resource.status = 'approved'
        resource.save(update_fields=['status'])
        request = self.factory.get(f'/api/resources/{resource.pk}/download/')
        force_authenticate(request, user=self.teacher)
        self.assertEqual(resource_download_view(request, resource.pk).status_code, 404)
        resource.refresh_from_db()
        self.assertEqual(resource.download_count, 0)
        stored, context = self.stored_context(resource, 'file')
        self.assertEqual(self.preparation.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)

    def test_explicitly_missing_service_fails_closed_without_legacy_fallback(self):
        self.assertEqual(self.post(enabled=False).status_code, 400)
        self.assertEqual(Resource.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.count(), 0)

    def test_original_format_validation_runs_before_private_preparation(self):
        data = self.data()
        data['file'] = SimpleUploadedFile('synthetic.txt', b'<script>synthetic</script>', content_type='text/plain')
        with patch.object(self.uploads, 'prepare', wraps=self.uploads.prepare) as prepare:
            self.assertEqual(self.post(data=data).status_code, 400)
            prepare.assert_not_called()
        self.assertEqual(Resource.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.count(), 0)

    def test_unbound_serializer_keeps_original_baseline_behavior(self):
        serializer = ResourceUploadSerializer(data=self.data(), context={'request': type('Request', (), {'user': self.teacher})()})
        self.assertTrue(serializer.is_valid())
        resource = serializer.save()
        self.assertEqual(resource.private_files, {})
        self.assertTrue(resource.file.name.startswith('resources/'))
        self.assertEqual(len(list(self.media.rglob('*.txt'))), 1)
        self.assertEqual(PrivateObject.objects.count(), 0)

    def test_bootstrap_rejects_nonprivate_root_without_enabling_any_route(self):
        self.root.chmod(0o755)
        with self.assertRaises(ContractViolation):
            assemble_resource_uploads(config_path=self.config_path,
                private_root=self.root, project_ref='resource-upload/synthetic')
        self.assertEqual(Resource.objects.count(), 0)
        self.assertEqual(PrivateObject.objects.count(), 0)
