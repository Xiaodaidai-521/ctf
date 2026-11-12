"""Real AEAD with disposable random keys; public state never implies an ACL."""
from copy import deepcopy
from datetime import timedelta
import secrets
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import AIConversation, AIMessage
from agent_runtime.memory import UserMemoryStore
from agent_runtime.models import AgentRun, UserMemory
from data_security.adapters.django.protection_status import field_status, protection_for, summarize
from data_security.adapters.persistence.fields import FieldStorage, bind_field_storage
from data_security.application.crypto_service import CryptoService
from data_security.contracts import BASELINE_LIMITS, Environment, KeyPurpose, KeyReference, KeyStatus, SecretMaterial, ProtectionError, ReasonCode
from users.models import CTFUser
from users.serializers import UserSerializer
from legal.models import LegalReport
from exams.models import ExamRecord, ExamAnswer
from exams.serializers import ExamRecordSerializer
from student_profiles.models import StudentProfile, StudentProfileReport
from student_profiles.serializers import StudentProfileReportSerializer
from resources.models import Resource, ExportSource, ExportSourcePermission


class PrivacyStatusTests(TestCase):
    def setUp(self):
        bind_field_storage(None)
        self.addCleanup(bind_field_storage, None)
        self.user = CTFUser.objects.create_user(username='privacy-owner', email='old@example.invalid')
        self.other = CTFUser.objects.create_user(username='privacy-other')
        self.admin = CTFUser.objects.create_user(username='privacy-admin', role='admin', is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        data = KeyReference(schema_version=KeyReference.SCHEMA, key_ref=KeyPurpose.DATA.value + '/v1',
                            purpose=KeyPurpose.DATA, version='v1', status=KeyStatus.ACTIVE)
        index = KeyReference(schema_version=KeyReference.SCHEMA, key_ref=KeyPurpose.INDEX.value + '/v1',
                             purpose=KeyPurpose.INDEX, version='v1', status=KeyStatus.ACTIVE)
        material = {data.key_ref: secrets.token_bytes(32), index.key_ref: secrets.token_bytes(32)}
        self.keys = Mock(resolve=Mock(side_effect=lambda key, purpose, identity: SecretMaterial(material[key.key_ref], purpose)))
        crypto = CryptoService(keys=self.keys, service_identity='service/privacy-test', random_bytes=secrets.token_bytes,
                               environment=Environment.EVALUATION, limits=BASELINE_LIMITS)
        self.storage = FieldStorage(crypto=crypto, data_key=data, index_keys=(index,), legacy_reads=True,
                                    protect_value=lambda value: value)

    def bind(self):
        bind_field_storage(self.storage)

    def message(self, text='Synthetic saved message'):
        conversation = AIConversation.objects.create(user=self.user)
        return AIMessage.objects.create(conversation=conversation, role='user', content=text, metadata={})

    def test_legacy_not_claimed_encrypted_when_adapter_enabled(self):
        message = self.message()
        self.bind()
        self.assertEqual(field_status(message, 'content')['storage'], 'legacy')

    def test_real_ciphertext_authenticated_and_no_public_envelope(self):
        self.bind()
        user = CTFUser.objects.create_user(username='privacy-sealed', email='sealed@example.invalid')
        user.refresh_from_db()
        before = deepcopy(user.security_envelopes)
        serialized = UserSerializer(user).data
        self.assertEqual(serialized['protection']['email'], {'storage': 'encrypted', 'present': True})
        self.assertEqual(serialized['email'], '[REDACTED]')
        self.assertEqual(serialized['email_display'], '已隐藏')
        self.assertNotIn('security_envelopes', serialized)
        self.assertNotIn('sealed@example.invalid', str(serialized))
        self.assertEqual(user.security_envelopes, before)

    def test_tampered_envelope_does_not_show_success(self):
        self.bind()
        message = self.message()
        message.security_envelopes['content']['envelope']['ciphertext'] = 'AAAA'
        self.assertEqual(field_status(message, 'content')['storage'], 'unknown')

    def test_missing_key_or_adapter_does_not_show_success(self):
        self.bind()
        message = self.message()
        self.storage.read_keys.clear()
        self.assertEqual(field_status(message, 'content')['storage'], 'unknown')
        bind_field_storage(None)
        self.assertEqual(field_status(message, 'content')['storage'], 'unknown')

    def test_unsaved_change_does_not_inherit_saved_status(self):
        self.bind()
        message = self.message()
        message.content = 'Unsaved edit'
        self.assertEqual(field_status(message, 'content')['storage'], 'unknown')

    def test_redaction_only_model_is_not_field_encryption(self):
        self.bind()
        run = AgentRun.objects.create(user=self.user, task_type='learning')
        self.assertEqual(run.security_state, 'sealed-v1')
        self.assertEqual(protection_for(run), {})

    def test_empty_and_mixed_collections(self):
        self.assertEqual(summarize([])['storage'], 'empty')
        self.assertEqual(summarize([{'storage': 'empty'}])['storage'], 'empty')
        self.assertEqual(summarize([{'storage': 'encrypted'}, {'storage': 'legacy'}])['storage'], 'partial')
        self.assertEqual(summarize([{'storage': 'encrypted'}, {'storage': 'unknown'}])['storage'], 'unknown')

    def test_conversation_complete_scope_and_acl(self):
        message = self.message('Legacy message')
        self.bind()
        AIMessage.objects.create(conversation=message.conversation, role='assistant', content='Sealed message')
        url = f'/api/data-security/privacy/conversations/{message.conversation_id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['protection']['content']['storage'], 'partial')
        self.assertEqual(response.data['protection']['content']['total'], 2)
        self.assertNotIn('Legacy message', str(response.data))
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_memories_only_owner_can_list_or_delete(self):
        self.bind()
        store = UserMemoryStore(user=self.user)
        memory = store.remember(memory_type='fact', memory_key='test/fact', memory_value={'note': 'Synthetic fact'})
        other = UserMemoryStore(user=self.other).remember(memory_type='fact', memory_key='test/other', memory_value={'note': 'Other fact'})
        response = self.client.get('/api/agent-runtime/memories/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data['results']], [memory.pk])
        self.assertEqual(response.data['results'][0]['protection']['memory_value']['storage'], 'encrypted')
        self.assertNotIn('memory_key', response.data['results'][0])
        self.assertEqual(self.client.delete(f'/api/agent-runtime/memories/{other.pk}/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/agent-runtime/memories/{memory.pk}/').status_code, 204)
        self.assertFalse(UserMemory.objects.filter(pk=memory.pk).exists())
        self.assertTrue(UserMemory.objects.filter(pk=other.pk).exists())

    def test_capabilities_do_not_expose_admin_policy_or_keys(self):
        self.bind()
        self.client.force_authenticate(None)
        response = self.client.get('/api/data-security/privacy/capabilities/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {'field_storage', 'private_files', 'controlled_export'})
        self.assertEqual(response.data['field_storage'], 'enabled-unverified')
        self.assertEqual(response['Cache-Control'], 'no-store, private')

    def test_exam_aggregate_uses_all_submitted_answers(self):
        record = ExamRecord.objects.create(user=self.user, exam_type='theory')
        ExamAnswer.objects.create(exam_record=record, user_answer='Legacy A')
        self.bind()
        ExamAnswer.objects.create(exam_record=record, user_answer='Sealed B')
        self.assertEqual(ExamRecordSerializer(record).data['protection']['user_answer']['storage'], 'partial')

    def test_report_count_available_without_raw_interview(self):
        self.bind()
        profile = StudentProfile.objects.create(user=self.user)
        report = StudentProfileReport.objects.create(profile=profile,
            raw_interview=[{'answer': 'First'}, {'answer': 'Second'}, {'answer': ''}])
        result = StudentProfileReportSerializer(report).data
        self.assertEqual(result['raw_interview'], [])
        self.assertEqual(result['answered_question_count'], 2)
        self.assertEqual(result['protection']['raw_interview']['storage'], 'encrypted')

    def test_report_export_without_generator_has_no_side_effects(self):
        self.client.force_authenticate(self.admin)
        report = LegalReport.objects.create(title='Synthetic report', report_type='compliance', content='Report', generated_by=self.admin)
        previous = report.status
        response = self.client.post(f'/api/legal/reports/{report.pk}/export/')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'EXPORT_NOT_AVAILABLE')
        report.refresh_from_db()
        self.assertEqual(report.status, previous)

    def export_permission(self, suffix, actor=None, **kwargs):
        resource = Resource.objects.create(title='Synthetic ' + suffix, uploader=self.user)
        deadline = timezone.now() + timedelta(hours=1)
        source = ExportSource.objects.create(source_ref='source/' + suffix, resource=resource,
            document={'private_original': 'never serialize this source'}, document_hash='a' * 64,
            expires_at=deadline)
        return ExportSourcePermission.objects.create(source=source, authorization_ref='grant/' + suffix,
            actor_ref='user/' + str((actor or self.user).pk), source_hash=source.document_hash,
            granted_by='user/' + str(self.admin.pk), expires_at=deadline, **kwargs)

    def test_export_records_current_subject_grants_only_and_no_delivery_effects(self):
        allowed = self.export_permission('allowed')
        self.export_permission('other', actor=self.other)
        self.export_permission('revoked', revoked_at=timezone.now())
        expired = self.export_permission('expired')
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save()
        owner = Mock()
        owner.describe.return_value = {'state': 'ready', 'can_execute': True, 'can_download': False,
            'protection': {'redaction': 'unknown', 'storage': 'unknown'}}
        with patch('data_security.adapters.django.export_delivery.export_delivery', return_value=owner):
            response = self.client.get('/api/data-security/exports/records/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row['id'] for row in response.data['items']], [allowed.pk])
            self.assertNotIn('never serialize', str(response.data))
            self.assertEqual(response['Cache-Control'], 'no-store, private')
            owner.sources.load.assert_called_once_with(user=self.user, source_ref=allowed.source.source_ref,
                                                       permission_ref=allowed.authorization_ref)
            owner.execute.assert_not_called()
            owner.open_delivery.assert_not_called()
            self.client.force_authenticate(self.admin)
            self.assertEqual(self.client.get('/api/data-security/exports/records/').data['items'], [])

    def test_export_owner_revalidation_never_turns_denial_into_success(self):
        self.export_permission('denied')
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUTHORIZATION_DENIED,
                                  retryable=False, trace_id='test/privacy-export')
        owner = Mock()
        owner.sources.load.return_value = failure
        with patch('data_security.adapters.django.export_delivery.export_delivery', return_value=owner):
            self.assertEqual(self.client.get('/api/data-security/exports/records/').data['items'], [])
            owner.describe.assert_not_called()
            owner.sources.load.return_value = object()
            owner.describe.return_value = failure
            row = self.client.get('/api/data-security/exports/records/').data['items'][0]
            self.assertEqual(row['state'], 'pending')
            self.assertFalse(row['can_execute'] or row['can_download'])
            self.assertEqual(row['protection'], {'redaction': 'unknown', 'storage': 'unknown'})

    def test_export_records_validate_filters_before_owner_access(self):
        owner = Mock()
        with patch('data_security.adapters.django.export_delivery.export_delivery', return_value=owner):
            for query in ('offset=-1', 'resource_id=bad', 'actor_ref=user/999', 'offset=0&offset=20'):
                with self.subTest(query=query):
                    self.assertEqual(self.client.get('/api/data-security/exports/records/?' + query).status_code, 400)
            owner.sources.load.assert_not_called()
