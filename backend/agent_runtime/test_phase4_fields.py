"""Approved memory and judging fields, exercised on isolated synthetic PostgreSQL."""
import importlib
import json
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from agent_runtime.memory import UserMemoryStore
from agent_runtime.models import AgentRun, UserMemory
from agent_runtime.serializers import AgentRunSerializer
from agent_runtime.state_store import AgentRunStateStore
from challenges.admin import ChallengeAdmin, ChallengeSolutionAdmin
from challenges.models import Category, Challenge, ChallengeSolution
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.fields import bind_field_storage
from data_security.tests.phase4_fixtures import field_configuration
from exams.models import ExamAnswer, ExamRecord, TheoryExam, TheoryExamQuestion, TheoryQuestion
from exams.serializers import ExamAnswerSerializer, TheoryQuestionCreateSerializer
from exams.views import ExamRecordViewSet
from submissions.models import Submission
from submissions.serializers import SubmissionSerializer
from users.models import CTFUser


class MemoryJudgingFieldTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        fixture = field_configuration()
        path, *_ = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.components = assemble(config_path=path)
        bind_field_storage(self.components['fields'])
        self.addCleanup(bind_field_storage, None)
        self.user = CTFUser.objects.create_user(username='synthetic-judging-user')
        self.category = Category.objects.create(name='Synthetic judging')

    def test_hundred_values_in_each_of_seven_fields(self):
        record = ExamRecord.objects.create(user=self.user, exam_type='theory')
        originals = []
        for number in range(100):
            text = f'Synthetic-answer-{number}@example.invalid'
            tree = {'note': text, 'score': number, 'items': []}
            memory = UserMemory.objects.create(user=self.user, memory_type='fact',
                memory_key=f'synthetic-{number}', memory_value=tree, metadata=tree)
            challenge = Challenge.objects.create(title=f'Synthetic challenge {number}',
                category=self.category, difficulty='easy', score=10, flag=text)
            solution = ChallengeSolution.objects.create(challenge=challenge, content=text, hint_map='')
            question = TheoryQuestion.objects.create(question_type='single_choice',
                question_text=f'Synthetic question {number}', correct_answer=text)
            answer = ExamAnswer.objects.create(exam_record=record, theory_question=question, user_answer=text)
            submission = Submission.objects.create(user=self.user, challenge=challenge,
                flag=text, ip_address='192.0.2.5', user_agent='synthetic')
            for obj, name, expected in ((memory, 'memory_value', tree), (memory, 'metadata', tree),
                    (challenge, 'flag', text), (solution, 'content', text),
                    (question, 'correct_answer', text), (answer, 'user_answer', text), (submission, 'flag', text)):
                self.assertEqual(obj.read_protected(name), expected)
                self.assertEqual(getattr(obj, name), {} if isinstance(expected, dict) else '')
            self.assertTrue(submission.is_correct)
            originals.append(text)
        with connection.cursor() as cursor:
            for model in (UserMemory, Challenge, ChallengeSolution, TheoryQuestion, ExamAnswer, Submission):
                table = connection.ops.quote_name(model._meta.db_table)
                cursor.execute(f'SELECT row_to_json(t)::text FROM {table} t')
                copied_rows = json.dumps(cursor.fetchall())
                self.assertTrue(all(value not in copied_rows for value in originals), model._meta.label)

    def test_memory_updates_and_user_scope(self):
        store = UserMemoryStore(user=self.user)
        tree = {'note': 'Memory@example.invalid'}
        memory = store.remember(memory_type='fact', memory_key='scope', memory_value=tree,
                                metadata={'note': 'Metadata@example.invalid'})
        self.assertEqual(store.recall(memory_type='fact', memory_key='scope')['memory_value'], tree)
        self.assertEqual(store.list_memories()[0]['metadata'], {'note': 'Metadata@example.invalid'})
        changed = store.remember(memory_type='fact', memory_key='scope', memory_value={'count': 2})
        self.assertEqual(memory.pk, changed.pk)
        self.assertEqual(store.recall(memory_type='fact', memory_key='scope')['memory_value'], {'count': 2})
        other = CTFUser.objects.create_user(username='synthetic-other-memory')
        self.assertIsNone(UserMemoryStore(user=other).recall(memory_type='fact', memory_key='scope'))

    def test_runtime_copies_store_only_protected_values(self):
        text = 'Runtime@example.invalid 192.0.2.7 4111111111111111'
        store = AgentRunStateStore()
        run = store.create_run(user=self.user, task_type='general', plan=[{'note': text}], current_step=text)
        store.record_tool_use(run, {'output': text})
        store.record_retrieval(run, [{'text': text}])
        store.record_intermediate(run, {'note': text, 'score': 17})
        store.complete(run, final_result={'note': text}, verification_result={'note': text})
        store.fail(run, error_message=text)
        run.refresh_from_db()
        wire = json.dumps(AgentRunSerializer(run).data)
        for token in text.split():
            self.assertNotIn(token, wire)
        self.assertEqual(run.intermediate_result['score'], 17)
        self.assertEqual(run.security_envelopes, {})

    def test_sealed_answers_remain_internal_and_resaving_submission_preserves_judgment(self):
        challenge = Challenge.objects.create(title='Synthetic secret challenge', category=self.category,
            difficulty='easy', score=10, flag='flag{synthetic-answer}')
        solution = ChallengeSolution.objects.create(challenge=challenge, content='Solution@example.invalid')
        submission = Submission.objects.create(user=self.user, challenge=challenge,
            flag='flag{synthetic-answer}', ip_address='192.0.2.5', user_agent='synthetic')
        submission.refresh_from_db()
        submission.save()
        self.assertTrue(submission.is_correct)
        challenge.refresh_from_db()
        self.assertEqual(challenge.solve_count, 1)
        self.assertEqual(SubmissionSerializer(submission).data['flag'], '[REDACTED]')
        self.assertNotIn('Solution@example.invalid', solution.match_hint('no match'))
        self.assertIn('flag', ChallengeAdmin(Challenge, None).get_readonly_fields(None, challenge))
        self.assertIn('content', ChallengeSolutionAdmin(ChallengeSolution, None).get_readonly_fields(None, solution))

    def test_theory_judging_uses_explicit_answer_reads(self):
        exam = TheoryExam.objects.create(title='Synthetic exam', created_by=self.user, duration=30)
        record = ExamRecord.objects.create(user=self.user, exam_type='theory', theory_exam=exam)
        for kind, correct, submitted in (('single_choice', 'A', 'A'),
                ('multiple_choice', 'A,B', ' B,A '), ('true_false', 'true', 'TRUE')):
            question = TheoryQuestion.objects.create(question_type=kind, question_text='Synthetic?', correct_answer=correct)
            TheoryExamQuestion.objects.create(exam=exam, question=question, points=10)
            request = APIRequestFactory().post('/api/exams/records/answer/', {'exam_record_id': record.pk,
                'theory_question_id': question.pk, 'user_answer': submitted}, format='json')
            force_authenticate(request, user=self.user)
            response = ExamRecordViewSet.as_view({'post': 'answer'})(request, pk=record.pk)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data['is_correct'])
            answer = ExamAnswer.objects.get(pk=response.data['answer_id'])
            self.assertEqual(ExamAnswerSerializer(answer).data['user_answer'], '[REDACTED]')
            self.assertEqual(TheoryQuestionCreateSerializer(question).data['correct_answer'], '[REDACTED]')
            self.assertNotIn(submitted, str(answer))

    def test_reverse_schema_refuses_to_drop_sealed_storage(self):
        UserMemory.objects.create(user=self.user, memory_type='fact', memory_key='rollback', memory_value={})
        module = importlib.import_module('agent_runtime.migrations.0003_field_envelopes')
        with self.assertRaisesRegex(RuntimeError, 'SEALED_FIELD_SCHEMA_ROLLBACK_REFUSED'):
            module.refuse_sealed_rollback(apps, SimpleNamespace(connection=connection))
