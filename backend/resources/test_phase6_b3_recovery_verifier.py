"""Real-PG restored-owner inspection cases; dispatch only, not a backup/RPO fixture."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from feedback_center.models import FeedbackAttachment, FeedbackTicket
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from audit.models import AuditLedgerLock, SecurityAuditRecord
from data_security.adapters.persistence.file_shares import DjangoPrivateFileShares
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject
from data_security.adapters.persistence.recovery_verifier import DjangoRecoveryVerifier
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.application.reports import ReportAuthenticator
from data_security.contracts import (
    BASELINE_LIMITS, Environment, ObjectContext, ProtectionContext, ProtectionError, Purpose, ReasonCode, StoredObject,
)
from data_security.tests.fixtures import examples
from export_quota.models import QuotaBucket, QuotaReservation
from users.models import CTFUser
from .models import Resource
from .test_phase6_b3_private_maintenance import LegacyMaintenanceFixture


class RestoredOwnerVerifierTests(LegacyMaintenanceFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.uploads.project_ref = 'ctf'
        self.components['private_uploads']['feedback'].project_ref = 'ctf'
        self.assertEqual(self.upload().status_code, 201)
        self.sink = self.components['audit'].sink
        checkpoint = self.sink.checkpoint('ds.audit.v2')
        self.assertNotIsInstance(checkpoint, ProtectionError)
        self.sink.checkpoint_ref = checkpoint.checkpoint_ref
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', domain='ctf',
            environment=Environment.EVALUATION, purpose=Purpose.STORAGE)
        database = connection.settings_dict

        def verify_report(record):
            auth = ReportAuthenticator(crypto=self.preparation.crypto, key=self.sink.keys[record.proof.key.key_ref],
                executor_ref='service/resource-column-export', environment=Environment.EVALUATION,
                clock=lambda: record.report.created_at)
            return auth.verify(record.report, record.proof, record.binding, record.plan, record.context,
                input_hash=record.plan.input_hash, output_hash=record.report.output_hash,
                ciphertext_hash=record.stored.ciphertext_hash)

        def inspect_share(share_id, read_event):
            owner = DjangoPrivateFileShares(owners=self.components['private_uploads'], audit=self.components['audit'],
                read_event=read_event, policy_binding=self.components['binding'], clock=self.components['clock'], identity=None)
            return owner._load(share_id, terminal=True)

        self.verifier = DjangoRecoveryVerifier(store=self.preparation.store, owners=self.components['private_uploads'],
            audit=self.sink, reports=DjangoReportRepository(environment=Environment.EVALUATION), verify_report=verify_report,
            field_storage=None, field_models=(CTFUser,), inspect_share=inspect_share, limits=BASELINE_LIMITS,
            clock=self.components['clock'], database={'dbname': database['NAME'], 'host': database['HOST'],
                'port': database['PORT'] or 5432})

    def fingerprint(self):
        rows = {model._meta.label: list(model._base_manager.order_by('pk').values()) for model in (
            Resource, FeedbackAttachment, PrivateObject, PrivateFileOperation, SecurityAuditRecord, AuditLedgerLock,
            QuotaBucket, QuotaReservation)}
        return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()

    def test_complete_stage_is_opened_and_source_bound_without_any_writes(self):
        resource, paths = self.legacy(cover=True)
        operation = self.maintain(resource, 'stage')
        self.assertNotIsInstance(operation, ProtectionError)
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        before = self.fingerprint()
        checkpoint_files = sorted(self.sink.checkpoint_root.iterdir())
        with CaptureQueriesContext(connection) as queries:
            result = self.verifier(self.context)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertTrue(result['complete'])
        self.assertFalse(result['opening_allowed'])  # Legacy fields/files remain a closed drill.
        self.assertEqual(result['governance'][operation.operation_ref], self.maintenance.source_hash(row))
        self.assertEqual(result['legacy_files_not_in_private_bundle'], 2)
        self.assertEqual(result['private_objects_opened'], 3)
        self.assertEqual(before, self.fingerprint())
        self.assertEqual(checkpoint_files, sorted(self.sink.checkpoint_root.iterdir()))
        self.assertTrue(all(path.exists() for path in paths.values()))
        sql = [item['sql'].strip().upper() for item in queries]
        self.assertTrue(any('REPEATABLE READ, READ ONLY' in item for item in sql))
        self.assertFalse(any(item.startswith(('INSERT ', 'UPDATE ', 'DELETE ')) or 'FOR UPDATE' in item for item in sql))

    def test_damaged_candidate_cannot_produce_recovery_proof(self):
        resource, _ = self.legacy()
        operation = self.maintain(resource, 'stage')
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        stored = StoredObject.from_wire(row.files['resources/file']['stored'])
        path = self.root / (stored.object_ref.removeprefix('private/') + '.sealed')
        path.write_bytes(path.read_bytes()[:-1])
        before = self.fingerprint()
        result = self.verifier(self.context)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(before, self.fingerprint())
        self.assertTrue(path.exists())

    def test_unselected_checkpoint_is_not_created_during_verification(self):
        self.sink.checkpoint_ref = None
        before = self.fingerprint()
        files = sorted(self.sink.checkpoint_root.iterdir())
        result = self.verifier(self.context)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(before, self.fingerprint())
        self.assertEqual(files, sorted(self.sink.checkpoint_root.iterdir()))

    def test_real_unanchored_suffix_is_reported_without_reanchoring(self):
        from uuid import uuid4
        selected = self.sink.checkpoint_ref
        self.assertEqual(self.upload(operation_id=uuid4()).status_code, 201)
        result = self.verifier(self.context)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result['audit_checkpoint'], selected)
        self.assertEqual(result['audit_unanchored_suffix'], 1)
        self.assertEqual(self.sink.checkpoint_ref, selected)

    def test_unregistered_partial_ciphertext_is_not_adopted_or_deleted(self):
        path = self.root / ('f' * 64 + '.sealed')
        path.write_bytes(b'partial encrypted output, no registration')
        path.chmod(0o600)
        before = self.fingerprint()
        result = self.verifier(self.context)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result['private_objects_opened'], 1)
        self.assertEqual(before, self.fingerprint())
        self.assertEqual(path.read_bytes(), b'partial encrypted output, no registration')

    def test_retired_deleted_candidate_preserves_identity_without_source_proof(self):
        resource, _ = self.legacy()
        operation = self.maintain(resource, 'stage')
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        item = row.files['resources/file']
        PrivateFileOperation.objects.filter(pk=row.pk).update(state='aborted')
        self.assertIs(self.preparation.store.retire_candidate(StoredObject.from_wire(item['stored']),
            ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})), True)
        before = self.fingerprint()
        result = self.verifier(self.context)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertNotIn(operation.operation_ref, result['governance'])
        self.assertEqual(result['retired_objects'], 1)
        self.assertEqual(before, self.fingerprint())

    def test_cleaned_resource_keeps_owner_metadata_and_retired_identity_read_only(self):
        resource = Resource.objects.get()
        metadata = resource.private_files
        self.assertEqual(self.operation(cleanup=True).data['state'], 'cleaned')
        before = self.fingerprint()
        result = self.verifier(self.context)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result['terminal_operations'], 1)
        self.assertEqual(result['private_objects_opened'], 0)
        self.assertEqual(result['retired_objects'], 1)
        self.assertEqual(result['pending_records'], 0)
        self.assertEqual(before, self.fingerprint())
        resource.refresh_from_db()
        self.assertEqual(resource.private_files, metadata)
        self.assertIsInstance(self.uploads.authenticated_references(user=self.teacher, resource_id=resource.pk), ProtectionError)

    def test_cleaned_feedback_keeps_owner_metadata_and_does_not_restore_download(self):
        ticket = FeedbackTicket.objects.create(client_request_id='b3-feedback-recovery', request_fingerprint='a' * 64,
            submitter=self.other, submitter_role='student', student=self.other, category='content', issue_type='synthetic',
            dispute='合成附件恢复', dedup_key='b' * 64)
        self.client.force_authenticate(self.other)
        base = f'/api/feedback/{ticket.feedback_id}/'
        uploaded = self.client.post(base + 'attachments/', {'visibility': 'student',
            'file': SimpleUploadedFile('synthetic.txt', self.content, content_type='text/plain')},
            format='multipart', HTTP_X_FILE_OPERATION_ID=str(self.operation_id))
        self.assertEqual(uploaded.status_code, 201, uploaded.data)
        attachment = FeedbackAttachment.objects.get()
        metadata = attachment.private_file
        cleaned = self.client.delete(base + f'file-operations/{self.operation_id}/')
        self.assertEqual(cleaned.data['state'], 'cleaned')
        before = self.fingerprint()
        result = self.verifier(self.context)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result['terminal_operations'], 1)
        self.assertEqual(result['retired_objects'], 1)
        self.assertEqual(result['private_objects_opened'], 1)  # Original resource remains live.
        self.assertEqual(before, self.fingerprint())
        attachment.refresh_from_db()
        self.assertEqual(attachment.private_file, metadata)
        self.assertEqual(self.client.get(uploaded.data['download_url']).status_code, 403)

    def test_retired_bytes_without_terminal_operation_do_not_pass_recovery(self):
        operation = PrivateFileOperation.objects.get()
        item = operation.files['resources/file']
        context = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})
        self.assertIs(self.preparation.store.retire_candidate(StoredObject.from_wire(item['stored']), context), True)
        before = self.fingerprint()
        self.assertEqual(self.verifier(self.context).code, ReasonCode.CIPHERTEXT_INVALID)
        self.assertEqual(before, self.fingerprint())

    def test_expired_and_unknown_quota_is_observed_not_released_or_settled(self):
        bucket = QuotaBucket.objects.create(subject_id='user/7', data_domain='ctf', window_key='b3', limit=20,
            active_reserved=4, unknown_reserved=6)
        for state, amount in (('reserved', 4), ('unknown', 6)):
            QuotaReservation.objects.create(bucket=bucket, reservation_id='b3/' + state, amount=amount,
                state=state, request_fingerprint='1' * 64, expires_at=self.components['clock']() - timedelta(hours=1))
        before = self.fingerprint()
        result = self.verifier(self.context)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result['quota']['expired_reserved'], 1)
        self.assertEqual(result['quota']['unknown'], 1)
        self.assertEqual(before, self.fingerprint())

    def test_deleted_legacy_marker_is_not_accepted_as_empty_genesis(self):
        AuditLedgerLock.objects.update_or_create(key='default', defaults={'legacy_archive': {'state': 'deleted'}})
        before = self.fingerprint()
        result = self.verifier(self.context)
        self.assertEqual(result.code, ReasonCode.KEY_UNAVAILABLE)
        self.assertEqual(before, self.fingerprint())
