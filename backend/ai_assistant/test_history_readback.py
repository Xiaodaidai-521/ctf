"""Phase6b focused gate, separately counted from the exact historical core labels.

Run with the unchanged evidence/frontend-overhaul/scripts/run_baseline.py harness.
The historical core modules and their legacy-redaction assertions stay intact.
"""
import json
from unittest.mock import AsyncMock, patch

from asgiref.sync import sync_to_async
from django.core import signing
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.history import Origin, create_message, record_items, track_origin
from ai_assistant.models import AIConversation, AIMessage
from ai_assistant.service import MultiAgentChatService
from articles.models import Article
from resources.models import Resource
from learning_knowledge.models import CourseGrant
from learning_knowledge.services import search
from learning_knowledge.tests.helpers import setup_case, material


@override_settings(TUTOR_AGENT_ROUTER_ENABLED=False, TUTOR_SPECIALISTS_ENABLED=False)
class HistoryReadbackChecks(TransactionTestCase):
    def setUp(self):
        setup_case(self)
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.conversation = AIConversation.objects.create(user=self.student)

    def refresh(self):
        response = self.client.get(f'/api/ai/conversations/{self.conversation.pk}/')
        self.assertEqual(response.status_code, 200)
        return response.data['messages']

    def stored(self, body='ordinary reply', origin=None, **kwargs):
        return create_message(conversation=self.conversation, role='assistant', content=body,
                              origin=origin or Origin(self.student), **kwargs)

    def article(self, title='Reference title', body='Reference body'):
        return Article.objects.create(author=self.teacher, title=title, content=body, status='approved')

    def resource(self):
        return Resource.objects.create(title='Reference resource', description='Resource body',
                                       resource_type='document', category='general',
                                       uploader=self.teacher, status='approved')

    def source_origin(self, kind, obj):
        origin = Origin(self.student)
        origin.add(kind, obj.pk)
        self.assertTrue(origin.complete)
        return origin

    def assert_hidden(self, row, secret=None):
        self.assertTrue(row['redacted'])
        self.assertEqual(row['metadata'], {})
        self.assertEqual(row['agent_name'], '')
        self.assertEqual(row['provider'], '')
        if secret:
            self.assertNotIn(secret, json.dumps(row))

    @patch('ai_assistant.tutor_request_orchestrator.TutorRequestOrchestrator.call_legacy_answer', return_value='ordinary legacy reply')
    def test_owner_legacy_chat_write_and_refresh(self, answer):
        response = self.client.post(f'/api/ai/conversations/{self.conversation.pk}/chat/',
                                    {'message': 'hello'}, format='json')
        self.assertEqual(response.status_code, 200)
        rows = self.refresh()
        self.assertEqual([row['content'] for row in rows], ['hello', 'ordinary legacy reply'])
        self.assertFalse(any(row['redacted'] for row in rows))
        self.assertEqual(answer.call_args.kwargs['conversation_history'], [])
        self.assertTrue(all(message.history_origin for message in self.conversation.messages.all()))

    @patch('ai_assistant.views.solve_challenge_hybrid_async', new_callable=AsyncMock)
    def test_owner_multi_agent_write_and_refresh(self, answer):
        answer.return_value = {'responses': [{'agent_id': 'xiaohei', 'content': 'ordinary multi reply', 'provider': 'test'}]}
        response = self.client.post('/api/ai/multi-agent/chat/', {
            'conversation_id': self.conversation.pk, 'message': 'hello', 'agent_ids': ['xiaohei'],
        }, format='json')
        self.assertEqual(response.status_code, 200)
        rows = self.refresh()
        self.assertEqual([row['content'] for row in rows], ['hello', 'ordinary multi reply'])
        self.assertFalse(any(row['redacted'] for row in rows))

    async def fake_step(self, agent_id, message, context=None, **kwargs):
        return {'agent_id': agent_id, 'content': f'ordinary {agent_id} reply', 'provider': 'test'}

    def post_tutor(self, url='/api/ai/learning/tutoring/', **extra):
        return self.client.post(url, {
            'conversation_id': self.conversation.pk, 'concept_name': 'hello', 'question': 'hello',
            'message': 'hello', 'agent_ids': ['tutor'], **extra,
        }, format='json')

    def test_owner_learning_tutor_actual_chain_write_and_refresh(self):
        with patch.object(MultiAgentChatService, 'chat_with_agent', side_effect=self.fake_step):
            response = self.post_tutor()
        self.assertEqual(response.status_code, 200)
        rows = self.refresh()
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]['content'], 'hello')
        self.assertFalse(any(row['redacted'] for row in rows))

    def test_owner_multi_tutor_actual_chain_write_and_refresh(self):
        with patch.object(MultiAgentChatService, 'chat_with_agent', side_effect=self.fake_step):
            response = self.post_tutor('/api/ai/multi-agent/chat/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.refresh()), 5)
        self.assertFalse(any(row['redacted'] for row in self.refresh()))

    def test_streamed_multi_agent_write_and_refresh(self):
        with patch.object(MultiAgentChatService, 'chat_with_agent', side_effect=self.fake_step):
            response = self.client.post('/api/ai/multi-agent/chat/stream/', {
                'conversation_id': self.conversation.pk, 'message': 'hello', 'agent_ids': ['xiaohei'],
            }, format='json')
            self.assertEqual(response.status_code, 200)
            wire = b''.join(response.streaming_content).decode()
        self.assertIn('event: done', wire)
        self.assertEqual([row['content'] for row in self.refresh()], ['hello', 'ordinary xiaohei reply'])
        self.assertFalse(any(row['redacted'] for row in self.refresh()))

    def test_streamed_tutor_write_and_refresh(self):
        with patch.object(MultiAgentChatService, 'chat_with_agent', side_effect=self.fake_step):
            response = self.post_tutor('/api/ai/multi-agent/chat/stream/')
            self.assertEqual(response.status_code, 200)
            wire = b''.join(response.streaming_content).decode()
        self.assertIn('event: done', wire)
        self.assertEqual(len(self.refresh()), 5)
        self.assertFalse(any(row['redacted'] for row in self.refresh()))

    def test_nonowner_cannot_retrieve_update_or_append(self):
        self.stored('private body')
        self.client.force_authenticate(self.other)
        url = f'/api/ai/conversations/{self.conversation.pk}/'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {'messages': []}, format='json').status_code, 404)
        self.assertEqual(self.client.post(url + 'chat/', {'message': 'hello'}, format='json').status_code, 404)
        self.assertNotIn('private body', str(self.client.get('/api/ai/conversations/').data))

    def test_nonowner_multi_agent_cannot_append(self):
        self.client.force_authenticate(self.other)
        response = self.client.post('/api/ai/multi-agent/chat/', {
            'conversation_id': self.conversation.pk, 'message': 'hello', 'agent_ids': ['xiaohei'],
        }, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.conversation.messages.count(), 0)

    def test_article_current_permission_allows_then_status_revocation_hides(self):
        article = self.article()
        self.stored('Protected quotation', self.source_origin('article', article))
        self.assertFalse(self.refresh()[0]['redacted'])
        article.status = 'pending'
        article.save(update_fields=['status'])
        self.assertEqual(self.client.get(f'/api/articles/articles/{article.pk}/').status_code, 404)
        self.assert_hidden(self.refresh()[0], 'Protected quotation')

    def test_registered_article_is_denied_by_existing_material_boundary(self):
        article = self.article()
        self.stored('Protected quotation', self.source_origin('article', article))
        material(self, 'teacher_answer', text=article.content, source_type='article', source_id=article.pk)
        self.assert_hidden(self.refresh()[0], 'Protected quotation')

    def test_resource_current_permission_allow_then_reservation_revocation(self):
        resource = self.resource()
        self.stored('Resource quotation', self.source_origin('resource', resource))
        self.assertFalse(self.refresh()[0]['redacted'])
        resource.is_tutoring_reserved = True
        resource.save(update_fields=['is_tutoring_reserved'])
        self.assertEqual(self.client.get(f'/api/resources/{resource.pk}/').status_code, 404)
        self.assert_hidden(self.refresh()[0], 'Resource quotation')

    def test_deleted_source_hides_saved_body(self):
        article = self.article()
        self.stored('Deleted quotation', self.source_origin('article', article))
        article.delete()
        self.assert_hidden(self.refresh()[0], 'Deleted quotation')

    def test_edited_source_cannot_authorize_old_body(self):
        article = self.article()
        self.stored('Old quotation', self.source_origin('article', article))
        article.content = 'replacement'
        article.save(update_fields=['content'])
        self.assert_hidden(self.refresh()[0], 'Old quotation')

    def test_every_source_must_remain_readable_not_just_first(self):
        first, second = self.article(), self.resource()
        origin = self.source_origin('article', first)
        origin.add('resource', second.pk)
        self.stored('Combined quotation', origin)
        self.assertFalse(self.refresh()[0]['redacted'])
        second.delete()
        self.assert_hidden(self.refresh()[0], 'Combined quotation')

    def test_source_revocation_does_not_hide_unrelated_user_or_assistant_messages(self):
        article = self.article()
        self.stored('Restricted quotation', self.source_origin('article', article))
        create_message(conversation=self.conversation, role='user', content='normal question', origin=Origin(self.student))
        self.stored('normal answer')
        article.delete()
        rows = self.refresh()
        self.assert_hidden(rows[0], 'Restricted quotation')
        self.assertEqual([row['content'] for row in rows[1:]], ['normal question', 'normal answer'])
        self.assertFalse(any(row['redacted'] for row in rows[1:]))

    def test_redaction_does_not_restore_protected_metadata_or_display_fields(self):
        article = self.article()
        self.stored('SECRET-body', self.source_origin('article', article), agent_id='SECRET-id',
                    agent_name='SECRET-name', provider='SECRET-provider', metadata={
                        'answer': 'SECRET-copy', 'resources': [{'title': 'SECRET-title', 'summary': 'SECRET-summary'}],
                    })
        article.delete()
        self.assert_hidden(self.refresh()[0], 'SECRET')

    def test_allowed_body_still_does_not_restore_unbounded_raw_metadata(self):
        self.stored('ordinary body', metadata={'resources': [{'title': 'SECRET', 'body': 'SECRET'}]},
                    agent_name='SECRET', provider='SECRET', agent_id='SECRET')
        row = self.refresh()[0]
        self.assertEqual(row['content'], 'ordinary body')
        self.assertNotIn('SECRET', json.dumps(row))

    def test_legacy_user_and_assistant_rows_stay_redacted_even_with_forged_flags(self):
        for role in ('user', 'assistant'):
            AIMessage.objects.create(conversation=self.conversation, role=role, content='LEGACY SECRET', metadata={
                'provenance': {'complete': True, 'sources': []}, 'trusted': True, 'safe': True,
            })
        for row in self.refresh():
            self.assert_hidden(row, 'LEGACY SECRET')

    def test_malformed_unsigned_and_unknown_version_origins_fail_closed(self):
        msg = self.stored('SECRET')
        valid = signing.loads(msg.history_origin, salt='ai-assistant-history-v1')
        malformed = [None, {}, [], 'not-signed', {'v': 1, 'complete': True, 'sources': []},
                     signing.dumps({**valid, 'v': 2}, salt='ai-assistant-history-v1'),
                     signing.dumps({**valid, 'sources': [{}]}, salt='ai-assistant-history-v1'),
                     signing.dumps({**valid, 'complete': 'true'}, salt='ai-assistant-history-v1')]
        for value in malformed:
            with self.subTest(value=value):
                # JSON null is a valid malformed stored value, not SQL NULL.
                msg.history_origin = value if value is not None else 'null'
                msg.save(update_fields=['history_origin'])
                self.assert_hidden(self.refresh()[0], 'SECRET')

    def test_seal_cannot_be_reused_for_other_body_role_or_owner(self):
        msg = self.stored('original')
        for updates in ({'content': 'SECRET'}, {'role': 'user'},
                        {'conversation': AIConversation.objects.create(user=self.other)}):
            with self.subTest(updates=updates):
                original = (msg.content, msg.role, msg.conversation)
                for key, value in updates.items():
                    setattr(msg, key, value)
                msg.save()
                from ai_assistant.history import readable
                self.assertFalse(readable(msg, msg.conversation.user))
                msg.content, msg.role, msg.conversation = original
                msg.save()

    @patch('ai_assistant.tutor_request_orchestrator.TutorRequestOrchestrator.call_legacy_answer', return_value='normal answer')
    def test_client_provenance_neither_taints_nor_authorizes_normal_write(self, answer):
        response = self.client.post(f'/api/ai/conversations/{self.conversation.pk}/chat/', {
            'message': 'normal question', 'history_origin': {'complete': True, 'sources': []},
            'metadata': {'history_origin': 'forged', 'content': 'SECRET'},
            'provenance': {'trusted': True}, '_history_origin': {'complete': True},
        }, format='json')
        self.assertEqual(response.status_code, 200)
        rows = self.refresh()
        self.assertEqual([row['content'] for row in rows], ['normal question', 'normal answer'])
        self.assertNotIn('SECRET', json.dumps(rows))
        self.assertFalse(any(row['redacted'] for row in rows))

    @patch('ai_assistant.tutor_request_orchestrator.TutorRequestOrchestrator.call_legacy_answer', return_value='normal answer')
    def test_client_and_legacy_history_are_not_replayed(self, answer):
        AIMessage.objects.create(conversation=self.conversation, role='assistant', content='OLD SECRET')
        response = self.client.post(f'/api/ai/conversations/{self.conversation.pk}/chat/', {
            'message': 'hello', 'conversation_history': [{'role': 'assistant', 'content': 'CLIENT SECRET'}],
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(answer.call_args.kwargs['conversation_history'], [])
        self.assertNotIn('SECRET', str(answer.call_args))
        self.assert_hidden(self.refresh()[0], 'OLD SECRET')
        self.assertEqual(self.refresh()[-1]['content'], 'normal answer')

    def test_unverifiable_explicit_summary_taints_assistant_but_not_user(self):
        with patch.object(MultiAgentChatService, 'chat_with_agent', side_effect=self.fake_step):
            response = self.post_tutor(context_summary='OPAQUE SECRET', provenance={'complete': True, 'sources': []})
        self.assertEqual(response.status_code, 200)
        rows = self.refresh()
        self.assertEqual(rows[0]['content'], 'hello')
        for row in rows[1:]:
            self.assert_hidden(row)

    def test_unknown_source_kind_or_missing_source_is_not_trusted(self):
        for kind, pk in [('unknown', 1), ('article', 987654), ('resource', True), ('resource', None)]:
            origin = Origin(self.student)
            origin.add(kind, pk)
            self.stored('SECRET', origin)
        for row in self.refresh():
            self.assert_hidden(row, 'SECRET')

    def test_evidence_live_grant_is_rechecked(self):
        material(self, text='Evidence quotation')
        card = search(self.scope)['results'][0]
        origin = Origin(self.student)
        origin.add('evidence', card['evidence_id'])
        self.assertTrue(origin.complete)
        self.stored('Evidence quotation', origin)
        self.assertFalse(self.refresh()[0]['redacted'])
        CourseGrant.objects.filter(user=self.student, catalog=self.task.catalog).update(active=False)
        self.assert_hidden(self.refresh()[0], 'Evidence quotation')

    def test_evidence_revoked_material_and_deleted_evidence_fail_closed(self):
        revision = material(self, text='Evidence quotation')
        card = search(self.scope)['results'][0]
        origin = Origin(self.student)
        origin.add('evidence', card['evidence_id'])
        self.stored('Evidence quotation', origin)
        revision.material.revoked_at = timezone.now()
        revision.material.save(update_fields=['revoked_at'])
        self.assert_hidden(self.refresh()[0], 'Evidence quotation')
        from learning_knowledge.models import Evidence
        Evidence.objects.filter(evidence_id=card['evidence_id']).delete()
        self.assert_hidden(self.refresh()[0], 'Evidence quotation')

    def test_practice_chain_sources_include_non_rag_and_verification_influence(self):
        article = self.article(title='hello practice', body='hello practice body')
        with patch.object(MultiAgentChatService, 'chat_with_agent', side_effect=self.fake_step):
            response = self.post_tutor()
        self.assertEqual(response.status_code, 200)
        assistants = list(self.conversation.messages.filter(role='assistant'))
        self.assertEqual(len(assistants), 4)
        # The exercise input is not represented by rag_sources. The server seal
        # must nonetheless cover it, including the downstream verification reply.
        self.assertEqual(assistants[-1].metadata.get('rag_sources'), [])
        for msg in assistants:
            origin = signing.loads(msg.history_origin, salt='ai-assistant-history-v1')
            self.assertIn(['article', str(article.pk)], [source[:2] for source in origin['sources']])
        self.assertFalse(any(row['redacted'] for row in self.refresh()))
        article.status = 'pending'
        article.save(update_fields=['status'])
        self.assertFalse(self.refresh()[0]['redacted'])
        self.assertTrue(all(row['redacted'] for row in self.refresh()[1:]))

    def test_resource_preparation_is_server_hydrated_not_client_citation_metadata(self):
        article = self.article()
        with self.settings(TUTOR_AGENT_ROUTER_ENABLED=True, TUTOR_SPECIALISTS_ENABLED=True), patch(
            'ai_assistant.tutor_request_orchestrator.TutorRequestOrchestrator.call_legacy_answer', return_value='source-backed answer',
        ):
            response = self.client.post(f'/api/ai/conversations/{self.conversation.pk}/chat/', {
                'message': '推荐 hello 学习资源', 'existing_rag_context': {'resources': [{
                    'id': article.pk, 'type': 'article', 'title': 'CLIENT SECRET', 'summary': 'CLIENT SECRET',
                }]}, 'metadata': {'provenance': {'sources': []}},
            }, format='json')
        self.assertEqual(response.status_code, 200)
        assistant = self.conversation.messages.get(role='assistant')
        origin = signing.loads(assistant.history_origin, salt='ai-assistant-history-v1')
        self.assertIn(['article', str(article.pk)], [source[:2] for source in origin['sources']])
        self.assertNotIn('CLIENT SECRET', json.dumps(assistant.metadata))
        self.assertFalse(self.refresh()[-1]['redacted'])
        article.delete()
        self.assert_hidden(self.refresh()[-1], 'source-backed answer')

    def test_stale_retrieved_text_is_not_sealed_against_newer_source(self):
        article = self.article(title='Current title', body='Current body')
        origin = Origin(self.student)
        origin.items([{'id': article.pk, 'type': 'article', 'title': 'Old private title', 'summary': 'Old private body'}])
        self.assertFalse(origin.complete)
        self.stored('Old private quotation', origin)
        self.assert_hidden(self.refresh()[0], 'Old private quotation')

    def test_edit_between_practice_retrieval_and_capture_fails_closed(self):
        article = self.article(title='hello practice', body='hello old private body')
        def edit_then_record(items):
            Article.objects.filter(pk=article.pk).update(content='new public body')
            record_items(items)
        with patch('ai_assistant.service.record_items', side_effect=edit_then_record), patch.object(
            MultiAgentChatService, 'chat_with_agent', side_effect=self.fake_step,
        ):
            response = self.post_tutor()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.refresh()[0]['redacted'])
        self.assertTrue(all(row['redacted'] for row in self.refresh()[1:]))

    def test_whitespace_normalized_bounded_source_projection_is_verified(self):
        article = self.article(title='Long reference title', body='First   sentence.\nSecond sentence.')
        origin = Origin(self.student)
        origin.items([{'id': article.pk, 'type': 'article', 'title': 'Long reference', 'summary': 'First sentence.'}])
        self.assertTrue(origin.complete)
        self.stored('Verified excerpt', origin)
        self.assertFalse(self.refresh()[0]['redacted'])

    def test_cached_diagnosis_name_cannot_claim_current_concept_provenance(self):
        from ai_assistant.history import preparation_origin
        from learning_paths.models import KnowledgeConcept
        concept = KnowledgeConcept.objects.create(name='current name', description='current description')
        origin = preparation_origin(self.student, {'knowledgeDiagnosis': {
            'weakKnowledgePoints': [{'id': concept.pk, 'name': 'old private name'}],
        }})
        self.assertFalse(origin.complete)

    def test_opaque_knowledge_and_malformed_resource_preparation_fail_closed(self):
        from ai_assistant.history import preparation_origin
        for specialists in ({'knowledgeContext': {'definition': 'opaque content', 'sources': []}},
                            {'resources': {'resourceList': {'id': 1}}},
                            {'resources': {'resourceList': [None]}}):
            with self.subTest(specialists=specialists):
                origin = preparation_origin(self.student, specialists)
                self.assertFalse(origin.complete)

    def test_current_staff_permission_is_reused_and_revoked_live(self):
        article = self.article()
        article.status = 'pending'
        article.save(update_fields=['status'])
        self.student.is_staff = True
        self.student.save(update_fields=['is_staff'])
        self.stored('Staff-only quotation', self.source_origin('article', article))
        self.assertFalse(self.refresh()[0]['redacted'])
        type(self.student).objects.filter(pk=self.student.pk).update(is_staff=False)
        # force_authenticate still holds the stale staff object; history must not.
        self.assert_hidden(self.refresh()[0], 'Staff-only quotation')

    def test_controlled_retrieval_captures_evidence_ids_before_projection(self):
        material(self, text='授权材料正文')
        origin = Origin(self.student)
        with track_origin(origin):
            result = MultiAgentChatService().build_knowledge_context(
                '授权', user=self.student, task_context=self.scope,
            )
        self.assertTrue(result['items'])
        self.assertTrue(origin.complete)
        self.assertIn(('evidence', result['items'][0]['evidence_id']), origin.sources)
        self.stored('授权材料正文', origin)
        self.assertFalse(self.refresh()[0]['redacted'])
        CourseGrant.objects.filter(user=self.student, catalog=self.task.catalog).delete()
        self.assert_hidden(self.refresh()[0], '授权材料正文')

    def test_permission_lookup_failure_fails_closed(self):
        article = self.article()
        self.stored('SECRET', self.source_origin('article', article))
        with patch('articles.views.ArticleViewSet.get_queryset', side_effect=RuntimeError('unavailable')):
            self.assert_hidden(self.refresh()[0], 'SECRET')

    def test_untracked_server_write_defaults_to_legacy_denial(self):
        create_message(conversation=self.conversation, role='assistant', content='SECRET')
        self.assert_hidden(self.refresh()[0], 'SECRET')

    def test_origin_collection_is_request_local_across_async_and_fallback(self):
        from ai_assistant.tutor_request_orchestrator import TutorRequestOrchestrator
        from ai_assistant.performance import TutorPerformanceMetrics
        from ai_assistant.views import _run_async
        article = self.article()
        origin = Origin(self.student)
        prep = {'_history_origin': origin, 'teachingContext': {'present': True},
                'performanceMetrics': TutorPerformanceMetrics.create()}
        async def chain(context):
            await sync_to_async(record_items)([{'type': 'article', 'id': article.pk}])
            if context:
                raise ValueError('retry without context')
            return 'answer'
        answer = _run_async(TutorRequestOrchestrator().call_existing_answer_chain_async(prep, chain))
        self.assertEqual(answer, 'answer')
        self.assertTrue(origin.complete)
        self.assertIn(('article', str(article.pk)), origin.sources)
        # Outside the scoped call no lingering recorder may affect this request.
        record_items([{'type': 'unknown', 'id': 1}])
        self.assertTrue(origin.complete)
