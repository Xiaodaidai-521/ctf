from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from .gateway import AgentGateway
from .memory import UserMemoryStore
from .models import AgentRun, UserMemory
from .state_store import AgentRunStateStore


User = get_user_model()


class FakeLearningService:
    def __init__(self):
        self.last_context = {}

    async def chat_with_agent(self, agent_id, message, context=None, conversation_history=None):
        self.last_context = context or {}
        return {
            'agent_id': agent_id,
            'agent_name': 'Learning Tutor',
            'provider': 'test',
            'model': 'test-model',
            'content': f'Learning guidance for {message}: study SQL Injection [S2], review the module, and practice one lab next [S3].',
        }


class FailingLearningService:
    async def chat_with_agent(self, agent_id, message, context=None, conversation_history=None):
        raise RuntimeError('provider unavailable')


class UnalignedLearningService:
    async def chat_with_agent(self, agent_id, message, context=None, conversation_history=None):
        return {
            'agent_id': agent_id,
            'agent_name': 'Learning Tutor',
            'provider': 'test',
            'model': 'test-model',
            'content': 'This answer talks about unrelated cryptography trivia.',
        }


class RetryLearningService:
    def __init__(self):
        self.calls = []

    async def chat_with_agent(self, agent_id, message, context=None, conversation_history=None):
        self.calls.append(context or {})
        if len(self.calls) == 1:
            content = 'This answer talks about unrelated cryptography trivia.'
        else:
            content = (
                f'Learning guidance for {message}: review SQL Injection basics [S1], '
                'then practice one safe lab next.'
            )
        return {
            'agent_id': agent_id,
            'agent_name': 'Learning Tutor',
            'provider': 'test',
            'model': 'test-model',
            'content': content,
        }


class AlwaysUnalignedLearningService:
    def __init__(self):
        self.calls = []

    async def chat_with_agent(self, agent_id, message, context=None, conversation_history=None):
        self.calls.append(context or {})
        return {
            'agent_id': agent_id,
            'agent_name': 'Learning Tutor',
            'provider': 'test',
            'model': 'test-model',
            'content': 'This answer talks about unrelated cryptography trivia.',
        }


class AgentRunStateStoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='student', password='pass12345')
        self.store = AgentRunStateStore()

    def test_create_complete_and_query_run(self):
        run = self.store.create_run(
            user=self.user,
            task_type=AgentRun.TASK_LEARNING,
            plan=[{'name': 'call_learning_agent'}],
        )

        self.store.mark_running(run, current_step='call_learning_agent')
        self.store.record_tool_use(run, {'name': 'read_student_profile', 'status': 'success'})
        self.store.complete(
            run,
            final_result={'content': 'result'},
            verification_result={'passed': True},
        )

        saved = AgentRun.objects.get(id=run.id)
        self.assertEqual(saved.status, AgentRun.STATUS_COMPLETED)
        self.assertEqual(saved.current_step, 'completed')
        self.assertEqual(saved.used_tools[0]['name'], 'read_student_profile')
        self.assertEqual(saved.final_result['content'], 'result')
        self.assertTrue(saved.verification_result['passed'])

    def test_fail_run_records_error(self):
        run = self.store.create_run(user=self.user, task_type=AgentRun.TASK_LEARNING)

        self.store.fail(run, error_message='bad input')

        saved = AgentRun.objects.get(id=run.id)
        self.assertEqual(saved.status, AgentRun.STATUS_FAILED)
        self.assertEqual(saved.current_step, 'failed')
        self.assertEqual(saved.error_message, 'bad input')

    def test_record_intermediate_keeps_run_active(self):
        run = self.store.create_run(user=self.user, task_type=AgentRun.TASK_LEARNING)
        self.store.mark_running(run, current_step='call_learning_agent')

        self.store.record_intermediate(run, {'attempts': [{'name': 'initial'}]})

        saved = AgentRun.objects.get(id=run.id)
        self.assertEqual(saved.status, AgentRun.STATUS_RUNNING)
        self.assertEqual(saved.current_step, 'call_learning_agent')
        self.assertEqual(saved.intermediate_result['attempts'][0]['name'], 'initial')


class UserMemoryStoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='memory-user', password='pass12345')

    def test_memory_store_upserts_recalls_and_forgets(self):
        store = UserMemoryStore(user=self.user)

        store.remember(
            memory_type=UserMemory.MEMORY_TYPE_PREFERENCE,
            memory_key='learning_style',
            memory_value={'style': 'lab_first'},
        )
        store.remember(
            memory_type=UserMemory.MEMORY_TYPE_PREFERENCE,
            memory_key='learning_style',
            memory_value={'style': 'review_first'},
        )

        recalled = store.recall(
            memory_type=UserMemory.MEMORY_TYPE_PREFERENCE,
            memory_key='learning_style',
        )
        self.assertEqual(recalled['memory_value']['style'], 'review_first')
        self.assertEqual(len(store.list_memories(memory_type=UserMemory.MEMORY_TYPE_PREFERENCE)), 1)
        self.assertEqual(
            store.forget(
                memory_type=UserMemory.MEMORY_TYPE_PREFERENCE,
                memory_key='learning_style',
            ),
            1,
        )


class AgentGatewayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='learner', password='pass12345')

    def test_learning_task_wraps_existing_service_and_completes_run(self):
        gateway = AgentGateway(service=FakeLearningService())

        run = gateway.run_learning_task(user=self.user, message='SQL injection basics')

        self.assertEqual(run.status, AgentRun.STATUS_COMPLETED)
        self.assertEqual(run.task_type, AgentRun.TASK_LEARNING)
        self.assertEqual(run.final_result['agent_id'], 'tutor')
        self.assertIn('SQL injection basics', run.final_result['content'])
        self.assertTrue(run.verification_result['passed'])

    def test_learning_task_failure_is_recorded(self):
        gateway = AgentGateway(service=FailingLearningService())

        run = gateway.run_learning_task(user=self.user, message='SQL injection basics')

        self.assertEqual(run.status, AgentRun.STATUS_FAILED)
        self.assertEqual(run.error_message, 'provider unavailable')

    def test_learning_task_records_retrieved_docs_and_tool_usage(self):
        from learning_paths.models import KnowledgeConcept, LearningPath, PathModule, UserKnowledgeState
        from student_profiles.models import LearningPreference, StudentProfile

        profile = StudentProfile.objects.create(
            user=self.user,
            learning_goals='Improve Web exploitation basics.',
            self_assessed_skills={'web': 2, 'crypto': 1},
            onboarding_completed=True,
        )
        LearningPreference.objects.create(
            profile=profile,
            preferred_pace='self_paced',
            preferred_modality=['text', 'lab'],
            daily_study_hours=1.5,
        )
        concept = KnowledgeConcept.objects.create(
            name='SQL Injection',
            slug='sql-injection',
            description='SQL injection fundamentals',
            concept_type='vul',
            difficulty_level=2,
        )
        UserKnowledgeState.objects.create(
            user=self.user,
            concept=concept,
            mastery_level=0.2,
            recall_probability=0.4,
            lab_attempts=3,
            lab_successes=1,
            recommended_intervention='Review query parameter handling.',
            struggle_indicators={'syntax': 'needs_practice'},
        )
        learning_path = LearningPath.objects.create(
            title='Web Security Basics',
            slug='web-security-basics',
            description='Learn HTTP, forms, and SQL injection safely.',
            difficulty='AP',
            estimated_hours=6,
            is_published=True,
        )
        PathModule.objects.create(
            learning_path=learning_path,
            title='SQL Injection Introduction',
            description='Understand inputs and query construction.',
            module_type='theory',
            content='Use parameterized queries and inspect request flow.',
            order=1,
        )
        service = FakeLearningService()
        gateway = AgentGateway(service=service)

        run = gateway.run_learning_task(user=self.user, message='How should I study SQL injection?')

        self.assertEqual(run.status, AgentRun.STATUS_COMPLETED)
        self.assertEqual(
            [tool['name'] for tool in run.used_tools],
            [
                'read_student_profile',
                'read_user_knowledge_state',
                'read_learning_path_modules',
            ],
        )
        self.assertTrue(all(tool['status'] == 'success' for tool in run.used_tools))
        source_types = {doc['source_type'] for doc in run.retrieved_docs}
        self.assertIn('student_profile', source_types)
        self.assertIn('user_knowledge_state', source_types)
        self.assertIn('learning_path', source_types)
        self.assertIn('Use the following platform learning context', service.last_context['knowledge_context'])
        self.assertIn('[S1]', service.last_context['knowledge_context'])
        self.assertIn('Available source references', service.last_context['agent_task_instruction'])
        self.assertIn('[S1]', service.last_context['agent_task_instruction'])
        self.assertIn('SQL Injection', service.last_context['knowledge_context'])
        self.assertTrue(all(doc.get('source_ref') for doc in run.retrieved_docs))
        checks = {check['name']: check for check in run.verification_result['checks']}
        self.assertEqual(checks['evidence_alignment']['citation_mode'], 'explicit_source_ref')

    def test_learning_task_records_failed_verification_when_answer_ignores_sources(self):
        from learning_paths.models import KnowledgeConcept, UserKnowledgeState

        concept = KnowledgeConcept.objects.create(
            name='SQL Injection',
            slug='sql-injection-failed',
            description='SQL injection fundamentals',
            concept_type='vul',
            difficulty_level=2,
        )
        UserKnowledgeState.objects.create(
            user=self.user,
            concept=concept,
            mastery_level=0.2,
            recall_probability=0.4,
        )
        gateway = AgentGateway(service=UnalignedLearningService())

        run = gateway.run_learning_task(user=self.user, message='How should I study SQL injection?')

        self.assertEqual(run.status, AgentRun.STATUS_COMPLETED)
        self.assertFalse(run.verification_result['passed'])
        checks = {check['name']: check for check in run.verification_result['checks']}
        self.assertFalse(checks['evidence_alignment']['passed'])
        self.assertFalse(checks['actionable_learning_advice']['passed'])
        self.assertIn('cite at least one valid source reference', checks['evidence_alignment']['remediation'])
        self.assertIn('concrete next learning action', checks['actionable_learning_advice']['remediation'])

    def test_learning_task_retries_once_when_verification_fails(self):
        from learning_paths.models import KnowledgeConcept, UserKnowledgeState

        concept = KnowledgeConcept.objects.create(
            name='SQL Injection',
            slug='sql-injection-retry',
            description='SQL injection fundamentals',
            concept_type='vul',
            difficulty_level=2,
        )
        UserKnowledgeState.objects.create(
            user=self.user,
            concept=concept,
            mastery_level=0.2,
            recall_probability=0.4,
        )
        service = RetryLearningService()
        gateway = AgentGateway(service=service)

        run = gateway.run_learning_task(user=self.user, message='How should I study SQL injection?')

        self.assertEqual(run.status, AgentRun.STATUS_COMPLETED)
        self.assertEqual(len(service.calls), 2)
        self.assertTrue(run.verification_result['passed'])
        self.assertIn('attempts', run.intermediate_result)
        self.assertFalse(run.intermediate_result['attempts'][0]['verification_result']['passed'])
        self.assertIn('Revise the previous learning answer', service.calls[1]['agent_task_instruction'])
        self.assertIn('[S1]', run.final_result['content'])

    def test_learning_task_completes_with_failed_verification_after_retry(self):
        from learning_paths.models import KnowledgeConcept, UserKnowledgeState

        concept = KnowledgeConcept.objects.create(
            name='SQL Injection',
            slug='sql-injection-retry-failed',
            description='SQL injection fundamentals',
            concept_type='vul',
            difficulty_level=2,
        )
        UserKnowledgeState.objects.create(
            user=self.user,
            concept=concept,
            mastery_level=0.2,
            recall_probability=0.4,
        )
        service = AlwaysUnalignedLearningService()
        gateway = AgentGateway(service=service)

        run = gateway.run_learning_task(user=self.user, message='How should I study SQL injection?')

        self.assertEqual(run.status, AgentRun.STATUS_COMPLETED)
        self.assertEqual(len(service.calls), 2)
        self.assertFalse(run.verification_result['passed'])
        self.assertFalse(run.intermediate_result['attempts'][0]['verification_result']['passed'])
        self.assertEqual(run.final_result['content'], 'This answer talks about unrelated cryptography trivia.')


class AgentRuntimeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='api-learner', password='pass12345')
        self.other_user = User.objects.create_user(username='other-learner', password='pass12345')
        self.client.force_authenticate(self.user)

    def _create_learning_context(self):
        from learning_paths.models import KnowledgeConcept, LearningPath, PathModule, UserKnowledgeState
        from student_profiles.models import StudentProfile

        StudentProfile.objects.create(
            user=self.user,
            learning_goals='Improve SQL injection fundamentals.',
            self_assessed_skills={'web': 2},
            onboarding_completed=True,
        )
        concept = KnowledgeConcept.objects.create(
            name='SQL Injection',
            slug='sql-injection-api',
            description='SQL injection fundamentals',
            concept_type='vul',
            difficulty_level=2,
        )
        UserKnowledgeState.objects.create(
            user=self.user,
            concept=concept,
            mastery_level=0.2,
            recall_probability=0.4,
            recommended_intervention='Practice request parameter review.',
        )
        learning_path = LearningPath.objects.create(
            title='Web Security Basics API',
            slug='web-security-basics-api',
            description='Learn SQL injection with guided modules.',
            difficulty='AP',
            estimated_hours=6,
            is_published=True,
        )
        PathModule.objects.create(
            learning_path=learning_path,
            title='SQL Injection Practice',
            description='Practice safe SQL injection analysis.',
            module_type='practice',
            content='Use safe labs only.',
            order=1,
        )

    def test_learning_run_api_creates_runtime_run(self):
        self._create_learning_context()

        with patch.object(AgentGateway, '_get_service', return_value=FakeLearningService()):
            response = self.client.post('/api/agent-runtime/learning-runs/', {
                'message': 'How should I study SQL injection?',
            }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['task_type'], AgentRun.TASK_LEARNING)
        self.assertEqual(response.data['status'], AgentRun.STATUS_COMPLETED)
        self.assertTrue(response.data['verification_result']['passed'])
        self.assertGreaterEqual(len(response.data['used_tools']), 3)
        source_types = {doc['source_type'] for doc in response.data['retrieved_docs']}
        self.assertIn('user_knowledge_state', source_types)
        self.assertIn('learning_path', source_types)
        self.assertTrue(all(doc.get('source_ref') for doc in response.data['retrieved_docs']))

    def test_run_detail_api_is_scoped_to_authenticated_user(self):
        own_run = AgentRun.objects.create(
            user=self.user,
            task_type=AgentRun.TASK_LEARNING,
            status=AgentRun.STATUS_COMPLETED,
            final_result={'content': 'own result'},
        )
        other_run = AgentRun.objects.create(
            user=self.other_user,
            task_type=AgentRun.TASK_LEARNING,
            status=AgentRun.STATUS_COMPLETED,
            final_result={'content': 'other result'},
        )

        own_response = self.client.get(f'/api/agent-runtime/runs/{own_run.id}/')
        other_response = self.client.get(f'/api/agent-runtime/runs/{other_run.id}/')

        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(own_response.data['id'], own_run.id)
        self.assertEqual(other_response.status_code, 404)

    def test_run_list_api_only_returns_authenticated_user_runs(self):
        AgentRun.objects.create(
            user=self.user,
            task_type=AgentRun.TASK_LEARNING,
            status=AgentRun.STATUS_COMPLETED,
            final_result={'content': 'own result'},
        )
        AgentRun.objects.create(
            user=self.other_user,
            task_type=AgentRun.TASK_LEARNING,
            status=AgentRun.STATUS_COMPLETED,
            final_result={'content': 'other result'},
        )

        response = self.client.get('/api/agent-runtime/runs/')

        self.assertEqual(response.status_code, 200)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['final_result']['content'], 'own result')
