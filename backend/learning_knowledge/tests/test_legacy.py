from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from ai_assistant.models import AIConversation, AIMessage, ChallengeKnowledgePack
from ai_assistant.service import MultiAgentChatService
from articles.models import Article
from challenges.models import Category, Challenge, ChallengeSolution
from resources.models import Resource
from .helpers import material, setup_case


class LegacyBoundaryTests(TestCase):
    def setUp(self):
        setup_case(self)
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def test_t3_02_legacy_history_redacts_all_secret_classes(self):
        conversation = AIConversation.objects.create(user=self.student)
        for kind in ('teacher_answer', 'grading_secret', 'student_analysis'):
            AIMessage.objects.create(conversation=conversation, role='assistant', content=f'{kind}-BODY',
                                     metadata={'title': f'{kind}-TITLE'})
        response = self.client.get(f'/api/ai/conversations/{conversation.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('-BODY', str(response.data))
        self.assertNotIn('-TITLE', str(response.data))
        self.assertEqual(len(response.data['messages']), 3)

    def test_t3_04_poisoned_pack_never_enters_keyword_semantic_fusion(self):
        challenge = Challenge.objects.create(title='public task', description='public', category=Category.objects.create(name='m3'),
                                             difficulty='easy', score=1, flag='SECRET-FLAG')
        ChallengeSolution.objects.create(challenge=challenge, content='SECRET-SOLUTION', is_enabled=True)
        ChallengeKnowledgePack.objects.create(challenge=challenge, context_text='SECRET-OLD-PACK', metadata={'has_solution_walkthrough': False})
        service = MultiAgentChatService()
        info = {'id': challenge.pk, 'title': challenge.title}
        result = service.build_knowledge_context('SECRET', challenge_info=info, user=self.student)
        self.assertEqual(result['context_text'], '')
        self.assertEqual(result['items'], [])
        self.assertIsNone(service._ensure_challenge_knowledge_pack(challenge.pk))
        self.assertNotIn('SECRET-SOLUTION', str(service.build_challenge_knowledge_pack_payload(challenge)))
        legal_context = service.build_legal_review_context('SECRET', challenge_info=info)
        self.assertEqual(legal_context['challenge_items'], [])
        self.assertEqual(legal_context['legal_items'], [])

    def test_t3_04_authorized_context_contains_only_short_lesson(self):
        material(self, text='授权范围证据')
        material(self, 'teacher_answer', text='授权范围 SECRET-TEACHER')
        result = MultiAgentChatService().build_knowledge_context('授权', user=self.student, task_context=self.scope)
        self.assertIn('授权范围证据', result['context_text'])
        self.assertNotIn('SECRET', str(result))
        denied = MultiAgentChatService().build_knowledge_context('授权', user=self.other, task_context=self.scope)
        self.assertEqual(denied['items'], [])

    def test_t3_06_old_unscoped_caches_are_not_authority(self):
        service = MultiAgentChatService()
        cache.set('old-secret', {'content': 'SECRET-CACHE'})
        self.assertIsNone(service._get_cached_knowledge_result('old-secret'))
        self.assertIsNone(service._get_cached_response_result('old-secret'))

    def test_t3_09_article_status_and_registered_secret_detail_are_denied(self):
        article = Article.objects.create(author=self.teacher, title='SECRET-TITLE', content='SECRET-BODY', status='pending')
        response = self.client.get(f'/api/articles/articles/{article.pk}/?status=pending')
        self.assertEqual(response.status_code, 404)
        article.status = 'approved'
        article.save()
        material(self, 'teacher_answer', text=article.content, source_type='article', source_id=article.pk)
        for url in (f'/api/articles/articles/{article.pk}/', '/api/articles/articles/?search=SECRET'):
            self.assertNotIn('SECRET', str(self.client.get(url).data))

    def test_t3_02_resource_highlight_cannot_authorize_detail_or_download(self):
        resource = Resource.objects.create(title='SECRET-TITLE', description='SECRET-BODY', resource_type='document',
                                           category='m3', uploader=self.teacher, status='approved', is_tutoring_reserved=True)
        for endpoint in (f'/api/resources/{resource.pk}/', f'/api/resources/{resource.pk}/download/'):
            response = self.client.get(endpoint + f'?highlight_resource={resource.pk}')
            self.assertEqual(response.status_code, 404)
            self.assertNotIn('SECRET', str(response.data))

    def test_t3_02_registered_secret_resource_stays_private_even_not_reserved(self):
        resource = Resource.objects.create(title='SECRET-TITLE', description='SECRET-BODY', resource_type='document',
                                           category='m3', uploader=self.teacher, status='approved')
        material(self, 'grading_secret', text=resource.description, source_type='resource', source_id=resource.pk)
        for endpoint in (f'/api/resources/{resource.pk}/', f'/api/resources/{resource.pk}/download/'):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn('SECRET', str(response.data))
