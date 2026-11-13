"""Database assertions for business field storage, with disposable AEAD keys."""
from copy import deepcopy
import json
import secrets
from unittest.mock import Mock, patch

from django.db import IntegrityError, connection
from django.test import TestCase

from agent_runtime.memory import UserMemoryStore
from agent_runtime.models import UserMemory
from ai_assistant.models import AIConversation, AIMessage
from data_security.adapters.persistence.fields import FieldStorage, bind_field_storage
from data_security.application.crypto_service import CryptoService
from data_security.contracts import (
    BASELINE_LIMITS, ContractViolation, Environment, KeyPurpose, KeyReference,
    KeyStatus, SecretMaterial,
)
from exams.models import ExamAnswer, ExamRecord
from legal.models import ComplianceAgentRun, LegalAnalysisTask, LegalFactSnapshot, LegalReport
from legal.services.compliance_orchestrator import ComplianceOrchestrator
from student_profiles.models import OnboardingInterview, StudentProfile, StudentProfileReport
from users.models import CTFUser


PRIVATE_EMAIL = 'private-person@example.invalid'


def redact(value):
    if isinstance(value, str):
        return value.replace(PRIVATE_EMAIL, '[REDACTED]')
    if isinstance(value, dict):
        return {name: redact(item) for name, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class FieldStorageWriteTests(TestCase):
    def setUp(self):
        bind_field_storage(None)
        self.addCleanup(bind_field_storage, None)
        self.user = CTFUser.objects.create_user(username='field-write-owner')
        data = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='enc-data/v1',
            purpose=KeyPurpose.DATA, version='v1', status=KeyStatus.ACTIVE)
        index = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='query-index/v1',
            purpose=KeyPurpose.INDEX, version='v1', status=KeyStatus.ACTIVE)
        material = {data.key_ref: secrets.token_bytes(32), index.key_ref: secrets.token_bytes(32)}
        keys = Mock(resolve=Mock(side_effect=lambda key, purpose, identity:
                    SecretMaterial(material[key.key_ref], purpose)))
        crypto = CryptoService(keys=keys, service_identity='service/field-write-tests',
            random_bytes=secrets.token_bytes, environment=Environment.EVALUATION, limits=BASELINE_LIMITS)
        self.storage = FieldStorage(crypto=crypto, data_key=data, index_keys=(index,),
                                    legacy_reads=True, protect_value=redact)
        bind_field_storage(self.storage)

    def message(self, **kwargs):
        conversation = AIConversation.objects.create(user=self.user)
        return AIMessage.objects.create(conversation=conversation, role='user',
            content='Original ' + PRIVATE_EMAIL, metadata={'contact': PRIVATE_EMAIL}, **kwargs)

    def raw_row(self, obj):
        quote = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT * FROM {quote(obj._meta.db_table)} WHERE {quote(obj._meta.pk.column)} = %s',
                           [obj.pk])
            return json.dumps(cursor.fetchone(), default=str)

    def test_all_requested_business_fields_are_ciphertext_and_round_trip(self):
        user = CTFUser.objects.create_user(username='encrypted-email', email=PRIVATE_EMAIL)
        message = self.message()
        memory = UserMemoryStore(user=self.user).remember(memory_type='fact', memory_key='contact',
            memory_value={'value': PRIVATE_EMAIL}, metadata={'source': PRIVATE_EMAIL})
        profile = StudentProfile.objects.create(user=self.user, learning_goals=PRIVATE_EMAIL)
        interview = OnboardingInterview.objects.create(profile=profile,
            answers={'1': PRIVATE_EMAIL}, ai_analysis={'summary': PRIVATE_EMAIL})
        profile_report = StudentProfileReport.objects.create(profile=profile,
            raw_interview=[{'answer': PRIVATE_EMAIL}], summary=PRIVATE_EMAIL,
            report_data={'summary': PRIVATE_EMAIL})
        record = ExamRecord.objects.create(user=self.user, exam_type='theory')
        answer = ExamAnswer.objects.create(exam_record=record, user_answer=PRIVATE_EMAIL)
        task = LegalAnalysisTask.objects.create(created_by=self.user, title=PRIVATE_EMAIL,
            input_text=PRIVATE_EMAIL, result_summary=PRIVATE_EMAIL)
        report = LegalReport.objects.create(task=task, title=PRIVATE_EMAIL,
            summary=PRIVATE_EMAIL, content=PRIVATE_EMAIL)
        snapshot = LegalFactSnapshot.objects.create(source_kind='hybrid', scope={}, automated_facts={},
            manual_notes=PRIVATE_EMAIL, preview_hash='a' * 64, snapshot_hash='b' * 64,
            confirmed_by=self.user)
        values = (
            (user, 'email', PRIVATE_EMAIL), (message, 'content', 'Original ' + PRIVATE_EMAIL),
            (message, 'metadata', {'contact': PRIVATE_EMAIL}),
            (memory, 'memory_value', {'value': PRIVATE_EMAIL}), (memory, 'metadata', {'source': PRIVATE_EMAIL}),
            (interview, 'answers', {'1': PRIVATE_EMAIL}),
            (profile_report, 'raw_interview', [{'answer': PRIVATE_EMAIL}]),
            (answer, 'user_answer', PRIVATE_EMAIL), (task, 'input_text', PRIVATE_EMAIL),
            (report, 'content', PRIVATE_EMAIL), (snapshot, 'manual_notes', PRIVATE_EMAIL),
        )
        for obj, name, expected in values:
            with self.subTest(model=obj._meta.label, field=name):
                obj.refresh_from_db()
                self.assertEqual(obj.security_state, 'sealed-v1')
                self.assertIn(getattr(obj, name), ('', {}))
                self.assertEqual(obj.read_protected(name), expected)
                self.assertNotIn(PRIVATE_EMAIL, self.raw_row(obj))
        self.assertNotIn(PRIVATE_EMAIL, self.raw_row(profile))
        self.assertEqual(CTFUser.objects.exact_email(PRIVATE_EMAIL).get().pk, user.pk)
        self.assertNotIn(PRIVATE_EMAIL, user.email_index)

    def test_partial_save_keeps_other_pending_encrypted_edits_for_next_save(self):
        message = self.message()
        message.content = 'Changed body'
        message.metadata = {'source': 'Changed metadata'}
        message.save(update_fields=['content'])
        stored = AIMessage.objects.get(pk=message.pk)
        self.assertEqual(stored.read_protected('content'), 'Changed body')
        self.assertEqual(stored.read_protected('metadata'), {'contact': PRIVATE_EMAIL})
        self.assertEqual(message._security_dirty, {'metadata'})
        message.save()
        message.refresh_from_db()
        self.assertEqual(message.read_protected('metadata'), {'source': 'Changed metadata'})
        self.assertEqual(message._security_dirty, set())

    def test_seal_failure_preserves_pending_values_and_can_be_retried(self):
        message = self.message()
        original_envelopes = deepcopy(message.security_envelopes)
        original_revision = message.security_revision
        message.content = 'Retry body'
        message.metadata = {'source': 'Retry metadata'}
        seal = self.storage.seal

        def fail_metadata(instance, name, value, revision, **kwargs):
            if name == 'metadata':
                raise RuntimeError('KEY_UNAVAILABLE')
            return seal(instance, name, value, revision, **kwargs)

        with patch.object(self.storage, 'seal', side_effect=fail_metadata):
            with self.assertRaisesRegex(RuntimeError, 'KEY_UNAVAILABLE'):
                message.save()
        self.assertEqual(message.content, 'Retry body')
        self.assertEqual(message.metadata, {'source': 'Retry metadata'})
        self.assertEqual(message.security_revision, original_revision)
        self.assertEqual(message.security_envelopes, original_envelopes)
        self.assertEqual(AIMessage.objects.get(pk=message.pk).security_envelopes, original_envelopes)
        message.save()
        message.refresh_from_db()
        self.assertEqual(message.read_protected('content'), 'Retry body')
        self.assertEqual(message.read_protected('metadata'), {'source': 'Retry metadata'})

    def test_database_failure_preserves_email_for_retry(self):
        user = CTFUser(username=self.user.username, email=PRIVATE_EMAIL)
        with self.assertRaises(IntegrityError):
            user.save()
        self.assertTrue(user._state.adding)
        self.assertEqual(user.email, PRIVATE_EMAIL)
        self.assertEqual(user.security_envelopes, {})
        user.username = 'retry-unique-user'
        user.save()
        self.assertEqual(user.read_protected('email'), PRIVATE_EMAIL)

    def test_runtime_migration_on_regular_update_encrypts_all_legacy_fields(self):
        bind_field_storage(None)
        legacy = CTFUser.objects.create_user(username='legacy-email', email=PRIVATE_EMAIL)
        bind_field_storage(self.storage)
        self.storage.migrate_on_write = True
        legacy.nickname = 'Updated name'
        legacy.save(update_fields=['nickname'])
        legacy.refresh_from_db()
        self.assertEqual(legacy.nickname, 'Updated name')
        self.assertEqual(legacy.read_protected('email'), PRIVATE_EMAIL)
        self.assertEqual(legacy.email, '')
        self.assertNotIn(PRIVATE_EMAIL, self.raw_row(legacy))

    def test_formal_adapter_still_requires_explicit_legacy_migration(self):
        with self.assertRaises(ContractViolation):
            self.user.save(update_fields=['last_login'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.security_state, 'legacy-v0')

    def test_exact_email_includes_authorized_legacy_rows_with_same_case_semantics(self):
        bind_field_storage(None)
        legacy = CTFUser.objects.create_user(username='legacy-search', email='Case@EXAMPLE.INVALID')
        bind_field_storage(self.storage)
        self.assertEqual(list(CTFUser.objects.exact_email(' Case@example.invalid ')), [legacy])
        self.assertFalse(CTFUser.objects.exact_email('case@example.invalid').exists())
        self.assertFalse(CTFUser.objects.filter(pk=self.user.pk).exact_email('Case@example.invalid').exists())
        self.storage.legacy_reads = False
        self.assertFalse(CTFUser.objects.exact_email('Case@example.invalid').exists())

    def test_unbound_or_tampered_ciphertext_cannot_fall_back_to_plaintext(self):
        message = self.message()
        original = deepcopy(message.security_envelopes)
        message.security_envelopes['content'] = deepcopy(original['metadata'])
        with self.assertRaises((RuntimeError, ContractViolation)):
            message.read_protected('content')
        bind_field_storage(None)
        with self.assertRaises(ContractViolation):
            message.save()
        self.assertEqual(AIMessage.objects.get(pk=message.pk).security_envelopes, original)

    def test_bulk_protected_writes_are_rejected_before_plaintext_reaches_database(self):
        message = self.message()
        with self.assertRaisesRegex(RuntimeError, 'FIELD_UPDATE_REQUIRES_OBJECT_SAVE'):
            AIMessage.objects.filter(pk=message.pk).update(content='Unsealed write')
        message.metadata = {'unsafe': 'Unsealed metadata'}
        with self.assertRaisesRegex(RuntimeError, 'FIELD_BULK_UPDATE_REQUIRES_OBJECT_SAVE'):
            AIMessage.objects.bulk_update([message], ['metadata'])
        self.assertEqual(AIMessage.objects.get(pk=message.pk).read_protected('metadata'),
                         {'contact': PRIVATE_EMAIL})

    def test_memory_update_service_encrypts_replacement_value_and_metadata(self):
        store = UserMemoryStore(user=self.user)
        memory = store.remember(memory_type='fact', memory_key='replace', memory_value={'v': 'first'})
        updated = store.remember(memory_type='fact', memory_key='replace',
            memory_value={'v': PRIVATE_EMAIL}, metadata={'source': PRIVATE_EMAIL})
        self.assertEqual(updated.pk, memory.pk)
        self.assertEqual(store.recall(memory_type='fact', memory_key='replace')['memory_value'],
                         {'v': PRIVATE_EMAIL})
        self.assertNotIn(PRIVATE_EMAIL, self.raw_row(updated))

    def test_legal_failure_details_use_redacted_storage_path(self):
        task = LegalAnalysisTask.objects.create(created_by=self.user, title='Failure case', input_text=PRIVATE_EMAIL)
        with patch('legal.services.compliance_orchestrator.AuditEvent.log') as audit:
            ComplianceOrchestrator()._mark_failed(task=task, actor=self.user,
                                                 error=RuntimeError('Could not analyze ' + PRIVATE_EMAIL))
        task.refresh_from_db()
        self.assertEqual(task.status, 'failed')
        self.assertEqual(task.error_message, 'Could not analyze [REDACTED]')
        self.assertNotIn(PRIVATE_EMAIL, str(audit.call_args))
        self.assertNotIn(PRIVATE_EMAIL, self.raw_row(task))
        run = ComplianceAgentRun.objects.create(task=task, error_message='Provider rejected ' + PRIVATE_EMAIL)
        self.assertNotIn(PRIVATE_EMAIL, self.raw_row(run))
