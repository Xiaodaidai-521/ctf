from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from users.models import CTFUser
from challenges.models import Category, Challenge
from .models import ExamRecord, PracticeExam, PracticeExamQuestion, TheoryExam, TheoryExamQuestion, TheoryQuestion
from .serializers import SubmitAnswerSerializer


class ExamBoundaryRegressionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = CTFUser.objects.create_user(username='audit-examinee')
        self.admin = CTFUser.objects.create_user(username='audit-exam-admin', is_staff=True)
        self.practice = PracticeExam.objects.create(title='Published practice', status='published', created_by=self.admin, easy_count=1, medium_count=0, hard_count=0)
        self.theory = TheoryExam.objects.create(title='Published theory', status='published', created_by=self.admin)
        self.draft = TheoryExam.objects.create(title='Draft theory', created_by=self.admin)
        category = Category.objects.create(name='audit-web')
        self.challenge = Challenge.objects.create(title='Exam challenge', category=category, difficulty='easy', score=10, flag='flag{audit}')

    def test_anonymous_can_read_only_published_exam_lists(self):
        for endpoint in ('practice-exams', 'theory-exams'):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(f'/api/exams/{endpoint}/')
                self.assertEqual(response.status_code, 200)
                self.assertTrue(all(row['status'] == 'published' for row in response.data['results']))

    def test_question_generation_requires_admin(self):
        for actor in (None, self.student):
            self.client.force_authenticate(actor)
            response = self.client.post(f'/api/exams/practice-exams/{self.practice.pk}/generate_questions/', {}, format='json')
            self.assertEqual(response.status_code, 403)

    def test_admin_generates_correctly_typed_questions_and_replaces_old_set(self):
        self.client.force_authenticate(self.admin)
        for _ in range(2):
            response = self.client.post(f'/api/exams/practice-exams/{self.practice.pk}/generate_questions/', {}, format='json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['total'], 1)
            self.assertEqual(list(self.practice.exam_questions.values_list('challenge_id', flat=True)), [self.challenge.pk])

    def test_exam_creation_binds_authenticated_admin(self):
        self.client.force_authenticate(self.admin)
        for endpoint, model in (('practice-exams', PracticeExam), ('theory-exams', TheoryExam)):
            with self.subTest(endpoint=endpoint):
                response = self.client.post(f'/api/exams/{endpoint}/', {'title': 'Created in audit', 'status': 'draft'}, format='json')
                self.assertEqual(response.status_code, 201)
                self.assertEqual(model.objects.get(pk=response.data['id']).created_by_id, self.admin.pk)

    def test_score_and_owner_cannot_be_overwritten_by_record_patch(self):
        record = ExamRecord.objects.create(user=self.student, theory_exam=self.theory, exam_type='theory', total_points=100)
        self.client.force_authenticate(self.student)
        response = self.client.patch(f'/api/exams/records/{record.pk}/', {'user': self.admin.pk, 'score': 100, 'status': 'completed', 'is_passed': True}, format='json')
        self.assertEqual(response.status_code, 405)
        record.refresh_from_db()
        self.assertEqual(record.user_id, self.student.pk)
        self.assertIsNone(record.score)
        self.assertEqual(record.status, 'in_progress')

    def test_record_creation_rejects_unpublished_or_mismatched_exam(self):
        self.client.force_authenticate(self.student)
        for payload in ({'exam_type': 'theory', 'theory_exam': self.draft.pk}, {'exam_type': 'practice', 'theory_exam': self.theory.pk}, {'exam_type': 'theory'}, {'exam_type': 'theory', 'theory_exam': self.theory.pk, 'practice_exam': self.practice.pk}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post('/api/exams/records/', payload, format='json').status_code, 400)

    def test_answer_validator_rejects_two_question_ids_and_negative_duration(self):
        for fields in ({'theory_question_id': 1, 'practice_question_id': 1}, {'theory_question_id': 1, 'time_spent': -1}):
            serializer = SubmitAnswerSerializer(data={'exam_record_id': 1, 'user_answer': 'A', **fields})
            self.assertFalse(serializer.is_valid(), fields)

    def test_non_started_record_cannot_submit_or_answer(self):
        record = ExamRecord.objects.create(user=self.student, practice_exam=self.practice, exam_type='practice', status='pending')
        question = PracticeExamQuestion.objects.create(exam=self.practice, challenge=self.challenge)
        self.client.force_authenticate(self.student)
        answer = self.client.post(f'/api/exams/records/{record.pk}/answer/', {'exam_record_id': record.pk, 'practice_question_id': question.pk, 'user_answer': 'flag{audit}'}, format='json')
        self.assertEqual(answer.status_code, 400)
        submit = self.client.post(f'/api/exams/records/{record.pk}/submit/', {}, format='json')
        self.assertEqual(submit.status_code, 400)
        self.assertFalse(record.answers.exists())

    def test_practice_correct_answer_is_saved_with_request_metadata(self):
        record = ExamRecord.objects.create(user=self.student, practice_exam=self.practice, exam_type='practice', total_points=10)
        question = PracticeExamQuestion.objects.create(exam=self.practice, challenge=self.challenge)
        self.client.force_authenticate(self.student)
        response = self.client.post(f'/api/exams/records/{record.pk}/answer/', {'exam_record_id': record.pk, 'practice_question_id': question.pk, 'user_answer': 'flag{audit}'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_correct'])
        self.assertEqual(record.answers.get().points_earned, 10)

    def test_student_cannot_read_answer_explanations_from_question_endpoints(self):
        question = TheoryQuestion.objects.create(question_type='single_choice', category='web', difficulty='easy', question_text='Choose', correct_answer='A', explanation='Correct answer is A')
        TheoryExamQuestion.objects.create(exam=self.theory, question=question)
        self.client.force_authenticate(self.student)
        self.assertNotIn('explanation', self.client.get(f'/api/exams/theory-questions/{question.pk}/').data)
        response = self.client.get(f'/api/exams/theory-exams/{self.theory.pk}/questions/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('explanation', response.data[0]['question_detail'])
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f'/api/exams/theory-exams/{self.theory.pk}/questions/').data[0]['question_detail']['explanation'], 'Correct answer is A')

    def test_expired_exam_rejects_new_answers_but_can_settle_saved_answers(self):
        record = ExamRecord.objects.create(user=self.student, practice_exam=self.practice, exam_type='practice', total_points=10)
        ExamRecord.objects.filter(pk=record.pk).update(start_time=timezone.now() - timedelta(minutes=self.practice.duration + 1))
        question = PracticeExamQuestion.objects.create(exam=self.practice, challenge=self.challenge)
        self.client.force_authenticate(self.student)
        response = self.client.post(f'/api/exams/records/{record.pk}/answer/', {'exam_record_id': record.pk, 'practice_question_id': question.pk, 'user_answer': 'flag{audit}'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'exam_time_expired')
        self.assertFalse(record.answers.exists())
        self.assertEqual(self.client.post(f'/api/exams/records/{record.pk}/submit/', {}, format='json').status_code, 200)

    def test_published_exam_rejects_duplicate_start_and_excess_attempts(self):
        self.theory.max_attempts = 1
        self.theory.save(update_fields=['max_attempts'])
        self.client.force_authenticate(self.student)
        payload = {'exam_type': 'theory', 'theory_exam': self.theory.pk}
        created = self.client.post('/api/exams/records/', payload, format='json')
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.post('/api/exams/records/', payload, format='json').status_code, 400)
        ExamRecord.objects.filter(pk=created.data['id']).update(status='completed')
        self.assertEqual(self.client.post('/api/exams/records/', payload, format='json').status_code, 400)

    def test_admin_role_without_staff_flag_can_manage_exams(self):
        administrator = CTFUser.objects.create_user(username='audit-role-admin', role='admin', is_staff=False)
        self.client.force_authenticate(administrator)
        response = self.client.post(f'/api/exams/practice-exams/{self.practice.pk}/generate_questions/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f'/api/exams/theory-exams/{self.draft.pk}/').status_code, 200)

    def seed_theory_pool(self):
        for kind, count in (('single_choice', 30), ('multiple_choice', 20), ('true_false', 20)):
            for index in range(count):
                TheoryQuestion.objects.create(question_type=kind, category='web', difficulty='easy', question_text=f'{kind} {index}', correct_answer='A')

    def test_insufficient_practice_pool_does_not_leave_partial_theory_exam(self):
        self.seed_theory_pool()
        self.client.force_authenticate(self.student)
        theory_count = TheoryExam.objects.count()
        response = self.client.post('/api/exams/records/start_comprehensive_exam/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TheoryExam.objects.count(), theory_count)
        self.assertFalse(ExamRecord.objects.filter(user=self.student).exists())

    def test_comprehensive_exam_is_paired_private_and_starts_practice_after_theory(self):
        self.seed_theory_pool()
        for difficulty, count in (('easy', 2), ('medium', 2), ('hard', 1)):
            for index in range(count):
                Challenge.objects.create(title=f'{difficulty} {index}', category=self.challenge.category, difficulty=difficulty, score=10, flag='flag{test}')
        self.client.force_authenticate(self.student)
        response = self.client.post('/api/exams/records/start_comprehensive_exam/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        theory = response.data['theory_record']
        practice = response.data['practice_record']
        record = ExamRecord.objects.get(pk=theory['id'])
        self.assertEqual(record.theory_exam.exam_questions.count(), 70)
        self.assertEqual(self.client.get(f'/api/exams/theory-exams/{theory["exam_id"]}/').status_code, 200)
        self.assertEqual(self.client.get(f'/api/exams/practice-exams/{practice["exam_id"]}/').status_code, 200)
        question = record.theory_exam.exam_questions.filter(question__question_type='single_choice').first()
        answered = self.client.post(f'/api/exams/records/{record.pk}/answer/', {'exam_record_id': record.pk, 'theory_question_id': question.question_id, 'user_answer': 'A'}, format='json')
        self.assertEqual(answered.status_code, 200)
        self.assertTrue(answered.data['saved'])
        self.assertNotIn('is_correct', answered.data)
        submitted = self.client.post(f'/api/exams/records/{record.pk}/submit/', {}, format='json')
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['practice_record_id'], practice['id'])
        self.assertEqual(ExamRecord.objects.get(pk=practice['id']).status, 'in_progress')
        self.client.force_authenticate(self.admin)
        other_student = CTFUser.objects.create_user(username='audit-other-examinee')
        self.client.force_authenticate(other_student)
        self.assertEqual(self.client.get(f'/api/exams/theory-exams/{theory["exam_id"]}/questions/').status_code, 404)
