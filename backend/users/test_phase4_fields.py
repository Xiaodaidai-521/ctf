"""Owner-model field and email-query tests, using the real isolated key adapter."""
from copy import deepcopy
from datetime import timedelta
import json

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_assistant.models import AIConversation, AIMessage
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.fields import bind_field_storage
from data_security.contracts import ContractViolation
from data_security.tests.phase4_fixtures import field_configuration
from learning_paths.models import LearningPath
from users.models import CTFUser, CourseDataGrant
from users.permissions import authorized_users
from users.serializers import UserSerializer
from users.views import search_users_view


class FieldStorageTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        fixture = field_configuration(dual_index=True)
        path, self.config, refs, binding = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.components = assemble(config_path=path)
        bind_field_storage(self.components['fields'])
        self.addCleanup(bind_field_storage, None)

    def test_one_hundred_values_per_selected_field(self):
        originals = []
        for number in range(100):
            email = f'Synthetic{number}@example.invalid'
            user = CTFUser.objects.create_user(username=f'field-user-{number}', email=email)
            conversation = AIConversation.objects.create(user=user)
            text = f'Synthetic message {number}: {email}'
            metadata = {'note': text, 'count': number, 'items': []}
            message = AIMessage.objects.create(conversation=conversation, role='user', content=text, metadata=metadata)
            user.refresh_from_db()
            message.refresh_from_db()
            self.assertEqual(user.email, '')
            self.assertEqual(user.read_protected('email'), email)
            self.assertEqual(message.read_protected('content'), text)
            self.assertEqual(message.read_protected('metadata'), metadata)
            self.assertEqual((message.content, message.metadata), ('', {}))
            self.assertNotIn(email, json.dumps(message.security_envelopes))
            originals.append(email)
        with connection.cursor() as cursor:
            cursor.execute('SELECT email, security_envelopes::text, email_index, email_index_previous FROM users_ctfuser')
            users_copy = json.dumps(cursor.fetchall())
            cursor.execute('SELECT content, metadata::text, security_envelopes::text FROM ai_assistant_aimessage')
            message_copy = json.dumps(cursor.fetchall())
        self.assertTrue(all(value not in users_copy and value not in message_copy for value in originals))

    def test_same_value_different_object_and_no_incidental_overwrite(self):
        left = CTFUser.objects.create_user(username='left', email='Same@example.invalid')
        right = CTFUser.objects.create_user(username='right', email='Same@example.invalid')
        self.assertNotEqual(left.security_envelopes, right.security_envelopes)
        self.assertEqual(left.email_index, right.email_index)
        envelope = deepcopy(left.security_envelopes)
        left.refresh_from_db()
        left.score = 4
        left.save()
        left.refresh_from_db()
        self.assertEqual(left.security_envelopes, envelope)
        self.assertEqual(left.read_protected('email'), 'Same@example.invalid')
        left.email = ''
        left.save(update_fields=['email'])
        self.assertEqual(left.read_protected('email'), '')
        self.assertEqual((left.email_index, left.email_index_previous), ('', ''))

    def test_email_normalization_and_authorized_collision_confirmation(self):
        target = CTFUser.objects.create_user(username='target', email='  Case@EXAMPLE.INVALID  ')
        other_case = CTFUser.objects.create_user(username='other-case', email='case@example.invalid')
        self.assertEqual(target.read_protected('email'), 'Case@example.invalid')
        self.assertEqual(list(CTFUser.objects.exact_email(' Case@Example.Invalid ')), [target])
        self.assertEqual(list(CTFUser.objects.exact_email('case@example.invalid')), [other_case])
        self.assertEqual(list(authorized_users(target).exact_email('case@example.invalid')), [])
        # Simulate an index collision without altering the authenticated field envelope.
        with connection.cursor() as cursor:
            cursor.execute('UPDATE users_ctfuser SET email_index=%s WHERE id=%s', [target.email_index, other_case.pk])
        self.assertEqual(list(CTFUser.objects.exact_email('Case@example.invalid')), [target])

    def test_bulk_and_sql_cannot_put_plaintext_into_sealed_rows(self):
        user = CTFUser.objects.create_user(username='bulk-user', email='Bulk@example.invalid')
        with self.assertRaisesRegex(RuntimeError, 'FIELD_UPDATE'):
            CTFUser.objects.filter(pk=user.pk).update(email='Changed@example.invalid')
        user.email = 'Changed@example.invalid'
        with self.assertRaisesRegex(RuntimeError, 'FIELD_BULK_UPDATE'):
            CTFUser.objects.bulk_update([user], ['email'])
        with self.assertRaisesRegex(RuntimeError, 'FIELD_BULK_CREATE'):
            CTFUser.objects.bulk_create([CTFUser(username='bulk-new', email='New@example.invalid')])
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE users_ctfuser SET email=%s WHERE id=%s', ['Changed@example.invalid', user.pk])

    def test_corruption_swapping_and_unknown_state_do_not_read_legacy(self):
        left = CTFUser.objects.create_user(username='sealed-left', email='Left@example.invalid')
        right = CTFUser.objects.create_user(username='sealed-right', email='Right@example.invalid')
        left.security_envelopes = deepcopy(right.security_envelopes)
        left.email = 'NotAFallback@example.invalid'
        with self.assertRaisesRegex(RuntimeError, 'CIPHERTEXT_INVALID'):
            left.read_protected('email')
        left.security_state = 'unknown'
        with self.assertRaises(ContractViolation):
            left.read_protected('email')
        bind_field_storage(None)
        with self.assertRaises(ContractViolation):
            right.save()
        with self.assertRaises(ContractViolation):
            right.read_protected('email')

    def test_stale_model_save_is_rejected_and_password_stays_hashed(self):
        user = CTFUser.objects.create_user(username='versioned', email='Before@example.invalid', password='synthetic-passphrase-not-a-key')
        stale = CTFUser.objects.get(pk=user.pk)
        user.email = 'After@example.invalid'
        user.save(update_fields=['email'])
        stale.email = 'Stale@example.invalid'
        with self.assertRaises(ContractViolation), transaction.atomic():
            stale.save(update_fields=['email'])
        user.refresh_from_db()
        self.assertEqual(user.read_protected('email'), 'After@example.invalid')
        self.assertTrue(user.check_password('synthetic-passphrase-not-a-key'))
        self.assertNotIn('password', user.security_envelopes)
        self.assertNotEqual(user.password, 'synthetic-passphrase-not-a-key')

    def test_conversation_title_from_challenge_is_protected_without_changing_source(self):
        from ai_assistant.views import list_conversations
        from challenges.models import Category, Challenge
        user = CTFUser.objects.create_user(username='conversation-title-owner')
        category = Category.objects.create(name='Category@example.invalid')
        challenge = Challenge.objects.create(title='Title@example.invalid', category=category,
                                              difficulty='easy', score=1, flag='synthetic-title-flag')
        conversation = AIConversation.objects.create(user=user, challenge=challenge)
        request = APIRequestFactory().get('/api/ai-assistant/list/')
        force_authenticate(request, user=user)
        response = list_conversations(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['id'], conversation.pk)
        self.assertNotIn('@example.invalid', json.dumps(response.data))
        challenge.refresh_from_db()
        self.assertEqual(challenge.title, 'Title@example.invalid')
        bind_field_storage(None)
        legacy_response = list_conversations(request)
        self.assertEqual(legacy_response.data[0]['challenge_title'], challenge.title)

    def test_role_self_other_and_course_matrix_and_missing_request(self):
        student = CTFUser.objects.create_user(username='scoped-student', email='Student@example.invalid')
        other = CTFUser.objects.create_user(username='scoped-other', email='Other@example.invalid')
        teacher = CTFUser.objects.create_user(username='scoped-teacher', role='teacher', email='Teacher@example.invalid')
        admin = CTFUser.objects.create_user(username='scoped-admin', role='admin', email='Admin@example.invalid')
        course = LearningPath.objects.create(title='Synthetic course', slug='synthetic-course', difficulty='AP')
        denied_course = LearningPath.objects.create(title='Other synthetic course', slug='other-synthetic-course', difficulty='AP')
        for actor in (teacher, admin):
            CourseDataGrant.objects.create(actor=actor, student=student, course=course, granted_by=admin,
                                          expires_at=timezone.now() + timedelta(hours=1))
        for actor in (student, teacher, admin):
            for course_id in (None, course.pk, denied_course.pk):
                with self.subTest(role=actor.role, course=course_id):
                    expected = {actor.pk}
                    if actor.role != 'student' and course_id == course.pk:
                        expected.add(student.pk)
                    self.assertEqual(set(authorized_users(actor, course_id).values_list('pk', flat=True)), expected)
                    request = APIRequestFactory().get('/api/users/search/', {'email': 'Other@example.invalid',
                        **({'course': course_id} if course_id else {})})
                    force_authenticate(request, user=actor)
                    response = search_users_view(request)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data['users'], [])
        self.assertEqual(UserSerializer(student).data['email'], '[REDACTED]')
        CourseDataGrant.objects.filter(actor=teacher).update(active=False)
        self.assertEqual(set(authorized_users(teacher, course.pk).values_list('pk', flat=True)), {teacher.pk})
