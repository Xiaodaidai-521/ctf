"""HTTP regressions for exam history, deadlines, secrecy and encrypted resume."""
from datetime import timedelta
import secrets

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from challenges.models import Category, Challenge
from data_security.adapters.persistence import fields
from data_security.runtime.crypto import RuntimeCipher
from data_security.runtime.fields import RuntimeFieldStorage
from users.models import CTFUser
from .models import ExamAnswer, ExamRecord, PracticeExam, PracticeExamQuestion, TheoryExam, TheoryExamQuestion, TheoryQuestion
from .serializers import ExamRecordSerializer


class ExamLogicFixTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = CTFUser.objects.create_user(username='fix-exam-admin', is_staff=True)
        self.student = CTFUser.objects.create_user(username='fix-exam-student')
        self.other = CTFUser.objects.create_user(username='fix-exam-other')
        self.client.force_authenticate(self.student)
        self.category = Category.objects.create(name='fix-exam-category')
        self.theory = TheoryExam.objects.create(
            title='Fix theory', status='published', created_by=self.admin, total_points=10,
        )
        self.question = TheoryQuestion.objects.create(
            question_type='multiple_choice', question_text='Choose A and B',
            options=['A', 'B', 'C'], correct_answer='A,B',
        )
        TheoryExamQuestion.objects.create(exam=self.theory, question=self.question, points=10)
        self.record = ExamRecord.objects.create(
            user=self.student, theory_exam=self.theory, exam_type='theory',
            total_points=10, total_questions=1,
        )

    def answer(self, value, record=None, **question):
        record = record or self.record
        question = question or {'theory_question_id': self.question.pk}
        return self.client.post(f'/api/exams/records/{record.pk}/answer/', {
            'exam_record_id': record.pk, 'user_answer': value, **question,
        }, format='json')

    def submit(self, record=None):
        record = record or self.record
        return self.client.post(f'/api/exams/records/{record.pk}/submit/', {}, format='json')

    def practice(self, **changes):
        return PracticeExam.objects.create(
            title='Fix practice', created_by=self.admin, status='published',
            easy_count=changes.pop('easy_count', 1), medium_count=0, hard_count=0, **changes,
        )

    def challenge(self, **changes):
        defaults = {'title': 'Fix challenge', 'category': self.category,
                    'difficulty': 'easy', 'score': 10, 'flag': 'flag{fix}'}
        defaults.update(changes)
        return Challenge.objects.create(**defaults)

    def test_theory_save_and_every_record_read_hide_grading_until_submit(self):
        for value in ('C', 'A,B'):
            response = self.answer(value)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data['saved'])
            self.assertNotIn('is_correct', response.data)
            self.assertNotIn('points_earned', response.data)
        self.assertEqual(self.record.answers.count(), 1)
        for endpoint in (f'{self.record.pk}/result/', f'{self.record.pk}/', '', 'my_history/'):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(f'/api/exams/records/{endpoint}')
                self.assertEqual(response.status_code, 200)
                data = response.data
                if 'results' in data: data = data['results'][0]
                elif 'records' in data: data = data['records'][0]
                self.assertIsNone(data['score'])
                self.assertIsNone(data['correct_count'])
                self.assertIsNone(data['is_passed'])
                self.assertNotIn('is_correct', data['answers'][0])
                self.assertNotIn('points_earned', data['answers'][0])
                self.assertEqual(data['answers'][0]['user_answer'], 'A,B')
        completed = self.submit()
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(float(completed.data['score']), 10)
        self.assertTrue(completed.data['answers'][0]['is_correct'])

    def test_clear_saved_multiple_choice_replaces_server_answer_and_scores_zero(self):
        self.assertEqual(self.answer('A,B').status_code, 200)
        self.assertEqual(self.answer('').status_code, 200)
        answer = self.record.answers.get()
        self.assertEqual(answer.read_protected('user_answer'), '')
        self.assertFalse(answer.is_correct)
        self.assertEqual(float(self.submit().data['score']), 0)

    def test_blank_correct_answer_does_not_grade_a_blank_submission_as_correct(self):
        self.question.correct_answer = ''
        self.question.save(update_fields=['correct_answer'])
        self.assertEqual(self.answer('').status_code, 200)
        self.assertFalse(self.record.answers.get().is_correct)

    def test_deadline_rejects_new_answers_and_settles_previously_saved_answer(self):
        self.assertEqual(self.answer('A,B').status_code, 200)
        ExamRecord.objects.filter(pk=self.record.pk).update(
            start_time=timezone.now() - timedelta(minutes=self.theory.duration),
        )
        late = self.answer('C')
        self.assertEqual(late.status_code, 400)
        self.assertEqual(late.data['code'], 'exam_time_expired')
        self.assertEqual(float(self.submit().data['score']), 10)

    def test_encrypted_answer_restores_only_for_owner_and_ciphertext_stays_at_rest(self):
        self.addCleanup(fields.bind_field_storage, fields._adapter)
        fields.bind_field_storage(RuntimeFieldStorage(RuntimeCipher(secrets.token_bytes(64))))
        response = self.answer('A,B')
        self.assertEqual(response.status_code, 200)
        answer = self.record.answers.get()
        self.assertEqual(answer.security_state, 'sealed-v1')
        self.assertEqual(answer.user_answer, '')
        detail = self.client.get(f'/api/exams/records/{self.record.pk}/result/')
        self.assertEqual(detail.data['answers'][0]['user_answer'], 'A,B')
        self.assertNotIn('is_correct', detail.data['answers'][0])
        self.assertEqual(ExamRecordSerializer(self.record).data['answers'][0]['user_answer'], '[REDACTED]')
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/exams/records/{self.record.pk}/result/').status_code, 404)

    def test_pending_practice_clock_starts_at_theory_submission(self):
        suffix = 'fix-pair'
        self.theory.title = f'综合考试-理论部分-{suffix}'
        self.theory.save(update_fields=['title'])
        practice = self.practice()
        practice.title = f'综合考试-实战部分-{suffix}'
        practice.save(update_fields=['title'])
        question = PracticeExamQuestion.objects.create(exam=practice, challenge=self.challenge())
        pending = ExamRecord.objects.create(
            user=self.student, practice_exam=practice, exam_type='practice', status='pending',
        )
        old = timezone.now() - timedelta(minutes=181)
        ExamRecord.objects.filter(pk__in=(pending.pk, self.record.pk)).update(start_time=old)
        self.assertIsNone(self.client.get(f'/api/exams/records/{pending.pk}/result/').data['start_time'])
        before = timezone.now()
        self.assertEqual(self.submit().status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'in_progress')
        self.assertGreaterEqual(pending.start_time, before)
        response = self.answer('flag{fix}', pending, practice_question_id=question.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_correct'])

    def test_used_practice_cannot_regenerate_or_delete_and_history_is_preserved(self):
        practice = self.practice()
        question = PracticeExamQuestion.objects.create(exam=practice, challenge=self.challenge())
        used = ExamRecord.objects.create(
            user=self.student, practice_exam=practice, exam_type='practice', score=10,
        )
        answer = ExamAnswer.objects.create(exam_record=used, practice_question=question,
                                          user_answer='flag{fix}', is_correct=True, points_earned=10)
        self.client.force_authenticate(self.admin)
        for state in ('pending', 'in_progress', 'completed'):
            ExamRecord.objects.filter(pk=used.pk).update(status=state)
            response = self.client.post(f'/api/exams/practice-exams/{practice.pk}/generate_questions/', {}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertTrue(ExamAnswer.objects.filter(pk=answer.pk).exists())
            self.assertEqual(practice.exam_questions.count(), 1)
        self.assertEqual(self.client.delete(f'/api/exams/practice-exams/{practice.pk}/').status_code, 400)
        used.refresh_from_db()
        self.assertEqual(used.score, 10)

    def test_ungradable_challenges_are_excluded_and_insufficient_pool_preserves_paper(self):
        practice = self.practice()
        valid = self.challenge()
        self.challenge(title='Free practice', submission_mode='practice', flag='')
        self.challenge(title='Missing Flag', submission_mode='flag', flag='   ')
        self.client.force_authenticate(self.admin)
        endpoint = f'/api/exams/practice-exams/{practice.pk}/generate_questions/'
        self.assertEqual(self.client.post(endpoint, {}, format='json').status_code, 200)
        self.assertEqual(list(practice.exam_questions.values_list('challenge_id', flat=True)), [valid.pk])
        practice.easy_count = 2
        practice.save(update_fields=['easy_count'])
        self.assertEqual(self.client.post(endpoint, {}, format='json').status_code, 400)
        self.assertEqual(practice.exam_questions.count(), 1)

    def test_sealed_flags_remain_eligible_without_relying_on_empty_public_column(self):
        self.addCleanup(fields.bind_field_storage, fields._adapter)
        fields.bind_field_storage(RuntimeFieldStorage(RuntimeCipher(secrets.token_bytes(64))))
        valid = self.challenge()
        self.challenge(title='Sealed empty Flag', flag='')
        self.assertEqual(valid.security_state, 'sealed-v1')
        self.assertEqual(valid.flag, '')
        practice = self.practice()
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/exams/practice-exams/{practice.pk}/generate_questions/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(practice.exam_questions.values_list('challenge_id', flat=True)), [valid.pk])

    def test_generated_total_points_matches_question_scores_and_full_score_normalizes_to_100(self):
        practice = self.practice(easy_count=2, total_points=100)
        self.challenge(title='Ten point challenge', score=10)
        self.challenge(title='Twenty point challenge', score=20)
        self.client.force_authenticate(self.admin)
        generated = self.client.post(f'/api/exams/practice-exams/{practice.pk}/generate_questions/', {}, format='json')
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.data['total_points'], 30)
        practice.refresh_from_db()
        self.assertEqual(practice.total_points, 30)
        self.client.force_authenticate(self.student)
        started = self.client.post('/api/exams/records/', {
            'exam_type': 'practice', 'practice_exam': practice.pk,
        }, format='json')
        self.assertEqual(started.status_code, 201)
        record = ExamRecord.objects.get(pk=started.data['id'])
        self.assertEqual(record.total_points, 30)
        for question in practice.exam_questions.all():
            answer = self.answer('flag{fix}', record, practice_question_id=question.pk)
            self.assertEqual(answer.status_code, 200)
            self.assertTrue(answer.data['is_correct'])
        submitted = self.submit(record)
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(float(submitted.data['score']), 30)
        self.assertEqual(submitted.data['total_points'], 30)
        self.assertEqual(self.client.get('/api/exams/records/statistics/').data['best_score'], 100)

    def test_practice_question_api_returns_real_description_field(self):
        practice = self.practice()
        challenge = self.challenge(description='<p>Actual environment and attachments</p>')
        PracticeExamQuestion.objects.create(exam=practice, challenge=challenge)
        response = self.client.get(f'/api/exams/practice-exams/{practice.pk}/questions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['challenge'], challenge.pk)
        self.assertEqual(response.data[0]['challenge_description'], challenge.description)
