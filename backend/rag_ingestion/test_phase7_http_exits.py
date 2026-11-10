"""Synthetic PostgreSQL checks for HTTP/SSE release and protection refusal."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from asgiref.sync import async_to_sync
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_assistant import views
from ai_assistant.models import AIConversation
from ai_assistant.service import MultiAgentChatService
from ai_assistant.tutor_request_orchestrator import TutorRequestOrchestrator
from data_security.adapters.django import rag

from . import test_phase7_protection as protection_fixture

MARKER = 'rag-private@example.invalid'


@override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False,
                   EMBEDDING_PROVIDER='', EMBEDDING_MODEL='local-hash-v1', EMBEDDING_DIMENSION=128)
class HttpTextExitTests(TransactionTestCase):
    def setUp(self):
        protection_fixture.RagProtectionTests.setUp(self)
        rag.bind_rag_protection(self.components['protect_rag_value'])
        self.factory = APIRequestFactory()
        self.conversation = AIConversation.objects.create(user=self.admin)

    def preparation(self):
        return {'route': {}, 'specialists': {}, 'teachingContext': {'taskType': 'question_answer'},
                'performanceMetrics': SimpleNamespace(fallback_used=False)}

    def request(self, *, agents=None):
        request = self.factory.post('/api/ai/multi-agent/chat/',
            {'message': 'Synthetic question', 'agent_ids': agents or ['analyst'], 'force_ai': True},
            format='json')
        force_authenticate(request, user=self.admin)
        return request

    def orchestrator(self):
        instance = Mock()
        instance.prepare.return_value = self.preparation()
        instance.metadata_summary.return_value = {}
        instance.call_existing_answer_chain.return_value = {
            'mode': 'collaborative', 'responses': [{'agent_id': 'analyst', 'provider': 'capture',
                'content': 'Answer ' + MARKER + ' conclusion'}],
            'knowledge_items': [{'summary': 'Evidence ' + MARKER, 'text': 'Evidence ' + MARKER}],
        }

        async def call(preparation, answer_chain):
            return await answer_chain(preparation.get('teachingContext'))

        instance.call_existing_answer_chain_async = AsyncMock(side_effect=call)
        instance.adapt_response.side_effect = lambda preparation, payload, **context: payload
        return instance

    def test_compatible_response_protects_body_metadata_and_resources_before_truncation(self):
        response = {'agent_id': 'analyst', 'content': 'Answer ' + MARKER + ' conclusion',
                    'legal_sources': [{'title': MARKER}]}
        resource = {'id': 7, 'title': 'Title ' + 'x' * 105 + ' ' + MARKER,
                    'summary': 'Evidence ' + 'x' * 244 + ' ' + MARKER + ' conclusion',
                    'entry': '/resources?highlight_resource=7', 'type': 'resource'}
        value = views._with_compatible_chat_response(
            {'responses': [response], 'challenge_info': {'title': MARKER}},
            responses=[response], resource_preparation={'resourceList': [resource]},
            specialist_context={'recommendations': [MARKER]})
        self.assertNotIn(MARKER, json.dumps(value))
        self.assertNotIn('rag-pr', value['resources'][0]['title'] + value['resources'][0]['summary'])
        self.assertIn('Evidence', value['resources'][0]['summary'])
        self.assertIn('Answer', value['answer'])
        self.assertIn('conclusion', value['answer'])
        self.assertEqual(value['content'], value['answer'])
        self.assertIn(MARKER, response['content'])
        self.assertIn(MARKER, resource['summary'])

    def test_http_final_adapter_protects_an_injected_answer_chain(self):
        orchestrator = self.orchestrator()
        with patch.object(views, '_TUTOR_REQUEST_ORCHESTRATOR', orchestrator), \
             patch.object(views, 'detect_challenge', return_value=(None, None)), \
             patch.object(views, '_get_or_create_ai_conversation', return_value=self.conversation), \
             patch.object(views, 'audit_event'):
            response = views.multi_agent_chat(self.request())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(MARKER, json.dumps(response.data))
        self.assertIn('Answer', response.data['answer'])
        self.assertIn('conclusion', response.data['answer'])

    def test_http_protection_denial_is_not_a_model_error_or_raw_audit_preview(self):
        orchestrator = self.orchestrator()
        orchestrator.call_existing_answer_chain.side_effect = rag.RagProtectionError()
        with patch.object(views, '_TUTOR_REQUEST_ORCHESTRATOR', orchestrator), \
             patch.object(views, 'detect_challenge', return_value=(None, None)), \
             patch.object(views, '_get_or_create_ai_conversation', return_value=self.conversation), \
             patch.object(views, 'audit_event') as audit:
            response = views.multi_agent_chat(self.request())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data, {'detail': 'RAG_PROTECTION_FAILED'})
        audit.assert_not_called()

    def test_sse_body_metadata_and_done_adapter_are_protected(self):
        orchestrator = self.orchestrator()
        orchestrator.prepare.return_value['specialists'] = {
            'resourcePreparation': {'title': MARKER, 'notes': MARKER}}
        knowledge = {'context_text': '', 'items': [{'summary': 'Evidence ' + MARKER}],
                     'scope': 'category', 'resolved_scope': 'category', 'keywords': [MARKER]}
        answer = {'agent_id': 'analyst', 'provider': 'capture',
                  'content': 'Answer ' + MARKER + ' conclusion',
                  'legal_sources': [{'title': MARKER}]}
        with patch.object(views, '_TUTOR_REQUEST_ORCHESTRATOR', orchestrator), \
             patch.object(views, 'detect_challenge', return_value=(None, None)), \
             patch.object(views, '_get_or_create_ai_conversation', return_value=self.conversation), \
             patch.object(views, '_persist_stream_message', new_callable=AsyncMock), \
             patch.object(MultiAgentChatService, 'build_knowledge_context', return_value=knowledge), \
             patch.object(MultiAgentChatService, 'chat_with_agent', new_callable=AsyncMock, return_value=answer):
            response = views.multi_agent_chat_stream(self.request())
            body = b''.join(response.streaming_content).decode()
        self.assertNotIn(MARKER, body)
        self.assertIn('Answer', body)
        self.assertIn('conclusion', body)
        self.assertIn('event: done', body)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn(MARKER, answer['content'])

    def test_sse_knowledge_denial_stops_before_any_answer_or_done(self):
        orchestrator = self.orchestrator()
        with patch.object(views, '_TUTOR_REQUEST_ORCHESTRATOR', orchestrator), \
             patch.object(views, 'detect_challenge', return_value=(None, None)), \
             patch.object(views, '_get_or_create_ai_conversation', return_value=self.conversation), \
             patch.object(MultiAgentChatService, 'build_knowledge_context', side_effect=rag.RagProtectionError()), \
             patch.object(MultiAgentChatService, 'chat_with_agent', new_callable=AsyncMock,
                          return_value={'content': 'Unsafe fallback', 'provider': 'capture'}) as answer, \
             patch.object(views, '_persist_stream_message', new_callable=AsyncMock):
            response = views.multi_agent_chat_stream(self.request())
            body = b''.join(response.streaming_content).decode()
        self.assertIn('event: error', body)
        self.assertIn('RAG_PROTECTION_FAILED', body)
        self.assertNotIn('event: done', body)
        self.assertNotIn('Unsafe fallback', body)
        answer.assert_not_called()
        orchestrator.adapt_response.assert_not_called()

    def test_parallel_sse_protection_denial_cannot_emit_a_successful_done(self):
        orchestrator = self.orchestrator()
        with patch.object(views, '_TUTOR_REQUEST_ORCHESTRATOR', orchestrator), \
             patch.object(views, 'detect_challenge', return_value=(None, None)), \
             patch.object(views, '_get_or_create_ai_conversation', return_value=self.conversation), \
             patch.object(MultiAgentChatService, 'build_knowledge_context', return_value={'items': []}), \
             patch.object(MultiAgentChatService, 'chat_with_agent', new_callable=AsyncMock,
                          side_effect=rag.RagProtectionError()), \
             patch.object(MultiAgentChatService, 'run_legal_reviewer', new_callable=AsyncMock,
                          side_effect=rag.RagProtectionError()):
            response = views.multi_agent_chat_stream(self.request(agents=['analyst', 'legal_reviewer']))
            body = b''.join(response.streaming_content).decode()
        self.assertIn('event: error', body)
        self.assertIn('RAG_PROTECTION_FAILED', body)
        self.assertNotIn('event: done', body)
        self.assertNotIn('event: agent_response', body)
        orchestrator.adapt_response.assert_not_called()

    def test_sse_frame_denial_emits_only_a_fixed_terminal_error(self):
        orchestrator = self.orchestrator()
        rag.bind_rag_protection(Mock(side_effect=RuntimeError(MARKER)))
        with patch.object(views, '_TUTOR_REQUEST_ORCHESTRATOR', orchestrator), \
             patch.object(views, 'detect_challenge', return_value=(None, None)), \
             patch.object(views, '_get_or_create_ai_conversation', return_value=self.conversation), \
             patch.object(MultiAgentChatService, 'build_knowledge_context', return_value={'items': []}), \
             patch.object(MultiAgentChatService, 'chat_with_agent', new_callable=AsyncMock,
                          return_value={'content': MARKER, 'provider': 'capture'}) as answer, \
             patch.object(views, '_persist_stream_message', new_callable=AsyncMock):
            response = views.multi_agent_chat_stream(self.request())
            body = b''.join(response.streaming_content).decode()
        self.assertEqual(body, 'event: error\ndata: {"error":"RAG_PROTECTION_FAILED"}\n\n')
        answer.assert_not_called()

    def test_answer_chain_protection_denial_is_not_retried_without_context(self):
        orchestrator = TutorRequestOrchestrator()
        preparation = self.preparation()
        answer = Mock(side_effect=rag.RagProtectionError())
        with self.assertRaises(rag.RagProtectionError):
            orchestrator.call_existing_answer_chain(preparation, answer)
        answer.assert_called_once()
        self.assertFalse(preparation['performanceMetrics'].fallback_used)
        async_answer = AsyncMock(side_effect=rag.RagProtectionError())
        with self.assertRaises(rag.RagProtectionError):
            async_to_sync(orchestrator.call_existing_answer_chain_async)(preparation, async_answer)
        async_answer.assert_called_once()
        self.assertFalse(preparation['performanceMetrics'].fallback_used)

    def test_prepare_protection_denial_is_not_replaced_by_an_empty_context(self):
        router = Mock()
        router.route.side_effect = rag.RagProtectionError()
        with override_settings(TUTOR_AGENT_ROUTER_ENABLED=True, TUTOR_SPECIALISTS_ENABLED=False,
                               TUTOR_CONTEXT_ENABLED=False), self.assertRaises(rag.RagProtectionError):
            TutorRequestOrchestrator(router=router).prepare(user=self.admin, message='Synthetic question')
        profile = Mock()
        profile.build.side_effect = rag.RagProtectionError()
        with override_settings(TUTOR_AGENT_ROUTER_ENABLED=False, TUTOR_SPECIALISTS_ENABLED=False,
                               TUTOR_CONTEXT_ENABLED=True), self.assertRaises(rag.RagProtectionError):
            TutorRequestOrchestrator(profile_adapter=profile).prepare(user=self.admin, message='Synthetic question')
