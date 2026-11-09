"""Formal-mode masking and admin scope during the explicit legacy transition."""
from datetime import timedelta
import json

from django.contrib import admin
from django.db import connection
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from challenges.models import Category, Challenge, ChallengeSolution
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.fields import bind_field_storage
from data_security.tests.phase4_fixtures import field_configuration
from exams.models import ExamAnswer, ExamRecord, TheoryQuestion
from exams.serializers import ExamAnswerSerializer, TheoryQuestionCreateSerializer
from learning_paths.models import LearningPath
from submissions.models import Submission
from submissions.serializers import SubmissionSerializer
from submissions.views import admin_submission_stats_view
from users.models import CTFUser, CourseDataGrant
from users.serializers import (AdminUserCreateSerializer, AdminUserUpdateSerializer,
                               UserRegisterSerializer, UserSerializer)


class LegacyTransitionM9Tests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        bind_field_storage(None)
        self.addCleanup(bind_field_storage, None)
        self.actor = CTFUser.objects.create_superuser(username='m9-admin', role='admin',
            email='Admin@example.invalid', password='synthetic-admin-passphrase')
        self.user = CTFUser.objects.create_user(username='legacy-subject', email='Subject@example.invalid')
        self.other = CTFUser.objects.create_user(username='outside-course', email='Outside@example.invalid')
        self.category = Category.objects.create(name='Synthetic transition')
        self.challenge = Challenge.objects.create(title='Legacy challenge', category=self.category,
            difficulty='easy', score=10, flag='LegacyFlag@example.invalid')
        self.solution = ChallengeSolution.objects.create(challenge=self.challenge,
            content='LegacySolution@example.invalid')
        self.question = TheoryQuestion.objects.create(question_type='single_choice',
            question_text='Legacy question', correct_answer='LegacyAnswer@example.invalid')
        record = ExamRecord.objects.create(user=self.user, exam_type='theory')
        self.answer = ExamAnswer.objects.create(exam_record=record, theory_question=self.question,
            user_answer='LegacyUserAnswer@example.invalid')
        self.submission = Submission.objects.create(user=self.user, challenge=self.challenge,
            flag='LegacySubmission@example.invalid', ip_address='192.0.2.40', user_agent='synthetic')
        for actor in (self.actor, self.other):
            Submission.objects.create(user=actor, challenge=self.challenge,
                flag='Incorrect@example.invalid', ip_address='192.0.2.40', user_agent='synthetic')
        self.client.force_login(self.actor)
        fixture = field_configuration(legacy_reads=True)
        path, *_ = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.components = assemble(config_path=path)
        bind_field_storage(self.components['fields'])

    def test_missing_request_masks_legacy_fields_in_formal_mode(self):
        cases = [(serializer, self.user, 'email', 'Subject@example.invalid') for serializer in (
            UserSerializer, UserRegisterSerializer, AdminUserCreateSerializer, AdminUserUpdateSerializer)]
        cases += [(TheoryQuestionCreateSerializer, self.question, 'correct_answer', 'LegacyAnswer@example.invalid'),
                  (ExamAnswerSerializer, self.answer, 'user_answer', 'LegacyUserAnswer@example.invalid'),
                  (SubmissionSerializer, self.submission, 'flag', 'LegacySubmission@example.invalid')]
        for serializer, instance, field, original in cases:
            with self.subTest(serializer=serializer.__name__):
                self.assertEqual(instance.security_state, 'legacy-v0')
                payload = serializer(instance).data
                self.assertEqual(payload[field], '[REDACTED]')
                self.assertNotIn(original, json.dumps(payload))
        bind_field_storage(None)
        for serializer, instance, field, original in cases:
            with self.subTest(unbound=serializer.__name__):
                self.assertEqual(serializer(instance).data[field], original)

    def test_user_create_update_representations_support_validated_mapping(self):
        value = {'username': 'transient', 'email': 'Transient@example.invalid', 'role': 'student', 'nickname': ''}
        for serializer in (UserRegisterSerializer, AdminUserCreateSerializer, AdminUserUpdateSerializer):
            self.assertEqual(serializer().to_representation(value)['email'], '[REDACTED]')
        bind_field_storage(None)
        for serializer in (UserRegisterSerializer, AdminUserCreateSerializer, AdminUserUpdateSerializer):
            self.assertEqual(serializer().to_representation(value)['email'], 'Transient@example.invalid')

    def test_sealed_user_output_stays_masked_without_bound_storage(self):
        self.user = CTFUser.objects.create_user(username='new-sealed-user', email='Sealed@example.invalid')
        self.user.refresh_from_db()
        self.assertEqual(self.user.security_state, 'sealed-v1')
        bind_field_storage(None)
        for serializer in (UserSerializer, UserRegisterSerializer, AdminUserCreateSerializer, AdminUserUpdateSerializer):
            self.assertEqual(serializer(self.user).data['email'], '[REDACTED]')

    def test_admin_statistics_use_course_grants_not_global_users(self):
        course = LearningPath.objects.create(title='Authorized synthetic course', slug='m9-authorized', difficulty='AP')
        denied = LearningPath.objects.create(title='Unassigned synthetic course', slug='m9-denied', difficulty='AP')
        CourseDataGrant.objects.create(actor=self.actor, student=self.user, course=course,
            granted_by=self.actor, expires_at=timezone.now() + timedelta(hours=1))
        for course_id, expected in ((None, {self.actor.pk}), (course.pk, {self.actor.pk, self.user.pk}),
                                    (denied.pk, {self.actor.pk}), ('invalid', {self.actor.pk})):
            with self.subTest(course=course_id):
                request = APIRequestFactory().get('/api/submissions/admin-stats/',
                    {'course': course_id} if course_id is not None else {})
                force_authenticate(request, user=self.actor)
                response = admin_submission_stats_view(request)
                self.assertEqual(response.status_code, 200)
                self.assertEqual({row['user_id'] for row in response.data['user_stats']}, expected)
                self.assertEqual(response.data['total_submissions'], len(expected))
                self.assertEqual(response.data['correct_submissions'], 0)
                self.assertNotIn(self.other.username, json.dumps(response.data))
        bind_field_storage(None)
        request = APIRequestFactory().get('/api/submissions/admin-stats/')
        force_authenticate(request, user=self.actor)
        response = admin_submission_stats_view(request)
        self.assertEqual(response.data['total_submissions'], 3)
        self.assertEqual({row['user_id'] for row in response.data['user_stats']},
                         {self.actor.pk, self.user.pk, self.other.pk})

    def test_admin_change_responses_hide_legacy_and_keep_sealed_answers_readonly(self):
        challenge = Challenge.objects.create(title='Sealed challenge', category=self.category,
            difficulty='easy', score=10, flag='SealedFlag@example.invalid')
        solution = ChallengeSolution.objects.create(challenge=challenge, content='SealedSolution@example.invalid')
        question = TheoryQuestion.objects.create(question_type='single_choice', question_text='Sealed question',
            correct_answer='SealedAnswer@example.invalid')
        request = RequestFactory().get('/admin/')
        request.user = self.actor
        cases = ((self.challenge, challenge, 'flag', 'LegacyFlag@example.invalid', 'SealedFlag@example.invalid'),
                 (self.solution, solution, 'content', 'LegacySolution@example.invalid', 'SealedSolution@example.invalid'),
                 (self.question, question, 'correct_answer', 'LegacyAnswer@example.invalid', 'SealedAnswer@example.invalid'))
        for legacy, sealed, field, legacy_value, sealed_value in cases:
            with self.subTest(model=type(legacy).__name__):
                model_admin = admin.site._registry[type(legacy)]
                rows = model_admin.get_queryset(request)
                self.assertFalse(rows.filter(pk=legacy.pk).exists())
                self.assertTrue(rows.filter(pk=sealed.pk).exists())
                self.assertIn(field, model_admin.get_readonly_fields(request, sealed))
                self.assertNotIn(field, model_admin.get_form(request, sealed).base_fields)
                url_name = f'admin:{legacy._meta.app_label}_{legacy._meta.model_name}_change'
                hidden = self.client.get(reverse(url_name, args=(legacy.pk,)))
                shown = self.client.get(reverse(url_name, args=(sealed.pk,)))
                self.assertEqual(hidden.status_code, 302)
                self.assertEqual(shown.status_code, 200)
                for value in (legacy_value, sealed_value):
                    self.assertNotIn(value.encode(), hidden.content)
                    self.assertNotIn(value.encode(), shown.content)
        bind_field_storage(None)
        for legacy, sealed, field, *_ in cases:
            self.assertTrue(admin.site._registry[type(legacy)].get_queryset(request).filter(pk=legacy.pk).exists())
