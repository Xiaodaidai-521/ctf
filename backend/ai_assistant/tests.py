import asyncio
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from articles.models import Article, Category as ArticleCategory
from challenges.models import Category, Challenge
from legal_kb.models import LegalKnowledgeEmbedding
from legal_kb.services.hashing import sha256_text
from legal_kb.services.platform_indexing_service import PlatformContentIndexingService

from .models import AgentPreset, ChallengeKnowledgePack
from .service import (
    MultiAgentChatService,
    _build_question_prompt,
    _build_teaching_context_summary,
)
from .views import (
    _internal_request_context_from_request,
    _with_compatible_chat_response,
)


User = get_user_model()


class ChatResponseCompatibilityTests(TestCase):
    def test_response_adds_answer_and_typed_optional_fields_without_removing_legacy_fields(self):
        payload = {
            'mode': 'collaborative',
            'responses': [
                {'agent_id': 'analyst', 'content': 'analysis'},
                {'agent_id': 'xiaohei', 'content': 'final answer'},
            ],
        }
        resource_preparation = {
            'resourceList': [{
                'id': 7,
                'title': 'SQL injection intro',
                'type': 'ai_resource',
                'entry': '/resources?highlight_resource=7&resource=7',
                'summary': 'Basics',
                'score': '0.8',
                'matchScore': '0.7',
                'source': 'resource_agent',
            }],
            'workflowId': 'must-not-leak',
        }
        payload['resourcePreparation'] = resource_preparation
        specialist_context = {
            'learningAnalysis': {
                'summary': 'Needs parameterized query practice',
                'workflowId': 'must-not-leak',
            },
            'recommendations': ['Review SQL injection basics'],
        }

        result = _with_compatible_chat_response(
            payload,
            responses=payload['responses'],
            resource_preparation=resource_preparation,
            specialist_context=specialist_context,
        )

        self.assertEqual(result['responses'], payload['responses'])
        self.assertEqual(result['answer'], 'final answer')
        self.assertEqual(result['resources'][0]['id'], '7')
        self.assertEqual(result['resources'], result['resourceList'])
        self.assertEqual(result['resources'][0]['entry'], '/resources?highlight_resource=7&resource=7')
        self.assertEqual(result['resources'][0]['ai_generated_label'], 'AI多模态生成')
        self.assertEqual(result['resources'][0]['location'], '资源中心 / AI多模态生成 / SQL injection intro')
        self.assertNotIn('score', result['resources'][0])
        self.assertNotIn('matchScore', result['resources'][0])
        self.assertNotIn('source', result['resources'][0])
        self.assertNotIn('score', result['resourcePreparation']['resourceList'][0])
        self.assertEqual(result['learningAnalysis'], {'summary': 'Needs parameterized query practice'})
        self.assertEqual(result['recommendations'], ['Review SQL injection basics'])
        self.assertNotIn('workflowId', result)
        self.assertNotIn('agentContext', result)

    def test_response_keeps_answer_when_optional_fields_are_missing(self):
        result = _with_compatible_chat_response(
            {'mode': 'collaborative', 'responses': []},
            responses=[],
            resource_preparation={},
            specialist_context={},
        )

        self.assertEqual(result['answer'], '')
        self.assertNotIn('resources', result)
        self.assertNotIn('learningAnalysis', result)
        self.assertNotIn('recommendations', result)

    def test_internal_request_context_accepts_new_fields_without_public_names(self):
        request = SimpleNamespace(data={
            'workflowId': 'workflow-1',
            'agentContext': {
                'stage': 'diagnosis',
                'agentContext': {'secret': True},
            },
        })

        context = _internal_request_context_from_request(request)

        self.assertEqual(context['workflow_id'], 'workflow-1')
        self.assertEqual(context['agent_context'], {'stage': 'diagnosis'})
        self.assertNotIn('workflowId', context)
        self.assertNotIn('agentContext', context)


class TeachingContextPromptTests(TestCase):
    def _context(self):
        return {
            'teaching_context': {
                'learningAnalysis': {'summary': '最近在学习 SQL 注入基础'},
                'knowledgeDiagnosis': {'weakness': '参数化查询理解不稳'},
                'resources': {'resources': [{'title': 'SQL 注入入门'}]},
            }
        }

    def test_context_summary_is_appended_to_question_prompt(self):
        summary = _build_teaching_context_summary(self._context())
        prompt = _build_question_prompt('为什么参数化查询能防注入？', summary)

        self.assertTrue(prompt.startswith('为什么参数化查询能防注入？\n\n- 学生学习摘要'))
        self.assertIn('- 知识诊断', prompt)
        self.assertIn('- 推荐资源', prompt)
        self.assertIn('SQL 注入入门', prompt)
        self.assertEqual(_build_teaching_context_summary({'context_summary': '外部摘要'}), '外部摘要')

    def test_chat_with_agent_sends_augmented_question_to_existing_provider(self):
        captured = {}

        class FakeProvider:
            name = 'fake'

            async def chat(self, messages, **kwargs):
                captured['messages'] = messages
                return SimpleNamespace(content='ok', provider='fake', model='fake-model')

        service = MultiAgentChatService()
        service.use_real_api = True
        service.manager = object()
        service._get_provider_candidates = lambda agent_id, agent_config, provider: [FakeProvider()]

        result = asyncio.run(service.chat_with_agent(
            'analyst',
            '为什么参数化查询能防注入？',
            self._context(),
        ))

        user_messages = [message for message in captured['messages'] if message.role == 'user']
        self.assertEqual(result['content'], 'ok')
        self.assertEqual(len(user_messages), 1)
        self.assertIn('- 学生学习摘要', user_messages[0].content)
        self.assertIn('- 知识诊断', user_messages[0].content)
        self.assertIn('- 推荐资源', user_messages[0].content)

