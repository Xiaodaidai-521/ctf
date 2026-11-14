"""Normal deployment protections: real cipher, raw SQL, restart and migration."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import json
import os
from pathlib import Path
import secrets
import tempfile
from unittest.mock import patch
from unittest import skipUnless

from django.core.management import call_command
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings

from data_security.adapters.persistence import fields
from data_security.runtime.crypto import RuntimeCipher, get_cipher, load_key, restrict_path
from data_security.runtime.fields import RuntimeFieldStorage
from data_security.runtime.redaction import redact


class RuntimeCryptoTests(SimpleTestCase):
    def test_random_nonces_roundtrip_and_context_binding(self):
        cipher = RuntimeCipher(secrets.token_bytes(64))
        first = cipher.encrypt(b'sensitive-original', 'object/1')
        second = cipher.encrypt(b'sensitive-original', 'object/1')
        self.assertNotEqual(first, second)
        self.assertNotIn(b'sensitive-original', first)
        self.assertEqual(cipher.decrypt(first, 'object/1'), b'sensitive-original')
        for data, context in ((first, 'object/2'), (first[:-1] + bytes([first[-1] ^ 1]), 'object/1'),
                              (b'plaintext', 'object/1')):
            with self.assertRaises(ValueError):
                cipher.decrypt(data, context)
        with self.assertRaises(ValueError):
            RuntimeCipher(secrets.token_bytes(64)).decrypt(first, 'object/1')

    def test_persistent_key_survives_restart_and_missing_key_cannot_regenerate(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'private' / 'storage.key'
            first = load_key(key)
            self.assertEqual(first, load_key(key))
            encrypted = RuntimeCipher(first).encrypt(b'original', 'restart')
            self.assertEqual(RuntimeCipher(load_key(key)).decrypt(encrypted, 'restart'), b'original')
            key.unlink()
            with self.assertRaises(ImproperlyConfigured):
                load_key(key)

    def test_first_start_workers_share_one_fully_written_private_key(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'new-installation' / 'private' / 'storage.key'
            with ThreadPoolExecutor(max_workers=8) as executor:
                material = list(executor.map(lambda _: load_key(key), range(16)))
            self.assertTrue(all(value == material[0] and len(value) == 64 for value in material))
            self.assertEqual(list(key.parent.glob('.storage-key-*')), [])

    @skipUnless(os.name == 'nt', 'Windows uses exclusive rename for key publication')
    def test_windows_key_publication_does_not_require_hardlink_support(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'private' / 'storage.key'
            with patch('data_security.runtime.crypto.os.link', side_effect=OSError(17, 'Hard links unavailable')):
                material = load_key(key)
            self.assertEqual(len(material), 64)
            self.assertEqual(load_key(key), material)
            self.assertEqual(list(key.parent.glob('.storage-key-*')), [])

    @skipUnless(os.name == 'nt', 'Windows rename must preserve a concurrently published key')
    def test_windows_key_publication_never_replaces_a_concurrent_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'private' / 'storage.key'
            winner = secrets.token_bytes(64)
            rename = os.rename

            def publish_winner_first(source, destination):
                Path(destination).write_bytes(winner)
                restrict_path(Path(destination))
                return rename(source, destination)

            with patch('data_security.runtime.crypto.os.rename', side_effect=publish_winner_first):
                material = load_key(key)
            self.assertEqual(material, winner)
            self.assertEqual(key.read_bytes(), winner)
            self.assertEqual(list(key.parent.glob('.storage-key-*')), [])

    @skipUnless(os.name == 'nt', 'Windows packaged applications can redirect LOCALAPPDATA across drives')
    def test_windows_key_publication_resolves_virtualized_appdata_parent(self):
        # Unlike the usual TEMP fixture, LOCALAPPDATA can retain a lexical C:
        # alias while this packaged process stores its files on another drive.
        with tempfile.TemporaryDirectory(prefix='ctf-key-publish-test-', dir=os.environ['LOCALAPPDATA']) as directory:
            key = Path(directory) / 'private' / 'disposable-test.key'
            material = load_key(key)
            self.assertEqual(len(material), 64)
            self.assertEqual(load_key(key), material)
            self.assertEqual(key.read_bytes(), material)
            self.assertEqual(list(key.parent.glob('.storage-key-*')), [])

    def test_redaction_preserves_ordinary_values_and_covers_nested_personal_data(self):
        value = {'summary': '邮箱 alpha@example.com 电话 13812345678 身份证 110101199001011234',
                 'details': [{'phone': 13812345678, 'token': 'sensitive-token', 'score': 75}],
                 'category': '网络安全'}
        result = redact(value)
        self.assertNotIn('alpha@example.com', str(result))
        self.assertNotIn('13812345678', str(result))
        self.assertNotIn('110101199001011234', str(result))
        self.assertNotIn('sensitive-token', str(result))
        self.assertEqual(result['details'][0]['score'], 75)
        self.assertEqual(result['category'], '网络安全')
        self.assertEqual(redact(result), result)


class RuntimeFieldTests(TestCase):
    def setUp(self):
        self.old = fields._adapter
        self.addCleanup(fields.bind_field_storage, self.old)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / 'security'
        self.settings_override = override_settings(DATA_PROTECTION_ENABLED=True,
            DATA_PROTECTION_ROOT=root, DATA_PROTECTION_KEY_FILE=root / 'storage.key')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        fields.bind_field_storage(RuntimeFieldStorage())
        from users.models import CTFUser
        self.user = CTFUser.objects.create_user(username='runtime-owner', email='owner@example.com')

    def assert_stored(self, obj, expected):
        obj.refresh_from_db()
        quoted = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute('SELECT ' + ','.join(quoted(name) for name in expected) + ',' +
                quoted('security_envelopes') + ' FROM ' + quoted(obj._meta.db_table) +
                ' WHERE ' + quoted(obj._meta.pk.column) + ' = %s', [obj.pk])
            raw = cursor.fetchone()
        for index, (name, value) in enumerate(expected.items()):
            self.assertIn(raw[index], ('', '{}'))
            self.assertEqual(obj.read_protected(name), value)
            for marker in ('sensitive-original', 'owner@example.com'):
                self.assertNotIn(marker, str(raw))

    def test_all_requested_fields_are_ciphertext_in_actual_database_columns(self):
        from ai_assistant.models import AIConversation, AIMessage
        from agent_runtime.models import UserMemory
        from student_profiles.models import StudentProfile, OnboardingInterview, StudentProfileReport
        from exams.models import ExamRecord, ExamAnswer
        from legal.models import LegalAnalysisTask, LegalReport, LegalFactSnapshot
        self.assert_stored(self.user, {'email': 'owner@example.com'})
        conversation = AIConversation.objects.create(user=self.user)
        message = AIMessage.objects.create(conversation=conversation, role='user',
            content='sensitive-original', metadata={'original': 'sensitive-original'})
        self.assert_stored(message, {'content': 'sensitive-original', 'metadata': {'original': 'sensitive-original'}})
        memory = UserMemory.objects.create(user=self.user, memory_type='fact', memory_key='key',
            memory_value={'original': 'sensitive-original'}, metadata={'note': 'sensitive-original'})
        self.assert_stored(memory, {'memory_value': {'original': 'sensitive-original'}, 'metadata': {'note': 'sensitive-original'}})
        profile, _ = StudentProfile.objects.get_or_create(user=self.user)
        interview = OnboardingInterview.objects.create(profile=profile, answers={'1': 'sensitive-original'},
            ai_analysis={'summary': 'owner@example.com'})
        self.assert_stored(interview, {'answers': {'1': 'sensitive-original'}})
        self.assertNotIn('owner@example.com', str(interview.ai_analysis))
        report = StudentProfileReport.objects.create(profile=profile, raw_interview=['sensitive-original'],
            summary='owner@example.com')
        self.assert_stored(report, {'raw_interview': ['sensitive-original']})
        self.assertNotIn('owner@example.com', report.summary)
        record = ExamRecord.objects.create(user=self.user, exam_type='theory')
        answer = ExamAnswer.objects.create(exam_record=record, user_answer='sensitive-original')
        self.assert_stored(answer, {'user_answer': 'sensitive-original'})
        task = LegalAnalysisTask.objects.create(created_by=self.user, title='owner@example.com',
            input_text='sensitive-original', result_summary='owner@example.com')
        self.assert_stored(task, {'input_text': 'sensitive-original'})
        self.assertNotIn('owner@example.com', task.title + task.result_summary)
        legal_report = LegalReport.objects.create(generated_by=self.user, title='owner@example.com',
            content='sensitive-original', summary='owner@example.com')
        self.assert_stored(legal_report, {'content': 'sensitive-original'})
        snapshot = LegalFactSnapshot.objects.create(confirmed_by=self.user, source_kind='hybrid',
            manual_notes='sensitive-original', preview_hash='a' * 64, snapshot_hash='b' * 64)
        self.assert_stored(snapshot, {'manual_notes': 'sensitive-original'})

    def test_other_row_envelope_and_tampered_ciphertext_are_rejected(self):
        from users.models import CTFUser
        other = CTFUser.objects.create_user(username='runtime-other', email='other@example.com')
        other.security_envelopes = deepcopy(self.user.security_envelopes)
        with self.assertRaises(ValueError):
            other.read_protected('email')

    def test_malformed_envelopes_are_unknown_and_never_expose_original_fields(self):
        from data_security.adapters.django.protection_status import field_status
        for envelope in (None, [], {'email': None},
                         {'email': {'revision': 1, 'envelope': []}}):
            with self.subTest(envelope=envelope):
                self.user.security_envelopes = envelope
                with self.assertRaisesRegex(ValueError, 'CIPHERTEXT_INVALID'):
                    self.user.read_protected('email')
                self.assertEqual(field_status(self.user, 'email'), {'storage': 'unknown', 'present': None})

    def test_read_after_restart_and_blind_email_lookup(self):
        from users.models import CTFUser
        fields.bind_field_storage(RuntimeFieldStorage(RuntimeCipher(load_key(
            self.settings_override.options['DATA_PROTECTION_KEY_FILE']))))
        self.assertEqual(CTFUser.objects.get(pk=self.user.pk).read_protected('email'), 'owner@example.com')
        self.assertEqual(CTFUser.objects.exact_email('owner@EXAMPLE.COM').get().pk, self.user.pk)
        self.assertFalse(CTFUser.objects.exact_email('absent@example.com').exists())

    def test_migration_dry_run_backup_and_idempotency(self):
        from users.models import CTFUser
        fields.bind_field_storage(None)
        legacy = CTFUser.objects.create_user(username='legacy-runtime', email='legacy@example.com')
        fields.bind_field_storage(RuntimeFieldStorage())
        output = StringIO()
        call_command('protect_existing_data', model=['users.CTFUser'], stdout=output)
        legacy.refresh_from_db()
        self.assertEqual(legacy.security_state, 'legacy-v0')
        output = StringIO()
        call_command('protect_existing_data', model=['users.CTFUser'], apply=True, stdout=output)
        result = json.loads(output.getvalue())
        self.assert_stored(legacy, {'email': 'legacy@example.com'})
        backup = next(Path(result['backup_directory']).glob('*.aead'))
        self.assertNotIn(b'legacy@example.com', backup.read_bytes())
        original = get_cipher().decrypt(backup.read_bytes(), 'migration-backup/v1/' + backup.name)
        self.assertEqual(json.loads(original)[0]['fields']['email'], 'legacy@example.com')
        again = StringIO()
        call_command('protect_existing_data', model=['users.CTFUser'], apply=True, stdout=again)
        self.assertEqual(json.loads(again.getvalue())['users.ctfuser']['migrated'], 0)

    def test_migration_leaves_original_row_when_durable_backup_fails(self):
        from users.models import CTFUser
        fields.bind_field_storage(None)
        legacy = CTFUser.objects.create_user(username='legacy-backup-failure', email='legacy@example.com')
        fields.bind_field_storage(RuntimeFieldStorage())
        with patch('data_security.adapters.persistence.management.commands.protect_existing_data.os.fsync',
                   side_effect=OSError('Backup unavailable')):
            with self.assertRaises(OSError):
                call_command('protect_existing_data', model=['users.CTFUser'], apply=True, stdout=StringIO())
        legacy.refresh_from_db()
        self.assertEqual(legacy.security_state, 'legacy-v0')
        self.assertEqual(legacy.email, 'legacy@example.com')
        self.assertEqual(legacy.security_envelopes, {})
