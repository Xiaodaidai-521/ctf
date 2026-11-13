"""Isolated AI/content regression: synthetic SQLite, no network/providers/files."""
import ast
import asyncio
import importlib
import json
from pathlib import Path
import secrets
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from django.apps import AppConfig
from django.conf import settings
tree = ast.parse((ROOT / 'backend/ctf_backend/settings.py').read_text(encoding='utf-8-sig'))
names = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'INSTALLED_APPS' for t in n.targets))
names = ['data_security.adapters.persistence' if n.endswith('PolicyPersistenceConfig') else n
         for n in names if n != 'ctf_backend.apps.SecurityConfig']
settings.configure(SECRET_KEY='synthetic-ai-fix',
    INSTALLED_APPS=[AppConfig(n, importlib.import_module(n)) for n in names],
    AUTH_USER_MODEL='users.CTFUser', USE_TZ=True,
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3',
                          'NAME': 'file:logic_ai_fix?mode=memory&cache=shared', 'OPTIONS': {'uri': True}}},
    REST_FRAMEWORK={'UNAUTHENTICATED_USER': None},
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    MEDIA_ROOT=str(ROOT / '.state/logic-fix-ai'), MEDIA_URL='/media/',
    DATA_SECURITY_FORMAL_MODE=False, DEBUG=True,
    TUTOR_AGENT_ROUTER_ENABLED=False, TUTOR_SPECIALISTS_ENABLED=False, TUTOR_CONTEXT_ENABLED=False)
import django
django.setup()
from django.db import connection
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from users.models import CTFUser
from articles.models import Article, Category as ArticleCategory
from challenges.models import Challenge, Category as ChallengeCategory
from resources.models import Resource
from learning_paths.models import KnowledgeConcept
from rag_ingestion.models import DocumentSource
from learning_knowledge.models import Material
from legal_kb.models import LegalKnowledgeEmbedding, LegalRetrievalLog, LegalClause, LegalDocument
from ai_assistant.models import AIConversation, AIMessage, ChallengeKnowledgePack
from content_generator.models import GeneratedTutorial, GeneratedQuiz, GeneratedDiagram, GeneratedCodeExercise
from content_generator.generators import ContentGeneratorService, ContentGenerationError
from content_generator import views as content_views
from ai_assistant import views as ai_views
from ai_assistant.history import Origin, create_message, history_message, readable, REDACTED, track_origin
from legal_kb.services.knowledge_retrieval_service import SafeKnowledgeRetrievalService
from legal_kb.services.retrieval_service import LegalRetrievalService
from legal_kb.services.hashing import sha256_text
from data_security.adapters.persistence import fields
from data_security.runtime.crypto import RuntimeCipher
from data_security.runtime.fields import RuntimeFieldStorage
from rest_framework.test import APIRequestFactory, force_authenticate

MODELS = (ContentType, CTFUser, ArticleCategory, ChallengeCategory, Challenge, Article, Resource,
          KnowledgeConcept, DocumentSource, Material, LegalDocument, LegalClause, LegalKnowledgeEmbedding,
          LegalRetrievalLog, AIConversation, AIMessage, ChallengeKnowledgePack,
          GeneratedTutorial, GeneratedQuiz, GeneratedDiagram, GeneratedCodeExercise)
with connection.schema_editor() as schema:
    for model in MODELS:
        schema.create_model(model)
fields.bind_field_storage(RuntimeFieldStorage(RuntimeCipher(secrets.token_bytes(64))))
factory = APIRequestFactory()