class LegalReviewerAgentTests(TestCase):
    """Legal reviewer should be available and grounded in vector retrieval."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='teacher',
            password='pass12345',
            role='teacher',
        )
        self.client.force_authenticate(self.user)
        self.category = Category.objects.create(name='Web')
        self.challenge = Challenge.objects.create(
            title='SQL 注入实验',
            description='在授权靶场中观察 SQL 注入现象。',
            category=self.category,
            difficulty='easy',
            score=100,
            flag='flag{demo}',
            hint='关注输入边界',
            is_active=True,
        )

    def test_list_agents_includes_legal_reviewer(self):
        response = self.client.get('/api/ai/multi-agent/agents/')

        self.assertEqual(response.status_code, 200)
        agent_ids = {item['id'] for item in response.data['agents']}
        self.assertIn('legal_reviewer', agent_ids)
        legal_reviewer = next(item for item in response.data['agents'] if item['id'] == 'legal_reviewer')
        self.assertEqual(legal_reviewer['provider'], 'deepseek')

    def test_legal_reviewer_uses_deepseek_provider_route(self):
        from ai_providers import ProviderRegistry

        service = MultiAgentChatService()

        self.assertEqual(service.get_agent_config('legal_reviewer')['provider'], 'deepseek')
        self.assertEqual(ProviderRegistry.get_provider_for_agent('legal_reviewer'), 'deepseek')

    def test_configured_agents_keep_provider_and_unknown_defaults_to_deepseek(self):
        from ai_providers import ProviderRegistry
        from .service import AGENT_CONFIGS

        for agent_id, config in AGENT_CONFIGS.items():
            self.assertEqual(ProviderRegistry.get_provider_for_agent(agent_id), config['provider'], agent_id)
        service = MultiAgentChatService()
        self.assertEqual(service.get_learning_agent_config('analyst')['provider'], 'volcano')
        self.assertEqual(ProviderRegistry.get_provider_for_agent('unconfigured_agent'), 'deepseek')

    def test_learning_center_model_selection_maps_to_allowlisted_providers(self):
        service = MultiAgentChatService()

        self.assertEqual(service._normalize_model_selection('auto'), {'provider': None, 'model': None})
        self.assertEqual(service._normalize_model_selection('deepseek'), {'provider': 'deepseek', 'model': None})
        self.assertEqual(service._normalize_model_selection('moonshot'), {'provider': 'moonshot', 'model': None})
        self.assertEqual(service._normalize_model_selection('qwen-plus'), {'provider': 'qwen', 'model': 'qwen-plus'})

    def test_legal_review_preset_exists(self):
        AgentPreset.objects.update_or_create(
            preset_id='legal-review',
            defaults={
                'name': '法律合规审查',
                'icon': '⚖',
                'agent_ids': ['analyst', 'security', 'legal_reviewer', 'xiaohei'],
                'sort_order': 75,
                'is_active': True,
            },
        )

        response = self.client.get('/api/ai/multi-agent/presets/')

        self.assertEqual(response.status_code, 200)
        presets = {item['id']: item for item in response.data}
        self.assertIn('legal-review', presets)
        self.assertIn('legal_reviewer', presets['legal-review']['agents'])

    def test_challenge_knowledge_pack_is_indexed_into_vector_table(self):
        ChallengeKnowledgePack.objects.create(
            challenge=self.challenge,
            category_name='Web',
            difficulty='easy',
            score=100,
            keywords=['SQL 注入', '授权靶场', '日志留痕'],
            summary='SQL 注入授权实验知识包',
            challenge_snapshot={'description': self.challenge.description, 'hint': self.challenge.hint},
            context_text='实验必须限定在授权靶场，记录请求、响应和整改建议。',
        )

        result = PlatformContentIndexingService().index_challenge_knowledge_packs(actor=self.user)

        self.assertEqual(result.indexed_objects, 1)
        self.assertGreater(result.embedded_chunks, 0)
        self.assertTrue(
            LegalKnowledgeEmbedding.objects.filter(
                source_type='challenge',
                object_id=self.challenge.knowledge_pack.id,
                metadata__kind='knowledge_pack',
            ).exists()
        )

    def test_tutoring_vector_context_returns_approved_learning_article(self):
        article_category = ArticleCategory.objects.create(name='Web 安全')
        article = Article.objects.create(
            title='SQL 注入与参数化查询入门',
            content='SQL 注入的核心风险是把用户输入拼接进查询。参数化查询能够让输入保持为数据。',
            summary='SQL 注入基础与参数化查询实践。',
            author=self.user,
            category=article_category,
            status='approved',
            tags='SQL 注入,参数化查询',
        )
        PlatformContentIndexingService().index_articles(actor=self.user)

        result = MultiAgentChatService()._build_tutoring_vector_context(
            'SQL 注入',
            '参数化查询为什么能防止注入？',
        )

        self.assertEqual(result['mode'], 'vector')
        self.assertTrue(result['items'])
        self.assertEqual(result['items'][0]['title'], article.title)
        self.assertEqual(result['items'][0]['entry'], f'/community/article/{article.id}')

    def test_legal_reviewer_fallback_mentions_evidence_gap(self):
        LegalKnowledgeEmbedding.objects.create(
            source_type='legal_clause',
            content_object=self.challenge,
            object_id=self.challenge.id,
            chunk_index=99,
            title='网络安全法参考',
            text='开展网络安全教育和技术实验应当采取安全保护措施。',
            text_hash=sha256_text('开展网络安全教育和技术实验应当采取安全保护措施。'),
            embedding=[1.0] + [0.0] * 127,
            embedding_model='local-hash-v1',
            embedding_dimension=128,
            metadata={'kind': 'legal_reference'},
        )
        service = MultiAgentChatService()
        service.use_real_api = False
        response = service._build_legal_review_fallback(
            legal_items=[{
                'title': '网络安全法参考',
                'source_type': 'legal_clause',
                'score': 0.8,
            }],
            challenge_items=[],
        )

        self.assertIn('相关法规依据', response)
        self.assertIn('未检索到题目知识包', response)

    def test_role_scoped_rag_keeps_agent_boundaries(self):
        service = MultiAgentChatService()

        analyst_instruction = service._build_role_rag_instruction(
            'analyst',
            'sql',
            'SQL 注入授权实验知识包',
        )
        xiaohei_instruction = service._build_role_rag_instruction(
            'xiaohei',
            'sql',
            'SQL 注入授权实验知识包',
        )

        self.assertIn('只负责拆解题面', analyst_instruction)
        self.assertIn('不要汇总其他智能体观点', analyst_instruction)
        self.assertIn('负责综合总结', xiaohei_instruction)
        self.assertIn('SQL 注入授权实验知识包', analyst_instruction)

    def test_challenge_context_respects_legal_reviewer_only_selection(self):
        async def fake_legal_review(self, *, question, challenge_info, context):
            return {
                'agent_id': 'legal_reviewer',
                'agent_name': '法律审核师',
                'provider': 'fallback',
                'content': '法律审核师结果',
                'legal_evidence_count': 0,
                'challenge_knowledge_count': 0,
            }

        with patch.object(MultiAgentChatService, 'run_legal_reviewer', fake_legal_review):
            response = self.client.post('/api/ai/multi-agent/chat/', {
                'message': 'sql',
                'challenge_id': self.challenge.id,
                'agent_ids': ['legal_reviewer'],
                'mode': 'collaborative',
                'force_ai': True,
                'workflowId': 'workflow-should-stay-internal',
                'agentContext': {'stage': 'api-test'},
            }, format='json')

        self.assertEqual(response.status_code, 200)
        response_agent_ids = [item['agent_id'] for item in response.data['responses']]
        self.assertEqual(response_agent_ids, ['legal_reviewer'])
        self.assertEqual(response.data['answer'], '法律审核师结果')
        self.assertNotIn('workflowId', response.data)
        self.assertNotIn('agentContext', response.data)
        self.assertNotIn('xiaohei', response_agent_ids)

    def test_multi_agent_stream_returns_sse_events(self):
        async def fake_chat(self, agent_id, message, context=None, conversation_history=None):
            return {
                'agent_id': agent_id,
                'agent_name': 'Analyst',
                'provider': 'fallback',
                'content': 'streamed answer',
            }

        def fake_knowledge(self, query, challenge_info=None, scope='category', limit=5):
            return {
                'context_text': '',
                'scope': scope,
                'resolved_scope': scope,
                'items': [],
                'keywords': [],
                'cache_hit': False,
            }

        with patch.object(MultiAgentChatService, 'chat_with_agent', fake_chat), \
             patch.object(MultiAgentChatService, 'build_knowledge_context', fake_knowledge):
            response = self.client.post('/api/ai/multi-agent/chat/stream/', {
                'message': 'hello',
                'agent_ids': ['analyst'],
                'mode': 'collaborative',
            }, format='json')
            body = b''.join(response.streaming_content).decode('utf-8')

        self.assertEqual(response.status_code, 200)
        self.assertIn('event: conversation', body)
        self.assertIn('event: agent_response', body)
        self.assertIn('streamed answer', body)
