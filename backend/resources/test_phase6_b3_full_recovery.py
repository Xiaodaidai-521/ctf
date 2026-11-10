"""Opt-in complete-schema PG/age drill with real owners and wall-clock RPO/RTO.

Dispatch to a sealed independent test tree. This is one isolated deployment, not
production capacity evidence or a substitute for the B5 all-owner matrix.
"""
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
from unittest.mock import patch
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TransactionTestCase

from ctf_backend.security_bootstrap import _FIELD_OWNERS, assemble, assemble_field_backfill, assemble_recovery
from data_security.adapters.persistence.fields import bind_field_storage
from data_security.adapters.persistence.recovery_state import recovery_admission
from data_security.contracts import (
    BASELINE_LIMITS, AuditReceipt, Environment, KeyPurpose, KeyReference, KeyStatus, ProtectionContext,
    ProtectionError, Purpose, ReasonCode, StoredObject,
)
from data_security.tests.fixtures import examples
from export_quota.models import QuotaBucket, QuotaReservation
from feedback_center.models import FeedbackTicket
from resources.models import Resource
from .test_phase6_formal_fixtures import FormalResourceFixture


class CompleteBackendRecoveryTests(FormalResourceFixture, TransactionTestCase):
    install_delivery_policy = True

    def setUp(self):
        if os.environ.get('DS_B3_FULL_RECOVERY_RUN') != '1':
            raise RuntimeError('EXPLICIT_ISOLATED_B3_FULL_RECOVERY_REQUIRED')
        self.repo = Path(__file__).resolve().parents[2]
        cluster = json.loads((self.repo / '.state/postgres.json').read_text())
        self.assertTrue(cluster['synthetic_only'])
        self.assertEqual(cluster['socket'], str(self.repo / '.state/pg-run'))
        self.assertEqual(str(connection.settings_dict['PORT']), str(cluster['port']))
        self.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
        self.admin = {'host': cluster['socket'], 'port': cluster['port'], 'user': cluster['user'], 'dbname': 'postgres'}
        super().setUp()
        self.addCleanup(bind_field_storage, None)
        self.saved_database = dict(connection.settings_dict)
        self.addCleanup(self.restore_connection)
        self.directory = self.config_path.parent / 'backups'
        self.directory.mkdir(mode=0o700)
        self.offline_keys = self.config_path.parent / 'offline'
        self.offline_keys.mkdir(mode=0o700)
        self.targets = []
        self.addCleanup(self.clean_targets)
        self.tools = Path(os.environ['DS_PHASE3_TOOLS'])
        self.public = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='backup-recipient/v1',
            purpose=KeyPurpose.BACKUP_PUBLIC, version='v1', status=KeyStatus.ACTIVE)
        self.identity = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='backup-identity/v1',
            purpose=KeyPurpose.BACKUP_PRIVATE, version='v1', status=KeyStatus.READ_ONLY)
        identity_file = self.offline_keys / 'identity'
        subprocess.run([str(self.tools / 'usr/bin/age-keygen'), '-o', str(identity_file)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        identity_file.write_bytes(next(line for line in identity_file.read_bytes().splitlines() if line.startswith(b'AGE-')) + b'\n')
        identity_file.chmod(0o600)
        recipient_file = self.config_path.parent / 'recipient'
        with recipient_file.open('wb') as target:
            subprocess.run([str(self.tools / 'usr/bin/age-keygen'), '-y', str(identity_file)],
                stdout=target, stderr=subprocess.DEVNULL, check=True)
        recipient_file.chmod(0o600)
        self.index = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='query-index/v1',
            purpose=KeyPurpose.INDEX, version='v1', status=KeyStatus.ACTIVE)
        index_file = self.config_path.parent / 'index.key'
        index_file.write_bytes(secrets.token_bytes(32))
        index_file.chmod(0o600)
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        for ref, path in ((self.public, recipient_file), (self.index, index_file)):
            manifest['entries'].append({'reference': ref.to_wire(), 'file': path.name, 'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))
        offline_manifest = deepcopy(manifest)
        for entry in offline_manifest['entries']:
            target = self.offline_keys / entry['file']
            target.write_bytes((manifest_path.parent / entry['file']).read_bytes())
            target.chmod(0o600)
        offline_manifest['entries'].append({'reference': self.identity.to_wire(), 'file': identity_file.name,
            'identities': ['service/security']})
        self.offline_manifest = self.offline_keys / 'manifest.json'
        self.offline_manifest.write_text(json.dumps(offline_manifest))
        self.offline_manifest.chmod(0o600)
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', domain='ctf',
            environment=Environment.EVALUATION, purpose=Purpose.STORAGE)

        source_ref, permission_ref, _, _ = self.ready()
        self.ok(self.entry.execute(user=self.teacher, source_ref=source_ref, permission_ref=permission_ref))
        self.config['private_files'] = {name: self.config['export_delivery'][name] for name in ('private_root', 'project_ref')}
        self.write_config()
        components = assemble(config_path=self.config_path)
        ticket = FeedbackTicket.objects.create(client_request_id='b3-complete', request_fingerprint='a' * 64,
            submitter=self.teacher, submitter_role='teacher', student=self.teacher, category='content',
            issue_type='synthetic', dispute='合成恢复附件', dedup_key='b' * 64)
        self.ok(components['private_uploads']['feedback'].create({'visibility': 'student',
            'file': SimpleUploadedFile('synthetic.txt', b'complete-recovery-attachment', content_type='text/plain')},
            user=self.teacher, ticket_id=ticket.pk, operation_id=uuid4()))
        shares = components['file_shares']
        # Expired sharing is seeded through the real owner with an earlier real timestamp.
        with patch.object(shares, 'clock', return_value=datetime.now(timezone.utc) - timedelta(days=2)):
            self.ok(shares.create(user=self.teacher, operation_id=uuid4(), domain='resources', object_id=Resource.objects.first().pk))
        bucket = QuotaBucket.objects.create(subject_id='user/b3-extra', data_domain='ctf', window_key='b3',
            limit=20, active_reserved=4, unknown_reserved=6)
        for state, amount in (('reserved', 4), ('unknown', 6)):
            QuotaReservation.objects.create(bucket=bucket, reservation_id='b3/' + state, amount=amount, state=state,
                request_fingerprint='a' * 64, expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        self.teacher.email = 'synthetic@example.invalid'
        self.teacher.save(update_fields=['email'])
        pending = self.root / ('f' * 64 + '.sealed')
        pending.write_bytes(b'opaque incomplete ciphertext')
        pending.chmod(0o600)

        # Real preflight restoration backs the original field-migration gate, not a synthetic success flag.
        quote = connection.ops.quote_name
        checks = []
        for label in _FIELD_OWNERS:
            model = apps.get_model(label)
            names = ('id', 'security_uuid', 'security_revision', *model.encrypted_fields,
                     *model.redacted_fields, *model.minimized_fields)
            checks.append(('fields/' + model._meta.label_lower, 'SELECT ' + ', '.join(quote(name) + '::text' for name in names)
                + ' FROM ' + quote(model._meta.db_table) + " WHERE security_state = 'legacy-v0' ORDER BY id"))
        self.config['backup'] = {'database': {'host': '127.0.0.1', 'port': cluster['port'], 'user': cluster['user'],
            'dbname': self.saved_database['NAME']}, 'directory': str(self.directory), 'checks': checks,
            'age': str(self.tools / 'usr/bin/age'), 'pg_dump': str(self.repo / '.state/pg-install/bin/pg_dump'),
            'pg_restore': str(self.repo / '.state/pg-install/bin/pg_restore'), 'private_root': str(self.root),
            'code_version': 'isolated/b3-complete', 'required_keys': [self.config['data_key'], self.config['audit_key']],
            'full_inventory': True}
        self.write_config()
        online = assemble(config_path=self.config_path)['backup']
        preflight_backup = self.ok(online.create('snapshot/b3-field-preflight', self.public, self.context))
        preflight, _ = self.new_target('preflight')
        self.ok(preflight.run('close', self.context))
        receipt = self.ok(preflight.run('restore', self.context, backup=preflight_backup))
        restoration = self.ok(preflight.backups.read_restoration(receipt, self.context))
        proof = self.config_path.parent / 'field-recovery.json'
        proof.write_text(json.dumps({'returncode': 0, 'key_material_in_evidence': False,
            'recovery_observations': {'receipt_durability': receipt.durability.value, 'checks': restoration['checks']}}))
        proof.chmod(0o600)
        self.config['field_storage'] = {'index_keys': [self.index.to_wire()], 'read_keys': [], 'legacy_reads': False,
            'recovery_record': {'path': str(proof), 'sha256': hashlib.sha256(proof.read_bytes()).hexdigest()}}
        self.write_config()
        backfill = assemble_field_backfill(config_path=self.config_path)
        checkpoint = self.config_path.parent / 'field-backfill.json'
        backfill.prepare(checkpoint=checkpoint, recovery=restoration)
        migrated = backfill.run(checkpoint=checkpoint, limit=1000)
        self.assertEqual((migrated['failed'], migrated['unprocessed']), (0, 0))
        components = assemble(config_path=self.config_path)
        selected = self.ok(components['audit'].sink.checkpoint('ds.audit.v2'))
        self.config['audit_chain']['checkpoint_ref'] = selected.checkpoint_ref
        self.config['backup']['required_keys'].append(self.index.to_wire())
        self.write_config()
        self.online = assemble(config_path=self.config_path)['backup']
        self.backup = self.ok(self.online.create('snapshot/b3-complete', self.public, self.context, cadence='daily'))
        self.flow, self.target_config = self.new_target('final')
        self.run_ref = self.ok(self.flow.run('close', self.context))

    def new_target(self, label):
        name = 'b3_recovery_' + uuid4().hex[:12]
        with closing(psycopg2.connect(**self.admin)) as database:
            database.autocommit = True
            with database.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        self.targets.append(name)
        root = self.config_path.parent / ('target-' + label)
        root.mkdir(mode=0o700)
        config = deepcopy(self.config)
        config['backup']['database']['dbname'] = name
        config['key_manifest'] = str(self.offline_manifest)
        for options in (config['backup'], config['private_files'], config['export_delivery']):
            options['private_root'] = str(root)
        path = self.config_path.parent / ('target-' + label + '.json')
        path.write_text(json.dumps(config))
        path.chmod(0o600)
        return assemble_recovery(config_path=path, identity=self.identity), path

    def restore_connection(self):
        connection.close()
        connection.settings_dict.update(self.saved_database)

    def clean_targets(self):
        self.restore_connection()
        with closing(psycopg2.connect(**self.admin)) as database:
            database.autocommit = True
            with database.cursor() as cursor:
                for name in self.targets:
                    self.assertRegex(name, r'^b3_recovery_[0-9a-f]{12}$')
                    cursor.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))

    def restore_target(self):
        self.assertIsInstance(self.flow.run('restore', self.context, backup=self.backup), AuditReceipt)
        connection.close()
        database = self.flow.backups.database
        connection.settings_dict.update(NAME=database['dbname'], HOST=database['host'], PORT=database['port'])

    def test_complete_schema_real_owners_and_explicit_open_record_actual_rpo_rto(self):
        self.restore_target()
        before = self.ok(self.flow.backups.source_inventory(self.context))
        receipt = self.ok(self.flow.run('verify', self.context))
        self.assertIsInstance(receipt, AuditReceipt)
        state = self.flow.journal.read(self.context)
        verified = state['verification']
        self.assertTrue(verified['complete'] and verified['opening_allowed'])
        self.assertGreater(verified['private_objects_opened'], 2)
        self.assertGreater(verified['encrypted_fields_opened'], 0)
        self.assertEqual(verified['reports_authenticated'], 1)
        self.assertEqual(verified['logical_delivery_receipts'], 1)
        self.assertEqual(verified['quota']['unknown'], 1)
        self.assertEqual(verified['quota']['expired_reserved'], 1)
        self.assertEqual(verified['shares']['expired'], 1)
        self.assertEqual(state['restoration']['full_inventory']['pending_files']['records'], 1)
        self.assertEqual(recovery_admission(self.flow.backups.private_root, self.flow.backups.source_identity,
            limits=BASELINE_LIMITS).code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.flow.run('open', self.context, approved_run_ref='recovery/wrong').code,
            ReasonCode.AUTHORIZATION_DENIED)
        self.assertIsInstance(self.flow.run('open', self.context, approved_run_ref=self.run_ref), AuditReceipt)
        opened = self.flow.journal.read(self.context)
        self.assertEqual(opened['state'], 'opened')
        metrics = opened['metrics']
        self.assertTrue(metrics['passed'])
        self.assertLessEqual(metrics['rpo_seconds'], 86400)
        self.assertLessEqual(metrics['rto_seconds'], 14400)
        self.assertAlmostEqual(metrics['rto_seconds'], sum(metrics[name] for name in (
            'outage_to_restore_seconds', 'restore_seconds', 'verification_seconds', 'review_and_open_seconds')))
        self.assertEqual(before, self.flow.backups.source_inventory(self.context))
        self.assertTrue(recovery_admission(self.flow.backups.private_root, self.flow.backups.source_identity,
            limits=BASELINE_LIMITS))
        # Only timings and counts leave the controlled fixture; no plaintext, keys or source rows.
        output = Path(os.environ['DS_B3_RECOVERY_EVIDENCE'])
        self.assertTrue(output.is_absolute() and not output.exists())
        with output.open('x') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({'scope': 'isolated-complete-schema', 'metrics': metrics,
                'tables': len(before['schema']), 'private_objects': verified['private_objects_opened'],
                'reports': verified['reports_authenticated'], 'network_delivery_confirmed': False}, stream, sort_keys=True)

    def test_changed_restored_table_blocks_open_and_retains_verified_evidence(self):
        self.restore_target()
        self.ok(self.flow.run('verify', self.context))
        journal = (self.flow.backups.private_root / '.restore-state.json').read_bytes()
        QuotaBucket.objects.filter(window_key='b3').update(limit=21)
        self.assertEqual(self.flow.run('open', self.context, approved_run_ref=self.run_ref).code, ReasonCode.REPORT_MISMATCH)
        self.assertEqual((self.flow.backups.private_root / '.restore-state.json').read_bytes(), journal)

    def test_missing_selected_checkpoint_cannot_be_replaced_by_recovery(self):
        self.restore_target()
        config = json.loads(self.target_config.read_bytes())
        config['audit_chain']['checkpoint_ref'] = 'audit/checkpoint/' + 'f' * 64
        self.target_config.write_text(json.dumps(config))
        result = self.flow.run('verify', self.context)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(self.flow.journal.read(self.context)['state'], 'restored')
        self.assertIsInstance(recovery_admission(self.flow.backups.private_root, self.flow.backups.source_identity,
            limits=BASELINE_LIMITS), ProtectionError)