class AIFixRegressions(unittest.TestCase):
    counter = 0

    def setUp(self):
        AIFixRegressions.counter += 1
        self.a = CTFUser.objects.create(username=f'ai_fix_a_{self.counter}')
        self.b = CTFUser.objects.create(username=f'ai_fix_b_{self.counter}')
        self.service = object.__new__(ContentGeneratorService)
        self.service.cache_ttl = 86400
        self.provider = AsyncMock(return_value={'content': '## Valid tutorial\nUseful content', 'agent_id': 'architect'})
        self.service.ai_service = SimpleNamespace(chat_with_agent=self.provider)
        cache.clear()

    def api(self, view, user, *, pk=None, data=None, method='get', content_type=None):
        url = '/synthetic/'
        req = getattr(factory, method)(url, data or {}, format='json')
        force_authenticate(req, user=user)
        kwargs = {} if pk is None else {'pk': pk}
        if content_type:
            kwargs['content_type'] = content_type
        return view.as_view()(req, **kwargs)

    def generate(self, method, *args, **kwargs):
        return asyncio.run(getattr(self.service, method)(*args, **kwargs))

    def source_message(self):
        article = Article.objects.create(author=self.b, title='Synthetic source',
                                         content='synthetic source body', status='approved')
        origin = Origin(self.a)
        origin.add('article', article.pk)
        conversation = AIConversation.objects.create(user=self.a)
        msg = create_message(origin=origin, conversation=conversation, role='assistant',
                             content='source-derived answer', metadata={'source_excerpt': article.content})
        return article, conversation, msg

    def test_cache_isolated_by_user_and_same_user_hits(self):
        one = self.generate('generate_tutorial', 'topic', user=self.a)
        same = self.generate('generate_tutorial', 'topic', user=self.a)
        two = self.generate('generate_tutorial', 'topic', user=self.b)
        self.assertEqual(one.pk, same.pk)
        self.assertNotEqual(one.pk, two.pk)
        self.assertEqual(two.created_by_id, self.b.pk)
        self.assertEqual(self.provider.await_count, 2)

    def test_poisoned_cache_cannot_return_other_user(self):
        other = GeneratedTutorial.objects.create(title='other', raw_content='secret', created_by=self.b)
        cache.set(self.service._cache_key('topic', 'medium', 'tutorial', user=self.a), other.pk)
        result = self.generate('generate_tutorial', 'topic', user=self.a)
        self.assertEqual(result.created_by_id, self.a.pk)
        self.assertNotEqual(result.pk, other.pk)

    def test_all_output_parameters_and_concept_enter_cache_key(self):
        key = self.service._cache_key
        base = ('topic', 'medium', 'quiz')
        self.assertNotEqual(key(*base, user=self.a, question_count=1), key(*base, user=self.a, question_count=10))
        self.assertNotEqual(key('topic', 'medium', 'diagram', diagram_type='flowchart'), key('topic', 'medium', 'diagram', diagram_type='class'))
        self.assertNotEqual(key('topic', 'medium', 'exercise', language='python'), key('topic', 'medium', 'exercise', language='go'))
        self.assertNotEqual(key(*base, concept=SimpleNamespace(pk=1)), key(*base, concept=SimpleNamespace(pk=2)))

    def test_quiz_requested_count_changes_generation(self):
        q = {'question': 'question', 'options': ['A. one', 'B. two'], 'answer': 'A'}
        self.provider.return_value = {'content': json.dumps([q])}
        one = self.generate('generate_quiz', 'quiz', question_count=1, user=self.a)
        self.provider.return_value = {'content': json.dumps([q] * 2)}
        two = self.generate('generate_quiz', 'quiz', question_count=2, user=self.a)
        self.assertEqual((one.question_count, two.question_count), (1, 2))
        self.assertEqual(self.provider.await_count, 2)

    def test_regenerate_bypasses_populated_cache(self):
        old = self.generate('generate_tutorial', 'topic', user=self.a)
        with patch.object(content_views, 'ContentGeneratorService', return_value=self.service):
            response = self.api(content_views.RegenerateContentView, self.a, pk=old.pk,
                                content_type='tutorial', method='post')
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.data['id'], old.pk)
        self.assertEqual(self.provider.await_count, 2)

    def test_typed_details_resolve_same_id_tables(self):
        one = GeneratedTutorial.objects.create(pk=10001, title='tutorial', raw_content='one', created_by=self.a)
        two = GeneratedQuiz.objects.create(pk=10001, title='quiz', raw_content='two', created_by=self.a)
        response = self.api(content_views.GeneratedContentDetailView, self.a, pk=one.pk, content_type='quiz')
        self.assertEqual(response.data['content_type'], 'quiz')
        ambiguous = self.api(content_views.GeneratedContentDetailView, self.a, pk=one.pk)
        self.assertEqual(ambiguous.status_code, 400)

    def test_foreign_tutorial_does_not_shadow_owned_quiz(self):
        GeneratedTutorial.objects.create(pk=10002, title='other', raw_content='other', created_by=self.b)
        quiz = GeneratedQuiz.objects.create(pk=10002, title='own', raw_content='own', created_by=self.a)
        response = self.api(content_views.GeneratedContentDetailView, self.a, pk=quiz.pk)
        self.assertEqual(response.data['content_type'], 'quiz')
        response = self.api(content_views.GeneratedContentDetailView, self.a, pk=quiz.pk, content_type='tutorial')
        self.assertEqual(response.status_code, 404)

    def test_fallback_is_502_retryable_and_not_saved(self):
        before = GeneratedQuiz.objects.count()
        self.provider.return_value = {'content': 'MODEL_CALL_FAILED', 'provider': 'fallback', 'provider_error': 'MODEL_CALL_FAILED'}
        with patch.object(content_views, 'ContentGeneratorService', return_value=self.service):
            response = self.api(content_views.GenerateQuizView, self.a, method='post', data={'topic': 'failure', 'question_count': 1})
        self.assertEqual(response.status_code, 502)
        self.assertTrue(response.data['retryable'])
        self.assertEqual(GeneratedQuiz.objects.count(), before)
        self.assertIsNone(cache.get(self.service._cache_key('failure', 'medium', 'quiz', user=self.a, question_count=1)))

    def test_invalid_question_shape_is_not_saved(self):
        before = GeneratedQuiz.objects.count()
        for text in ('[]', '{}', '[{"question":"q"}]', '[{"question":"q","options":["a","b"],"answer":"Z"}]'):
            with self.subTest(text=text):
                self.provider.return_value = {'content': text}
                with self.assertRaises(ContentGenerationError):
                    self.generate('generate_quiz', text, question_count=1, user=self.a)
        self.assertEqual(GeneratedQuiz.objects.count(), before)

    def test_invalid_diagram_and_exercise_are_not_saved(self):
        self.provider.return_value = {'content': 'a provider explanation, no diagram'}
        with self.assertRaises(ContentGenerationError):
            self.generate('generate_diagram', 'invalid', user=self.a)
        self.provider.return_value = {'content': '[1,2]'}
        with self.assertRaises(ContentGenerationError):
            self.generate('generate_exercise', 'invalid', user=self.a)

    def test_history_allowed_body_and_metadata_excluded(self):
        _, _, msg = self.source_message()
        self.assertTrue(readable(msg, self.a))
        projected = history_message(msg, self.a)
        self.assertEqual(projected['content'], 'source-derived answer')
        self.assertEqual(projected['metadata'], {})

    def test_revoked_history_api_redacts_body_and_excerpt(self):
        article, conv, _ = self.source_message()
        article.status = 'rejected'; article.save(update_fields=['status'])
        req = factory.get('/synthetic/'); force_authenticate(req, user=self.a)
        response = ai_views.AIConversationViewSet.as_view({'get': 'retrieve'})(req, pk=conv.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['messages'][0]['content'], REDACTED)
        self.assertEqual(response.data['messages'][0]['metadata'], {})

    def test_legacy_tampered_and_other_user_history_fail_closed(self):
        _, conv, msg = self.source_message()
        self.assertFalse(readable(msg, self.b))
        legacy = AIMessage.objects.create(conversation=conv, role='assistant', content='legacy', metadata={'claimed_source': 1})
        self.assertEqual(history_message(legacy, self.a)['content'], REDACTED)
        msg.history_origin += 'bad'; msg.save(update_fields=['history_origin'])
        self.assertFalse(readable(msg, self.a))

    def test_source_edit_invalidates_signed_history(self):
        article, _, msg = self.source_message()
        article.content = 'edited body'; article.save(update_fields=['content'])
        self.assertFalse(readable(msg, self.a))

    def test_actual_chat_omits_revoked_history_and_seals_new_rows(self):
        article, conv, _ = self.source_message()
        article.status = 'rejected'; article.save(update_fields=['status'])
        histories = []
        answer = SimpleNamespace(chat=lambda **kw: (histories.append(kw['conversation_history']) or 'new answer'))
        req = factory.post('/synthetic/chat/', {'message': 'continue'}, format='json'); force_authenticate(req, user=self.a)
        with patch.object(ai_views, 'detect_challenge', return_value=(None, None)), patch.object(ai_views._TUTOR_REQUEST_ORCHESTRATOR, 'answer_service', answer):
            response = ai_views.AIConversationViewSet.as_view({'post': 'chat'})(req, pk=conv.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(histories, [[]])
        new = list(conv.messages.order_by('id'))[-2:]
        self.assertTrue(all(readable(m, self.a) for m in new))

    def test_replayed_answer_inherits_source_revocation(self):
        article, conv, _ = self.source_message()
        histories = []
        answer = SimpleNamespace(chat=lambda **kw: (histories.append(kw['conversation_history']) or 'derived continuation'))
        req = factory.post('/synthetic/chat/', {'message': 'continue'}, format='json'); force_authenticate(req, user=self.a)
        with patch.object(ai_views, 'detect_challenge', return_value=(None, None)), patch.object(ai_views._TUTOR_REQUEST_ORCHESTRATOR, 'answer_service', answer):
            response = ai_views.AIConversationViewSet.as_view({'post': 'chat'})(req, pk=conv.pk)
        self.assertEqual(histories[0][0]['content'], 'source-derived answer')
        latest = conv.messages.filter(role='assistant').latest('id')
        self.assertTrue(readable(latest, self.a))
        article.status = 'rejected'; article.save(update_fields=['status'])
        self.assertFalse(readable(latest, self.a))

    def test_actual_safe_retrieval_filters_withdrawn_article(self):
        article = Article.objects.create(author=self.b, title='unique synthetic recall',
                                         content='unique synthetic recall source text', status='approved')
        LegalKnowledgeEmbedding.objects.create(source_type='article',
            content_type=ContentType.objects.get_for_model(Article), object_id=article.pk,
            title=article.title, text=article.content, text_hash=sha256_text(article.content),
            embedding_model='local-hash-v1', embedding_dimension=128, embedding=[])
        safe = SafeKnowledgeRetrievalService(retrieval_service=LegalRetrievalService(embedding_service=SimpleNamespace()))
        self.assertTrue(any(r['object_id'] == article.pk for r in safe.retrieve(query='unique synthetic recall', user=self.a)))
        article.status = 'rejected'; article.save(update_fields=['status'])
        self.assertFalse(any(r['object_id'] == article.pk for r in safe.retrieve(query='unique synthetic recall', user=self.a)))

    def test_retrieval_does_not_accept_forged_content_type(self):
        article = Article.objects.create(author=self.b, title='forged index', content='forged index body', status='approved')
        LegalKnowledgeEmbedding.objects.create(source_type='article',
            content_type=ContentType.objects.get_for_model(KnowledgeConcept), object_id=article.pk,
            title=article.title, text=article.content, text_hash=sha256_text(article.content),
            embedding_model='local-hash-v1', embedding_dimension=128, embedding=[])
        service = LegalRetrievalService(embedding_service=SimpleNamespace())
        self.assertEqual(service.retrieve(query='forged index', filters={'source_type': 'article', 'object_id': article.pk}, user=self.a), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
