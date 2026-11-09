"""Owner-field key/index rotation with real isolated PostgreSQL and M5 files."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
from unittest.mock import Mock, patch

from django.db import connection
from django.test import TestCase

from ai_assistant.models import AIConversation, AIMessage
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.field_rotation import FieldRotation
from data_security.adapters.persistence.fields import bind_field_storage, ProtectedQuerySet
from data_security.contracts import ContractViolation, KeyPurpose, KeyReference, KeyStatus, ProtectionError
from data_security.tests.phase4_fixtures import field_configuration
from users.models import CTFUser


class FieldRotationTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        fixture = field_configuration()
        self.path, self.config, self.refs, binding = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.components = assemble(config_path=self.path)
        bind_field_storage(self.components['fields'])
        self.addCleanup(bind_field_storage, None)
        self.user = CTFUser.objects.create_user(username='rotation-owner', email='Before@example.invalid',
                                              password='synthetic-rotation-passphrase')
        conversation = AIConversation.objects.create(user=self.user)
        self.message = AIMessage.objects.create(conversation=conversation, role='user',
            content='Message@example.invalid', metadata={'note': 'Nested@example.invalid', 'count': 7})

    def configure_rotation(self):
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        old_data = replace(self.refs['data_key'], status=KeyStatus.READ_ONLY)
        for entry in manifest['entries']:
            if entry['reference']['key_ref'] == old_data.key_ref:
                entry['reference'] = old_data.to_wire()
        new_data = replace(self.refs['data_key'], key_ref='enc-data/v2', version='v2')
        new_index = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='query-index/v2',
                                version='v2', purpose=KeyPurpose.INDEX, status=KeyStatus.ACTIVE)
        for reference, filename in ((new_data, 'data-v2.key'), (new_index, 'index-v2.key')):
            key_file = self.path.parent / filename
            key_file.write_bytes(secrets.token_bytes(32))
            key_file.chmod(0o600)
            manifest['entries'].append({'reference': reference.to_wire(), 'file': filename,
                                        'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))
        self.config['data_key'] = new_data.to_wire()
        options = self.config['field_storage']
        options['read_keys'] = [old_data.to_wire()]
        options['index_keys'].insert(0, new_index.to_wire())
        options['index_deadline'] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.path.write_text(json.dumps(self.config))
        self.components = assemble(config_path=self.path)
        bind_field_storage(self.components['fields'])
        return FieldRotation(models=(CTFUser, AIMessage), storage=self.components['fields'])

    def final_configuration(self):
        options = self.config['field_storage']
        options['read_keys'] = []
        options['index_keys'] = options['index_keys'][:1]
        options.pop('index_deadline', None)
        self.path.write_text(json.dumps(self.config))
        self.components = assemble(config_path=self.path)
        bind_field_storage(self.components['fields'])
        return FieldRotation(models=(CTFUser, AIMessage), storage=self.components['fields'])

    def test_new_writes_old_readonly_reads_and_root_transition(self):
        rotation = self.configure_rotation()
        self.assertEqual(self.user.read_protected('email'), 'Before@example.invalid')
        self.assertEqual(self.message.read_protected('metadata')['count'], 7)
        new_user = CTFUser.objects.create_user(username='rotation-new', email='New@example.invalid')
        self.assertEqual(new_user.security_envelopes['email']['envelope']['key']['version'], 'v2')
        self.assertEqual(self.user.security_envelopes['email']['envelope']['key']['version'], 'v1')
        self.config['data_key'] = self.config['field_storage']['read_keys'][0]
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path)
        self.assertFalse(rotation.run()['stopped'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.security_envelopes['email']['envelope']['key']['version'], 'v2')
        self.assertTrue(self.user.check_password('synthetic-rotation-passphrase'))
        self.assertNotIn('password', self.user.security_envelopes)

    def test_partial_restart_is_idempotent_and_preserves_values(self):
        rotation = self.configure_rotation()
        self.assertEqual(rotation.run(limit=1)['rotated'], 1)
        self.user.refresh_from_db()
        first = deepcopy(self.user.security_envelopes)
        self.components = assemble(config_path=self.path)
        bind_field_storage(self.components['fields'])
        rotation = FieldRotation(models=(CTFUser, AIMessage), storage=self.components['fields'])
        self.assertEqual(rotation.run(limit=1)['rotated'], 1)
        self.user.refresh_from_db()
        self.message.refresh_from_db()
        self.assertEqual(self.user.security_envelopes, first)
        self.assertEqual(self.message.read_protected('content'), 'Message@example.invalid')
        self.assertEqual(self.message.read_protected('metadata'), {'note': 'Nested@example.invalid', 'count': 7})
        self.assertEqual(rotation.run()['rotated'], 0)
        with self.assertRaises(ContractViolation):
            rotation.finish()

    def test_dual_lookup_backfill_and_single_version_online_exit(self):
        old_envelope = deepcopy(self.user.security_envelopes)
        rotation = self.configure_rotation()
        self.assertEqual(list(CTFUser.objects.exact_email('Before@EXAMPLE.INVALID')), [self.user])
        self.assertEqual(rotation.run()['rotated'], 2)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_index.startswith('v2:'))
        self.assertTrue(self.user.email_index_previous.startswith('v1:'))
        rotation = self.final_configuration()
        self.assertEqual(rotation.run()['rotated'], 1)
        result = rotation.finish()
        self.assertEqual(result['verified_rows'], 2)
        self.assertEqual((result['old_read_refs'], result['old_indexes']), (0, 0))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email_index_previous, '')
        self.assertEqual(list(CTFUser.objects.exact_email('Before@example.invalid')), [self.user])
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        obsolete = [entry for entry in manifest['entries'] if entry['reference']['key_ref'] in ('enc-data/v1', 'query-index/v1')]
        manifest['entries'] = [entry for entry in manifest['entries'] if entry not in obsolete]
        manifest_path.write_text(json.dumps(manifest))
        for entry in obsolete:
            (manifest_path.parent / entry['file']).unlink()
        self.assertEqual(self.user.read_protected('email'), 'Before@example.invalid')
        self.user.security_envelopes = old_envelope
        with self.assertRaises(ContractViolation):
            self.user.read_protected('email')

    def test_stale_revision_never_overwrites_new_business_value(self):
        rotation = self.configure_rotation()
        old_revision = self.user.security_revision
        self.user.email = 'Concurrent@example.invalid'
        self.user.save(update_fields=['email'])
        rows = Mock()
        rows.iterator.return_value = iter([(self.user.pk, old_revision)])
        with patch.object(ProtectedQuerySet, 'values_list', return_value=rows):
            result = rotation.run()
        self.assertTrue(result['stopped'])
        self.assertEqual(result['rotated'], 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.read_protected('email'), 'Concurrent@example.invalid')
        self.assertFalse(rotation.run()['stopped'])

    def test_missing_new_key_refuses_startup_and_stops_without_overwrite(self):
        rotation = self.configure_rotation()
        before = deepcopy(self.user.security_envelopes)
        (self.path.parent / 'data-v2.key').unlink()
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path)
        result = rotation.run()
        self.assertTrue(result['stopped'])
        self.assertEqual(result['rotated'], 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.security_envelopes, before)
        self.assertEqual(self.user.read_protected('email'), 'Before@example.invalid')

    def test_configuration_recovery_preserves_formats_and_refuses_unbound_rollback(self):
        rotation = self.configure_rotation()
        self.assertEqual(rotation.run(limit=1)['rotated'], 1)
        self.user.refresh_from_db()
        before = deepcopy(self.user.security_envelopes)
        revision = self.user.security_revision
        key_file = self.path.parent / 'data-v2.key'
        material = key_file.read_bytes()
        key_file.unlink()
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path)
        self.user.email = 'Stopped@example.invalid'
        with self.assertRaisesRegex(RuntimeError, 'KEY_UNAVAILABLE'):
            self.user.save(update_fields=['email'])
        self.user.refresh_from_db()
        self.assertEqual((self.user.security_revision, self.user.security_envelopes), (revision, before))
        self.assertEqual(self.user.email, '')
        bind_field_storage(None)
        with self.assertRaises(ContractViolation):
            self.user.read_protected('email')
        with self.assertRaises(ContractViolation):
            self.user.save(update_fields=['nickname'])
        # Restore only this fixture's same approved key, not an old key version or plaintext.
        key_file.write_bytes(material)
        key_file.chmod(0o600)
        self.components = assemble(config_path=self.path)
        bind_field_storage(self.components['fields'])
        self.assertEqual(self.user.read_protected('email'), 'Before@example.invalid')
        self.assertEqual(self.message.read_protected('content'), 'Message@example.invalid')
        self.assertEqual(self.user.security_envelopes, before)
        self.assertEqual(self.user.security_envelopes['email']['envelope']['key']['version'], 'v2')
        self.assertEqual(self.message.security_envelopes['content']['envelope']['key']['version'], 'v1')
        self.assertTrue(self.user.check_password('synthetic-rotation-passphrase'))

    def test_expired_dual_index_stops_queries_writes_and_backfill(self):
        rotation = self.configure_rotation()
        self.components['fields'].index_deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        with self.assertRaises(ContractViolation):
            CTFUser.objects.exact_email('Before@example.invalid')
        with self.assertRaises(ContractViolation):
            CTFUser.objects.create_user(username='expired-index', email='After@example.invalid')
        self.assertTrue(rotation.run()['stopped'])
        self.config['field_storage'].pop('index_deadline')
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path)

    def test_bad_ciphertext_stops_and_does_not_fall_back_or_reseal(self):
        rotation = self.configure_rotation()
        damaged = deepcopy(self.user.security_envelopes)
        damaged['email']['envelope']['ciphertext'] = 'invalid-ciphertext'
        with connection.cursor() as cursor:
            cursor.execute('UPDATE users_ctfuser SET security_envelopes=%s WHERE id=%s',
                           [json.dumps(damaged), self.user.pk])
        result = rotation.run()
        self.assertTrue(result['stopped'])
        self.assertEqual(result['rotated'], 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.security_envelopes, damaged)
        self.assertEqual(self.user.email, '')
        with self.assertRaises((ContractViolation, RuntimeError)):
            self.user.read_protected('email')

    def test_manifest_revocation_wins_over_database_envelope_display_status(self):
        rotation = self.configure_rotation()
        self.assertFalse(rotation.run()['stopped'])
        self.user.refresh_from_db()
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        for entry in manifest['entries']:
            if entry['reference']['key_ref'] == 'enc-data/v2':
                entry['reference']['status'] = KeyStatus.RETIRED.value
        manifest_path.write_text(json.dumps(manifest))
        display = deepcopy(self.user.security_envelopes)
        display['email']['envelope']['key']['status'] = KeyStatus.ACTIVE.value
        with connection.cursor() as cursor:
            cursor.execute('UPDATE users_ctfuser SET security_envelopes=%s WHERE id=%s',
                           [json.dumps(display), self.user.pk])
        self.user.refresh_from_db()
        with self.assertRaisesRegex(RuntimeError, 'KEY_UNAVAILABLE'):
            self.user.read_protected('email')
        self.assertTrue(rotation.run()['stopped'])

    def test_link_pseudonym_and_wrong_purpose_stay_disabled(self):
        self.configure_rotation()
        storage = self.components['fields']
        resolver = storage.crypto.keys
        for purpose in (KeyPurpose.LINK, KeyPurpose.PSEUDONYM):
            reference = replace(storage.index_keys[0], purpose=purpose, key_ref=purpose.value + '/v2')
            self.assertIsInstance(resolver.resolve(reference, purpose, 'service/security'), ProtectionError)
        self.assertIsInstance(resolver.resolve(storage.data_key, KeyPurpose.INDEX, 'service/security'), ProtectionError)
        self.assertNotEqual(storage.data_key.key_ref, storage.index_keys[0].key_ref)
