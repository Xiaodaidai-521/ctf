"""Opt-in full main-schema recovery; synthetic owner, no business download enablement."""
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
import unittest

import psycopg2

from tools.data_security.phase3_backup_cases import BackupFixture


class MainSchemaRecoveryAcceptance(BackupFixture):
    def setUp(self):
        super().setUp()
        os.environ.update(DB_HOST='127.0.0.1', DB_PORT=str(self.database['port']),
                          DB_USER=self.database['user'], DB_NAME=self.source, DB_PASSWORD='', DATA_SECURITY_CONFIG='')
        import django
        django.setup()
        from django.core.management import call_command
        from django.db import connection
        connection.close()
        connection.settings_dict['NAME'] = self.source
        call_command('migrate', interactive=False, verbosity=0)

    def clean_databases(self):
        from django.db import connections
        connections.close_all()
        super().clean_databases()

    def test_main_schema_files_reports_quota_and_explicit_checkpoint_survive_restore(self):
        from django.db import connection, transaction
        from django.utils import timezone
        from audit.models import AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
        from data_security.adapters.keys import FileKeyResolver
        from data_security.adapters.persistence.audit import DjangoAuditSink
        from data_security.adapters.persistence.backup import PostgresAgeBackup
        from data_security.adapters.persistence.models import (
            ExportReport, PolicyVersion, PrivateObject, QuotaExecution, RecoveryPermission,
        )
        from data_security.adapters.persistence.private_store import DjangoPrivateStore
        from data_security.application.audit_gateway import AuditGateway
        from data_security.application.crypto_service import CryptoService
        from data_security.application.reports import ReportAuthenticator
        from data_security.contracts import (
            AuditReceipt, BASELINE_LIMITS, CipherEnvelope, DeliveryReceipt, Durability,
            Environment, KeyPurpose, KeyStatus, ProtectionError, ReportRecord, SecurityEvent, content_hash,
        )
        from data_security.tests.fixtures import examples
        from data_security.tests.phase2_fixtures import reference_key, root_key, text
        from export_quota.models import QuotaBucket, QuotaReservation
        from export_risk.models import ExecutionAuthorizationRecord
        from resources.test_phase6_export_commit import ExportOwnerFixture

        class Owner(ExportOwnerFixture, unittest.TestCase):
            pass

        owner = Owner()
        self.addCleanup(owner.doCleanups)
        owner.setUp()
        checkpoint_root = self.work / 'external-checkpoints'
        checkpoint_root.mkdir(mode=0o700)
        checkpoint_root.chmod(0o700)
        sink = DjangoAuditSink(clock=timezone.now, crypto=owner.crypto, key=reference_key(KeyPurpose.AUDIT),
                               context=owner.context, checkpoint_root=checkpoint_root)
        owner.flow.audit = AuditGateway(sink=sink)
        delivered = owner.flow.execute(owner.plan, owner.binding, owner.owner)
        self.assertIsInstance(delivered, DeliveryReceipt)
        self.assertEqual(delivered.delivered_records, 2)
        candidate = owner.candidate()
        with transaction.atomic():
            envelope = owner.crypto.seal(text('synthetic orphan'), owner.context, owner.key)
            orphan = owner.store.write_candidate(envelope, owner.context)
            transaction.set_rollback(True)
        self.assertTrue(owner.path(orphan).exists())
        self.assertFalse(PrivateObject.objects.filter(object_ref=orphan.object_ref).exists())
        legacy = owner.flow.audit.record(examples()[SecurityEvent], Durability.LEDGER_CONFIRMED)
        self.assertIsInstance(legacy, AuditReceipt)
        legacy_verified = sink.verify('v1')
        self.assertIsInstance(legacy_verified, AuditReceipt)
        self.assertEqual((legacy_verified.entry_ref, legacy_verified.sequence, legacy_verified.entry_hash),
                         (legacy.entry_ref, legacy.sequence, legacy.entry_hash))
        anchored = sink.checkpoint('ds.audit.v2')
        self.assertIsInstance(anchored, AuditReceipt)
        RecoveryPermission.objects.create(authorization_ref='synthetic/recovery-main-schema',
            actor_ref='synthetic/maintainer', binding_hash=content_hash(owner.binding), allow_release=True,
            expires_at=timezone.now() + timedelta(minutes=5))
        record = owner.reports.read(owner.binding)
        self.assertIsInstance(record, ReportRecord)
        models = (ExportReport, PolicyVersion, PrivateObject, QuotaExecution, RecoveryPermission,
                  QuotaBucket, QuotaReservation, ExecutionAuthorizationRecord,
                  AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord)
        checks = tuple(('check/' + model._meta.db_table,
            'SELECT row_to_json(t)::text FROM ' + connection.ops.quote_name(model._meta.db_table) +
            ' t ORDER BY row_to_json(t)::text') for model in models)
        checks += (('check/migrations', 'SELECT app, name FROM django_migrations ORDER BY app, name'),)
        target_files = self.work / 'restored-private'
        target_files.mkdir(mode=0o700)
        required = tuple(replace(reference_key(purpose), status=KeyStatus.READ_ONLY)
                         for purpose in (KeyPurpose.DATA, KeyPurpose.AUDIT))
        offline_root = self.work / 'offline-service'
        offline_root.mkdir(mode=0o700)
        offline_root.chmod(0o700)
        entries = []
        for name, ref, value in [('identity', self.private_ref, self.identity.read_bytes()),
                                *[(key.purpose.value, key, root_key(key.purpose.value)) for key in required]]:
            path = offline_root / name
            path.write_bytes(value)
            path.chmod(0o600)
            entries.append({'reference': ref.to_wire(), 'file': name, 'identities': ['service/backup-offline']})
        manifest = offline_root / 'manifest.json'
        manifest.write_text(json.dumps({'schema_version': 'ds.key-manifest.v1', 'environment': 'test', 'entries': entries}))
        manifest.chmod(0o600)
        resolver = FileKeyResolver(manifest_path=manifest, environment=Environment.TEST, repository_root=self.repo.parent)
        common = dict(directory=self.work, checks=checks, environment=Environment.TEST, domain='domain/backup',
            age=self.tools / 'usr/bin/age', pg_dump=self.repo.parent / '.state/pg-install/bin/pg_dump',
            pg_restore=self.repo.parent / '.state/pg-install/bin/pg_restore', code_version='isolated/phase6-main-schema',
            required_keys=required)
        online = PostgresAgeBackup(resolver=self.online_resolver, service_identity='service/backup-online',
            database=dict(self.database, dbname=self.source), private_root=owner.root, **common)
        offline = PostgresAgeBackup(resolver=resolver, service_identity='service/backup-offline',
            database=dict(self.database, dbname=self.target), private_root=target_files,
            identity_ref=self.private_ref, **common)
        started = perf_counter()
        backup = online.create('snapshot/main-schema', self.public_ref, self.online_context)
        self.assertEqual(backup.version, 'v2')
        created = perf_counter()
        receipt = offline.restore(backup, self.offline_context)
        self.assertIsInstance(receipt, AuditReceipt)
        restored_at = perf_counter()
        self.assertIsNone(receipt.chain_version)
        self.assertEqual(len(list(target_files.iterdir())), 2)
        self.assertFalse((target_files / owner.path(orphan).name).exists())
        # Only the database connection changes; context, selected anchor and keys
        # come from this controlled owner, not from the restored database.
        connection.close()
        connection.settings_dict['NAME'] = self.target
        try:
            self.assertEqual(owner.reports.read(owner.binding), record)
            self.assertEqual(owner.reports.delivery(owner.binding), delivered)
            self.assertEqual(QuotaReservation.objects.get().state, 'committed')
            self.assertEqual((QuotaBucket.objects.get().active_reserved, QuotaBucket.objects.get().settled), (0, 2))
            self.assertEqual(RecoveryPermission.objects.get().binding_hash, content_hash(owner.binding))
            self.assertEqual(PrivateObject.objects.get(object_ref=candidate.object_ref).state, 'candidate')
            crypto = CryptoService(keys=resolver, service_identity='service/backup-offline', random_bytes=os.urandom,
                                   environment=Environment.TEST, limits=BASELINE_LIMITS)
            store = DjangoPrivateStore(root=target_files, crypto=crypto, environment=Environment.TEST)
            sealed = store.read(record.stored, record.context)
            self.assertIsInstance(sealed, CipherEnvelope)
            opened = crypto.open(sealed, record.context, required[0])
            self.assertNotIsInstance(opened, ProtectionError)
            output_hash = hashlib.sha256(opened.binary).hexdigest()
            self.assertEqual(output_hash, record.report.output_hash)
            self.assertIsInstance(store.read(candidate, owner.context), ProtectionError)
            authenticator = ReportAuthenticator(crypto=crypto, key=required[1], executor_ref=owner.auth.executor_ref,
                environment=Environment.TEST, clock=timezone.now)
            self.assertIs(authenticator.verify(record.report, record.proof, owner.binding, owner.plan, record.context,
                input_hash=hashlib.sha256(owner.payload.binary).hexdigest(), output_hash=output_hash,
                ciphertext_hash=record.stored.ciphertext_hash), True)
            restored_sink = DjangoAuditSink(clock=timezone.now, crypto=crypto, key=required[1], context=owner.context,
                checkpoint_root=checkpoint_root, checkpoint_ref=anchored.checkpoint_ref)
            self.assertEqual(restored_sink.verify('ds.audit.v2'), anchored)
            # v1 verification timestamps the ledger row, not outbox persistence.
            self.assertEqual(restored_sink.verify('v1'), legacy_verified)
            anchor_path = checkpoint_root / (anchored.checkpoint_ref.removeprefix('audit/checkpoint/') + '.json')
            anchor = anchor_path.read_bytes()
            anchor_path.write_bytes(anchor[:-1])
            self.assertIsInstance(restored_sink.verify('ds.audit.v2'), ProtectionError)
            anchor_path.write_bytes(anchor)
            # A usable key reference with wrong bytes must fail actual content and
            # chain verification, even though BackupPort itself only resolves keys.
            (offline_root / KeyPurpose.DATA.value).write_bytes(os.urandom(32))
            self.assertIsInstance(crypto.open(sealed, record.context, required[0]), ProtectionError)
            (offline_root / KeyPurpose.AUDIT.value).write_bytes(os.urandom(32))
            self.assertIsInstance(restored_sink.verify('ds.audit.v2'), ProtectionError)
            self.assertEqual(owner.reports.delivery(owner.binding), delivered)
        finally:
            connection.close()
            connection.settings_dict['NAME'] = self.source
        with closing(psycopg2.connect(**dict(self.database, dbname=self.target))) as restored:
            with restored.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
                table_count = cursor.fetchone()[0]
        observation = {'scope': 'full main Django schema, synthetic owner; independent executor not included',
            'restored_public_tables': table_count, 'checked_projections': len(checks), 'private_files': 2,
            'candidate_preserved': True, 'unregistered_orphan_excluded': True,
            'report_quota_and_recovery_permission_verified': True, 'old_and_anchored_new_chain_verified': True,
            'wrong_data_and_audit_bytes_rejected_after_restore': True, 'bad_external_anchor_rejected': True,
            'create_seconds': created - started, 'restore_seconds': restored_at - created,
            'backup_ciphertext_sha256': backup.ciphertext_hash,
            'downloads_enabled': False, 'complete_business_recovery': False}
        with (self.controlled / 'main-schema-recovery-observations.json').open('x') as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(observation, output, indent=2)
            output.write('\n')

    def test_resource_and_feedback_private_references_survive_full_restore_with_retained_keys(self):
        from django.db import connection
        from audit.models import AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
        from ctf_backend.security_bootstrap import assemble_feedback_uploads, assemble_resource_uploads
        from data_security.adapters.keys import FileKeyResolver
        from data_security.adapters.persistence.backup import PostgresAgeBackup
        from data_security.adapters.persistence.models import PrivateObject
        from data_security.contracts import (
            AuditReceipt, CipherEnvelope, ContractViolation, Environment, KeyReference,
            ProtectionError, ReasonCode, StoredObject,
        )
        from feedback_center.models import FeedbackAccessLog, FeedbackAttachment, FeedbackTicket
        from feedback_center.tests.test_phase6_private_uploads import PrivateFeedbackUploadFixture
        from resources.models import Resource
        from resources.test_phase6_private_uploads import PrivateResourceUploadFixture
        from users.models import CTFUser

        class ResourceOwner(PrivateResourceUploadFixture, unittest.TestCase):
            pass

        class FeedbackOwner(PrivateFeedbackUploadFixture, unittest.TestCase):
            pass

        resource, feedback = ResourceOwner(), FeedbackOwner()
        self.addCleanup(resource.doCleanups)
        resource.setUp()
        self.addCleanup(feedback.doCleanups)
        feedback.setUp()
        # Both domains use one explicit private root and the same authenticated audit writer.
        feedback.uploads = assemble_feedback_uploads(config_path=resource.config_path,
            private_root=resource.root, project_ref=feedback.uploads.project_ref)
        feedback.uploads.audit = resource.uploads.audit
        feedback.uploads.read_event = resource.uploads.read_event
        markers = (b'recovery-student@example.invalid', b'192.0.2.73', b'4111111111111111')
        resource.content = b'resource ' + b' '.join(markers)
        feedback.content = b'feedback ' + b' '.join(markers)
        self.assertEqual(resource.post(data=resource.data(cover=True)).status_code, 201)
        self.assertEqual(feedback.post().status_code, 201)
        uploaded = Resource.objects.get()
        attachment = FeedbackAttachment.objects.get()
        expected = {}
        for field, payload in (('file', resource.content), ('cover_image', resource.cover_bytes)):
            stored, _ = resource.stored_context(uploaded, field)
            expected[stored.object_ref] = hashlib.sha256(payload).hexdigest()
        feedback_stored = StoredObject.from_wire(attachment.private_file['stored'])
        expected[feedback_stored.object_ref] = hashlib.sha256(feedback.content).hexdigest()
        self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 3)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
        anchor = resource.uploads.audit.sink.checkpoint('ds.audit.v2')
        self.assertIsInstance(anchor, AuditReceipt)
        source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in resource.root.iterdir()}
        self.assertEqual(len(source_hashes), 3)
        models = (Resource, FeedbackTicket, FeedbackAttachment, FeedbackAccessLog, CTFUser,
                  PrivateObject, AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord)
        checks = self.checks + tuple(('check/' + model._meta.db_table,
            'SELECT row_to_json(t)::text FROM ' + connection.ops.quote_name(model._meta.db_table) +
            ' t ORDER BY row_to_json(t)::text') for model in models)
        checks += (('check/migrations', 'SELECT app, name FROM django_migrations ORDER BY app, name'),)
        target_files = self.work / 'restored-upload-files'
        target_files.mkdir(mode=0o700)
        offline_root = self.work / 'retained-upload-configuration'
        offline_root.mkdir(mode=0o700)
        offline_root.chmod(0o700)
        # Retain keys, policy and the selected external checkpoint separately from the backup database.
        manifest = json.loads(Path(resource.config['key_manifest']).read_text())
        for entry in manifest['entries']:
            path = offline_root / entry['file']
            path.write_bytes((resource.config_path.parent / entry['file']).read_bytes())
            path.chmod(0o600)
            entry['identities'].append('service/backup-offline')
        identity = offline_root / 'backup-identity'
        identity.write_bytes(self.identity.read_bytes())
        identity.chmod(0o600)
        manifest['entries'].append({'reference': self.private_ref.to_wire(), 'file': identity.name,
                                    'identities': ['service/backup-offline']})
        manifest_path = offline_root / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest))
        manifest_path.chmod(0o600)
        policy = offline_root / 'approved-policy.json'
        policy.write_bytes(Path(resource.config['policy_file']).read_bytes())
        policy.chmod(0o600)
        checkpoints = offline_root / 'checkpoints'
        checkpoints.mkdir(mode=0o700)
        anchor_name = anchor.checkpoint_ref.removeprefix('audit/checkpoint/') + '.json'
        retained_anchor = checkpoints / anchor_name
        retained_anchor.write_bytes((Path(resource.config['audit_chain']['checkpoint_root']) / anchor_name).read_bytes())
        retained_anchor.chmod(0o600)
        restored_config = dict(resource.config, key_manifest=str(manifest_path), policy_file=str(policy),
            audit_chain=dict(resource.config['audit_chain'], checkpoint_root=str(checkpoints),
                             checkpoint_ref=anchor.checkpoint_ref))
        config_path = offline_root / 'bootstrap.json'
        config_path.write_text(json.dumps(restored_config))
        config_path.chmod(0o600)
        required = tuple(KeyReference.from_wire(resource.config[name])
                         for name in ('framework_key', 'data_key', 'audit_key'))
        resolver = FileKeyResolver(manifest_path=manifest_path, environment=Environment.EVALUATION,
                                   repository_root=self.repo.parent)
        common = dict(directory=self.work, checks=checks, environment=Environment.TEST, domain='domain/backup',
            age=self.tools / 'usr/bin/age', pg_dump=self.repo.parent / '.state/pg-install/bin/pg_dump',
            pg_restore=self.repo.parent / '.state/pg-install/bin/pg_restore',
            code_version='isolated/phase6-upload-recovery', required_keys=required)
        online = PostgresAgeBackup(resolver=self.online_resolver, service_identity='service/backup-online',
            database=dict(self.database, dbname=self.source), private_root=resource.root, **common)
        offline = PostgresAgeBackup(resolver=resolver, service_identity='service/backup-offline',
            database=dict(self.database, dbname=self.target), private_root=target_files,
            identity_ref=self.private_ref, **common)
        started = perf_counter()
        backup = online.create('snapshot/resource-feedback', self.public_ref, self.online_context)
        self.assertIsInstance(backup, StoredObject)
        self.assertEqual(backup.version, 'v2')
        created = perf_counter()
        receipt = offline.restore(backup, self.offline_context)
        restored_at = perf_counter()
        self.assertIsInstance(receipt, AuditReceipt)
        self.assertIsNone(receipt.chain_version)
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in target_files.iterdir()},
                         source_hashes)
        for path in (*target_files.iterdir(), *self.work.glob('*.age')):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for marker in markers:
                self.assertNotIn(marker, path.read_bytes())
        connection.close()
        connection.settings_dict['NAME'] = self.target
        try:
            restored_resource = assemble_resource_uploads(config_path=config_path,
                private_root=target_files, project_ref=resource.uploads.project_ref)
            restored_feedback = assemble_feedback_uploads(config_path=config_path,
                private_root=target_files, project_ref=feedback.uploads.project_ref)
            restored_feedback.audit = restored_resource.audit
            restored_feedback.read_event = restored_resource.read_event
            self.assertEqual(restored_resource.audit.sink.verify('ds.audit.v2'), anchor)
            resource_refs = restored_resource.reconcile(user=resource.teacher, resource_id=uploaded.pk)
            feedback_ref = restored_feedback.reconcile(user=feedback.student,
                ticket_id=feedback.ticket.pk, attachment_id=attachment.attachment_id)
            self.assertIsInstance(resource_refs, tuple)
            self.assertIsInstance(feedback_ref, tuple)
            self.assertEqual((len(resource_refs), len(feedback_ref)), (2, 2))
            references = [(context, stored) for _, context, stored in resource_refs] + [feedback_ref]
            preparation = restored_resource.prepare.__self__
            for context, stored in references:
                self.assertEqual(stored.state, 'verified')
                self.assertEqual(preparation.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)
                path = target_files / (stored.object_ref.removeprefix('private/') + '.sealed')
                envelope = CipherEnvelope.from_json(path.read_bytes())
                opened = preparation.crypto.open(envelope, context, envelope.key)
                self.assertNotIsInstance(opened, ProtectionError)
                self.assertEqual(hashlib.sha256(opened.binary).hexdigest(), expected[stored.object_ref])
            restored = Resource.objects.get(pk=uploaded.pk)
            self.assertEqual((restored.file.name, restored.cover_image.name, restored.status), ('', '', 'pending'))
            self.assertEqual(FeedbackAttachment.objects.get().file.name, '')
            CTFUser.objects.filter(pk__in=(resource.teacher.pk, feedback.student.pk)).update(is_active=False)
            self.assertEqual(restored_resource.reconcile(user=resource.teacher,
                resource_id=uploaded.pk).code, ReasonCode.AUTHORIZATION_DENIED)
            self.assertEqual(restored_feedback.reconcile(user=feedback.student, ticket_id=feedback.ticket.pk,
                attachment_id=attachment.attachment_id).code, ReasonCode.AUTHORIZATION_DENIED)
            CTFUser.objects.filter(pk__in=(resource.teacher.pk, feedback.student.pk)).update(is_active=True)
            self.assertEqual(restored_feedback.reconcile(user=feedback.other, ticket_id=feedback.ticket.pk,
                attachment_id=attachment.attachment_id).code, ReasonCode.AUTHORIZATION_DENIED)
            Resource.objects.filter(pk=uploaded.pk).update(private_files={})
            self.assertIsInstance(restored_resource.reconcile(user=resource.teacher,
                resource_id=uploaded.pk), ProtectionError)
            Resource.objects.filter(pk=uploaded.pk).update(private_files=uploaded.private_files)
            FeedbackAttachment.objects.filter(pk=attachment.pk).update(sha256='0' * 64)
            self.assertIsInstance(restored_feedback.reconcile(user=feedback.student, ticket_id=feedback.ticket.pk,
                attachment_id=attachment.attachment_id), ProtectionError)
            FeedbackAttachment.objects.filter(pk=attachment.pk).update(sha256=attachment.sha256)
            data_path = offline_root / 'data_key.key'
            data_key = data_path.read_bytes()
            data_path.write_bytes(os.urandom(32))
            self.assertIsInstance(preparation.crypto.open(envelope, context, envelope.key), ProtectionError)
            data_path.write_bytes(data_key)
            audit_path = offline_root / 'audit_key.key'
            audit_key = audit_path.read_bytes()
            audit_path.write_bytes(os.urandom(32))
            with self.assertRaises(ContractViolation):
                assemble_resource_uploads(config_path=config_path,
                    private_root=target_files, project_ref=resource.uploads.project_ref)
            self.assertIsInstance(restored_feedback.reconcile(user=feedback.student, ticket_id=feedback.ticket.pk,
                attachment_id=attachment.attachment_id), ProtectionError)
            audit_path.write_bytes(audit_key)
            self.assertEqual(restored_resource.audit.sink.verify('ds.audit.v2'), anchor)
            self.assertEqual(AuthenticatedAuditEntry.objects.count(), 3)
            self.assertEqual(PrivateObject.objects.filter(state='verified').count(), 3)
            self.assertEqual((Resource.objects.count(), FeedbackAttachment.objects.count()), (1, 1))
        finally:
            connection.close()
            connection.settings_dict['NAME'] = self.source
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in resource.root.iterdir()},
                         source_hashes)
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in target_files.iterdir()},
                         source_hashes)
        self.assertTrue(CTFUser.objects.get(pk=resource.teacher.pk).is_active)
        self.assertEqual(Resource.objects.get().private_files, uploaded.private_files)
        self.assertEqual(FeedbackAttachment.objects.get().sha256, attachment.sha256)
        self.assertEqual(list(resource.media.iterdir()), [])
        self.assertEqual(list(feedback.media.iterdir()), [])
        with closing(psycopg2.connect(**dict(self.database, dbname=self.target))) as restored:
            with restored.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
                table_count = cursor.fetchone()[0]
        observation = {'scope': 'Resource original/cover and feedback attachment through real owners, full main-schema restore',
            'restored_public_tables': table_count, 'checked_projections': len(checks), 'private_files': 3,
            'resource_rows': 1, 'feedback_attachments': 1, 'new_chain_events': 3,
            'authenticated_owner_references_verified': True, 'all_private_states': 'verified',
            'data_plaintext_hashes_match': True, 'retained_external_checkpoint_verified': True,
            'retained_key_status': 'active original references for explicit B; no rotation claim',
            'current_permissions_and_tampered_metadata_rejected': True,
            'wrong_retained_data_and_audit_bytes_rejected': True, 'source_rows_and_ciphertexts_preserved': True,
            'persistent_marker_hits': 0, 'public_media_files': 0,
            'create_seconds': created - started, 'restore_seconds': restored_at - created,
            'backup_ciphertext_sha256': backup.ciphertext_hash, 'downloads_enabled': False,
            'complete_business_recovery': False, 'periodic_rpo_rto_verified': False}
        with (self.controlled / 'upload-owner-recovery-observations.json').open('x') as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(observation, output, indent=2)
            output.write('\n')
