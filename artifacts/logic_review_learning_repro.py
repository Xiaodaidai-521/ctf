"""Audit-only reproductions; these assert observed defects, not desired behavior.

Run with tools/full_audit/run.py and its owned synthetic PostgreSQL cluster.
No production database, business code, external service or container is changed.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import CTFUser
from challenges.models import Category, Challenge
from exams.models import (
    ExamRecord, PracticeExam, PracticeExamQuestion,
    TheoryExam, TheoryExamQuestion, TheoryQuestion,
)


class LearningAuditReproductions(TestCase):
    def setUp(self):
        self.admin = CTFUser.objects.create_user(username='review-admin', is_staff=True)
        self.student = CTFUser.objects.create_user(username='review-student')
        self.category = Category.objects.create(name='review-category')
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def challenge(self, **kwargs):
        return Challenge.objects.create(category=self.category, title='Review challenge',
                                        difficulty='easy', score=10, **kwargs)

    def answer(self, record, **data):
        return self.client.post(f'/api/exams/records/{record.pk}/answer/',
                                {'exam_record_id': record.pk, **data}, format='json')

    def test_comprehensive_practice_clock_already_expired_on_activation(self):
        for kind, count in [('single_choice', 30), ('multiple_choice', 20), ('true_false', 20)]:
            for index in range(count):
                TheoryQuestion.objects.create(question_type=kind, question_text=f'{kind}-{index}',
                                              correct_answer='A')
        for kind, count in [('easy', 3), ('medium', 2), ('hard', 1)]:
            for index in range(count):
                Challenge.objects.create(category=self.category, title=f'{kind}-{index}',
                                         difficulty=kind, score=10, flag='flag{review}')
        response = self.client.post('/api/exams/records/start_comprehensive_exam/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        theory = ExamRecord.objects.get(pk=response.data['theory_record']['id'])
        practice = ExamRecord.objects.get(pk=response.data['practice_record']['id'])
        original_start = practice.start_time
        future = original_start + timedelta(minutes=181)
        with patch('exams.views.timezone.now', return_value=future):
            submitted = self.client.post(f'/api/exams/records/{theory.pk}/submit/', {}, format='json')
            self.assertEqual(submitted.status_code, 200)
            practice.refresh_from_db()
            self.assertEqual(practice.status, 'in_progress')
            self.assertEqual(practice.start_time, original_start)
            question = practice.practice_exam.exam_questions.first()
            answered = self.answer(practice, practice_question_id=question.pk, user_answer='flag{review}')
            self.assertEqual(answered.status_code, 400)
            self.assertEqual(answered.data['code'], 'exam_time_expired')
        print('REPRO comprehensive: practice activated with original start; first answer HTTP 400 exam_time_expired')

    def test_theory_answer_flushed_at_deadline_is_rejected_then_settles_zero(self):
        exam = TheoryExam.objects.create(title='Review theory', created_by=self.admin, duration=1)
        question = TheoryQuestion.objects.create(question_type='single_choice', question_text='Pick A', correct_answer='A')
        TheoryExamQuestion.objects.create(exam=exam, question=question, points=10)
        record = ExamRecord.objects.create(user=self.student, theory_exam=exam, exam_type='theory', total_points=10)
        with patch('exams.views.timezone.now', return_value=record.start_time + timedelta(minutes=1)):
            answer = self.answer(record, theory_question_id=question.pk, user_answer='A')
            self.assertEqual(answer.status_code, 400)
            self.assertEqual(answer.data['code'], 'exam_time_expired')
            self.assertFalse(record.answers.exists())
            submitted = self.client.post(f'/api/exams/records/{record.pk}/submit/', {}, format='json')
            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(float(submitted.data['score']), 0)
        print('REPRO deadline: correct unsaved theory answer HTTP 400; settlement HTTP 200 score=0')

    def test_regenerating_practice_exam_deletes_completed_answer_history(self):
        challenge = self.challenge(flag='flag{review}')
        exam = PracticeExam.objects.create(title='Review practice', created_by=self.admin, status='published',
                                          easy_count=1, medium_count=0, hard_count=0)
        question = PracticeExamQuestion.objects.create(exam=exam, challenge=challenge)
        record = ExamRecord.objects.create(user=self.student, practice_exam=exam, exam_type='practice', total_points=10)
        self.assertEqual(self.answer(record, practice_question_id=question.pk, user_answer='flag{review}').status_code, 200)
        self.assertEqual(self.client.post(f'/api/exams/records/{record.pk}/submit/', {}, format='json').status_code, 200)
        self.assertEqual(record.answers.count(), 1)
        self.client.force_authenticate(self.admin)
        generated = self.client.post(f'/api/exams/practice-exams/{exam.pk}/generate_questions/', {}, format='json')
        self.assertEqual(generated.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.answers.count(), 0)
        self.assertEqual(float(record.score), 10)
        self.client.force_authenticate(self.student)
        result = self.client.get(f'/api/exams/records/{record.pk}/result/')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['answers'], [])
        print('REPRO regeneration: completed result keeps score=10 but answers change from 1 to 0')

    def test_practice_generator_selects_free_practice_without_a_gradable_flag(self):
        challenge = self.challenge(flag='', submission_mode='practice')
        exam = PracticeExam.objects.create(title='Review free practice', created_by=self.admin, status='published',
                                          easy_count=1, medium_count=0, hard_count=0)
        self.client.force_authenticate(self.admin)
        generated = self.client.post(f'/api/exams/practice-exams/{exam.pk}/generate_questions/', {}, format='json')
        self.assertEqual(generated.status_code, 200)
        question = exam.exam_questions.get()
        self.assertEqual(question.challenge_id, challenge.pk)
        self.client.force_authenticate(self.student)
        record = ExamRecord.objects.create(user=self.student, practice_exam=exam, exam_type='practice', total_points=10)
        answered = self.answer(record, practice_question_id=question.pk, user_answer='anything')
        self.assertEqual(answered.status_code, 200)
        self.assertFalse(answered.data['is_correct'])
        print('REPRO generator: accepts non-Flag free practice into a Flag-only exam; no gradable answer')
