"""Profile owner fields, copies and HTTP scopes on isolated synthetic PostgreSQL."""
from datetime import timedelta
from importlib import import_module
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.fields import bind_field_storage
from data_security.tests.phase4_fixtures import field_configuration
from learning_paths.models import LearningPath
from users.models import CTFUser, CourseDataGrant

from .admin import OnboardingInterviewAdmin, StudentProfileReportAdmin
from .models import (DynamicGrowthProfile, LearningPersona, LearningPreference,
                     OnboardingInterview, StudentProfile, StudentProfileReport)
from .onboarding_service import ONBOARDING_QUESTIONS, _fallback_analysis, complete_interview, serialize_answers
from .serializers import StudentProfileReportSerializer
from .views import OnboardingInterviewView, StudentProfileReportReviewView, StudentProfileReportView


class ProfileFieldStorageTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        fixture = field_configuration()
        path, config, refs, binding = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        components = assemble(config_path=path)
        bind_field_storage(components['fields'])
        self.addCleanup(bind_field_storage, None)
        self.factory = APIRequestFactory()

    def profile(self, name, **kwargs):
        user = CTFUser.objects.create_user(username=name, **kwargs)
        return StudentProfile.objects.create(user=user)

    def test_one_hundred_values_per_encrypted_profile_field(self):
        originals = []
        for number in range(100):
            profile = self.profile(f'profile-synthetic-{number}')
            token = f'Profile{number}@example.invalid'
            profile.self_assessed_skills = {'web': 2, 'note': token}
            profile.initial_self_assessed_skills = {'web': 2, 'note': token}
            profile.save(update_fields=['self_assessed_skills', 'initial_self_assessed_skills'])
            LearningPreference.objects.create(profile=profile, preferred_modality=[token])
            LearningPersona.objects.create(profile=profile, persona_traits={'note': token, 'score': number},
                                           recommended_agent_roster=[token])
            growth = DynamicGrowthProfile.objects.create(profile=profile,
                **{field: {'note': token, 'score': number} for field in DynamicGrowthProfile.redacted_fields})
            self.assertEqual(growth.analysis['score'], number)
            answers = {'1': token, '2': f'Synthetic answer {number}'}
            rows = [{'id': 1, 'answer': token, 'score': number}]
            interview = OnboardingInterview.objects.create(profile=profile, answers=answers,
                                                           ai_analysis={'note': token, 'score': number})
            report = StudentProfileReport.objects.create(profile=profile, source_interview=interview,
                raw_interview=rows, report_data={'note': token, 'score': number}, summary=token)
            interview.refresh_from_db()
            report.refresh_from_db()
            self.assertEqual(interview.read_protected('answers'), answers)
            self.assertEqual(report.read_protected('raw_interview'), rows)
            self.assertEqual((interview.answers, report.raw_interview), ({}, {}))
            self.assertEqual(report.report_data['score'], number)
            originals.append(token)
        with connection.cursor() as cursor:
            copies = []
            for model in (StudentProfile, LearningPreference, LearningPersona, DynamicGrowthProfile,
                          OnboardingInterview, StudentProfileReport):
                table = connection.ops.quote_name(model._meta.db_table)
                cursor.execute(f'SELECT to_jsonb(stored_row)::text FROM {table} AS stored_row')
                copies.extend(cursor.fetchall())
        database_copy = json.dumps(copies)
        self.assertTrue(all(token not in database_copy for token in originals))

    def test_same_values_different_objects_and_unrelated_save(self):
        left_profile, right_profile = self.profile('profile-left'), self.profile('profile-right')
        interviews = [OnboardingInterview.objects.create(profile=profile, answers={'1': 'Same@example.invalid'})
                      for profile in (left_profile, right_profile)]
        reports = [StudentProfileReport.objects.create(profile=profile, raw_interview=[{'answer': 'Same@example.invalid'}])
                   for profile in (left_profile, right_profile)]
        self.assertNotEqual(interviews[0].security_envelopes, interviews[1].security_envelopes)
        self.assertNotEqual(reports[0].security_envelopes, reports[1].security_envelopes)
        for instance, field in ((interviews[0], 'answers'), (reports[0], 'raw_interview')):
            original = instance.read_protected(field)
            envelope = instance.security_envelopes
            instance.refresh_from_db()
            instance.save()
            self.assertEqual(instance.security_envelopes, envelope)
            self.assertEqual(instance.read_protected(field), original)

    def test_answer_http_merge_and_masked_self_response(self):
        profile = self.profile('profile-merge')
        for number, answer in ((1, 'Merge@example.invalid'), (2, 'Synthetic host 192.0.2.42')):
            request = self.factory.post('/api/student-profile/interview/', {'question_id': number, 'answer': answer})
            force_authenticate(request, user=profile.user)
            response = OnboardingInterviewView.as_view()(request)
            self.assertEqual(response.status_code, 200)
        interview = OnboardingInterview.objects.get(profile=profile)
        self.assertEqual(interview.read_protected('answers'), {'1': 'Merge@example.invalid', '2': 'Synthetic host 192.0.2.42'})
        request = self.factory.get('/api/student-profile/interview/')
        force_authenticate(request, user=profile.user)
        response = OnboardingInterviewView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Merge@example.invalid', json.dumps(response.data))
        self.assertNotIn('192.0.2.42', json.dumps(response.data))

    def test_completion_keeps_raw_only_in_envelopes_and_masks_derived_copies(self):
        profile = self.profile('profile-completion')
        token = 'Completion@example.invalid'
        answers = {str(item['id']): f'Synthetic answer {token}' for item in ONBOARDING_QUESTIONS}
        rows = serialize_answers(answers)
        analysis = _fallback_analysis(rows)
        analysis.update(learning_goal=token, summary=token, evidence={'web': token}, preferred_modality=[token])
        interview = OnboardingInterview.objects.create(profile=profile, answers=answers)
        with patch('student_profiles.onboarding_service.analyze_answers', return_value=(rows, analysis)):
            report = complete_interview(interview)
        interview.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(interview.read_protected('answers'), answers)
        self.assertEqual(report.read_protected('raw_interview'), rows)
        self.assertEqual(complete_interview(interview).pk, report.pk)
        persona = LearningPersona.objects.get(profile=profile)
        preference = LearningPreference.objects.get(profile=profile)
        growth = DynamicGrowthProfile.objects.create(profile=profile, analysis={'note': token, 'score': 42},
            growth_evidence={'web': {'reason': token}}, recommendation_preferences={'note': token})
        safe_copies = json.dumps([profile.learning_goals, profile.self_assessed_skills, report.report_data,
            report.summary, interview.ai_analysis, persona.persona_traits, preference.preferred_modality,
            growth.analysis, growth.growth_evidence, growth.recommendation_preferences])
        self.assertNotIn(token, safe_copies)
        self.assertEqual(growth.analysis['score'], 42)
        self.assertEqual(report.report_data['ability_scores'], analysis['ability_scores'])

    def test_fallback_protects_before_truncating_sensitive_token(self):
        token = 'Edge@example.invalid'
        answers = {str(item['id']): 'Synthetic answer' for item in ONBOARDING_QUESTIONS}
        answers['1'] = 'x' * 489 + ' ' + token
        result = _fallback_analysis(serialize_answers(answers))
        self.assertNotIn('Edge@', result['learning_goal'])

    def test_report_role_course_matrix_and_missing_request_never_reveal_raw(self):
        student = self.profile('profile-student')
        teacher = self.profile('profile-teacher', role='teacher')
        admin = self.profile('profile-admin', role='admin', is_staff=True, is_superuser=True)
        other = self.profile('profile-other')
        course = LearningPath.objects.create(title='Synthetic profile course', slug='synthetic-profile-course', difficulty='AP')
        denied = LearningPath.objects.create(title='Other profile course', slug='other-profile-course', difficulty='AP')
        for profile in (student, teacher, admin, other):
            StudentProfileReport.objects.create(profile=profile, raw_interview=[{'answer': 'Hidden@example.invalid'}])
        for profile in (teacher, admin):
            CourseDataGrant.objects.create(actor=profile.user, student=student.user, course=course,
                granted_by=admin.user, expires_at=timezone.now() + timedelta(hours=1))
        for profile in (student, teacher, admin):
            request = self.factory.get('/api/student-profile/reports/')
            force_authenticate(request, user=profile.user)
            response = StudentProfileReportView.as_view()(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row['user_id'] for row in response.data], [profile.user_id])
            self.assertEqual(response.data[0]['raw_interview'], [])
            for target in (profile, student, other):
                for course_id in (None, course.pk, denied.pk):
                    params = {'student_id': target.user_id}
                    if course_id is not None:
                        params['course'] = course_id
                    request = self.factory.get('/api/student-profile/review/', params)
                    force_authenticate(request, user=profile.user)
                    response = StudentProfileReportReviewView.as_view()(request)
                    if profile is student:
                        expected = 403
                    elif target == profile or target == student and course_id == course.pk:
                        expected = 200
                    else:
                        expected = 404
                    self.assertEqual(response.status_code, expected, (profile.user.role, target.pk, course_id))
                    self.assertNotIn('Hidden@example.invalid', json.dumps(response.data))
        report = StudentProfileReport.objects.get(profile=student)
        with patch.object(report, 'read_protected', side_effect=AssertionError('unexpected raw read')):
            self.assertEqual(StudentProfileReportSerializer(report).data['raw_interview'], [])
        CourseDataGrant.objects.filter(actor=teacher.user).update(active=False)
        request = self.factory.get('/api/student-profile/review/', {'student_id': student.user_id, 'course': course.pk})
        force_authenticate(request, user=teacher.user)
        self.assertEqual(StudentProfileReportReviewView.as_view()(request).status_code, 404)

    def test_admin_scope_and_forms_do_not_expose_or_overwrite_interview(self):
        owner = self.profile('profile-admin-owner', role='admin', is_staff=True, is_superuser=True)
        other = self.profile('profile-admin-other')
        own_interview = OnboardingInterview.objects.create(profile=owner, answers={'1': 'Admin@example.invalid'})
        OnboardingInterview.objects.create(profile=other, answers={'1': 'Other@example.invalid'})
        own_report = StudentProfileReport.objects.create(profile=owner, raw_interview=[{'answer': 'Admin@example.invalid'}])
        StudentProfileReport.objects.create(profile=other, raw_interview=[{'answer': 'Other@example.invalid'}])
        request = RequestFactory().get('/admin/student_profiles/onboardinginterview/')
        request.user = owner.user
        for model, admin_type, obj, field in (
            (OnboardingInterview, OnboardingInterviewAdmin, own_interview, 'answers'),
            (StudentProfileReport, StudentProfileReportAdmin, own_report, 'raw_interview'),
        ):
            model_admin = admin_type(model, AdminSite())
            self.assertEqual(list(model_admin.get_queryset(request)), [obj])
            self.assertNotIn(field, model_admin.get_form(request, obj).base_fields)
            self.assertEqual(list(model_admin.formfield_for_foreignkey(model._meta.get_field('profile'), request).queryset), [owner])

    def test_bulk_sql_and_schema_rollback_refuse_sealed_plaintext_loss(self):
        profile = self.profile('profile-write-guards')
        interview = OnboardingInterview.objects.create(profile=profile, answers={'1': 'Guard@example.invalid'})
        with self.assertRaisesRegex(RuntimeError, 'FIELD_UPDATE'):
            OnboardingInterview.objects.filter(pk=interview.pk).update(answers={'1': 'Changed@example.invalid'})
        interview.answers = {'1': 'Changed@example.invalid'}
        with self.assertRaisesRegex(RuntimeError, 'FIELD_BULK_UPDATE'):
            OnboardingInterview.objects.bulk_update([interview], ['answers'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE student_profiles_onboardinginterview SET answers=%s::jsonb WHERE id=%s',
                    [json.dumps({'1': 'Changed@example.invalid'}), interview.pk])
        migration = import_module('student_profiles.migrations.0010_profile_field_envelopes')
        with self.assertRaisesRegex(RuntimeError, 'SEALED_FIELD_SCHEMA_ROLLBACK_REFUSED'):
            migration.refuse_sealed_rollback(apps, SimpleNamespace(connection=connection))
