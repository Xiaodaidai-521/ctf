"""Regressions for corpus growth, meaningful recall and caller authorization."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from ai_assistant.service import MultiAgentChatService
from learning_knowledge.models import Material
from learning_map.models import CatalogVersion
from rag_ingestion.models import DocumentSource

from .models import LegalClause, LegalDocument, LegalKnowledgeEmbedding
from .services.embedding_service import EmbeddingService
from .services.hashing import sha256_text
from .services.knowledge_retrieval_service import SafeKnowledgeRetrievalService
from .services.retrieval_service import LegalRetrievalService


class CorpusRetrievalRegressionTests(TestCase):
    def setUp(self):
        # These regressions exercise ranking and caller permissions on both
        # databases; availability of real provider credentials is independent.
        configuration = self.settings(EMBEDDING_PROVIDER='', EMBEDDING_MODEL='local-hash-v1', EMBEDDING_DIMENSION=128)
        configuration.enable()
        self.addCleanup(configuration.disable)
        users = get_user_model()
        self.admin = users.objects.create_user(username='recall-admin', role='admin')
        self.teacher = users.objects.create_user(username='recall-teacher', role='teacher')
        self.student = users.objects.create_user(username='recall-student', role='student')
        self.doc_ct = ContentType.objects.get_for_model(DocumentSource)
        self.engine = EmbeddingService(local_only=True)
        self.service = LegalRetrievalService(self.engine)

    def document(self, title, text, *, visibility='internal', chunks=1):
        document = DocumentSource.objects.create(title=title, filename='source.md',
            source_hash=sha256_text(title), visibility=visibility, status='completed',
            metadata={'source_url': 'https://example.org/source'})
        rows = [LegalKnowledgeEmbedding(source_type='document', content_type=self.doc_ct,
            object_id=document.pk, chunk_index=index, title=f'Chunk {index + 1}', text=text,
            text_hash=sha256_text(text), embedding=[1.0] + [0.0] * 127,
            embedding_model='local-hash-v1', embedding_dimension=128) for index in range(chunks)]
        LegalKnowledgeEmbedding.objects.bulk_create(rows)
        return document

    def test_late_document_and_law_survive_more_than_one_thousand_chunks(self):
        self.document('Early document', 'Unrelated filler text.', chunks=1001)
        late = self.document('Telemetry Retention Guide', 'Retain telemetry for seven days.')
        law = LegalDocument.objects.create(title='数据安全法', source_hash='law-late', status='active')
        clause = LegalClause.objects.create(document=law, clause_key='第二十一条',
            article_number='第二十一条', title='第二十一条',
            text='第二十一条 国家建立数据分类分级保护制度。', text_hash='law-body')
        LegalKnowledgeEmbedding.objects.create(source_type='legal_clause',
            content_type=ContentType.objects.get_for_model(LegalClause), object_id=clause.pk,
            title=clause.title, text=clause.text, text_hash=sha256_text(clause.text))
        documents = self.service.retrieve(query='Telemetry Retention Guide', top_k=3, user=self.admin)
        self.assertEqual(documents[0]['object_id'], late.pk)
        self.assertEqual(documents[0]['title'], late.title)
        laws = self.service.retrieve(query='数据分类分级保护制度', top_k=3, user=self.admin)
        self.assertEqual(laws[0]['source_type'], 'legal_clause')
        self.assertEqual(laws[0]['object_id'], clause.pk)

    def test_character_vector_similarity_cannot_return_unanswerable_evidence(self):
        self.document('Known topic', 'Authentication and password management.')
        with patch.object(self.engine, 'embed_local_text', return_value=[1.0] + [0.0] * 127):
            self.assertEqual(self.service.retrieve(query='zxqv987654_no_matching_corpus', user=self.admin), [])
        self.assertEqual(self.service.retrieve(query='火星量子香蕉税法', user=self.admin), [])

    def test_common_alias_cannot_mask_an_unrelated_question(self):
        self.document('个人信息保护', '依法保护个人信息，履行个人信息处理义务。')
        self.assertEqual(self.service.retrieve(query='个人信息 火星量子香蕉税法', user=self.admin), [])

    def test_overlapping_chunks_do_not_crowd_out_another_relevant_source(self):
        first = self.document('Logging Guide', 'Logging audit logs logging audit logs.', chunks=8)
        second = self.document('Audit Logs', 'Audit logs support retention review.')
        results = self.service.retrieve(query='audit logs', top_k=3, user=self.admin)
        self.assertIn(second.pk, [row['object_id'] for row in results])
        self.assertLessEqual(sum(row['object_id'] == first.pk for row in results), 2)
        scoped = self.service.retrieve(query='audit logs', top_k=5, user=self.admin,
            filters={'source_type': 'document', 'object_id': first.pk})
        self.assertEqual(len(scoped), 5)

    def test_bilingual_security_terms_recall_the_original_english_title(self):
        source = self.document('Cross Site Scripting Prevention Cheat Sheet',
                               'Prevent cross site scripting with output encoding.')
        found = self.service.retrieve(query='跨站脚本攻击防护', user=self.teacher)
        self.assertEqual(found[0]['object_id'], source.pk)
        self.assertEqual(found[0]['retrieval'], 'lexical')
        self.assertEqual(found[0]['vector_space'], '')

    def test_management_assistant_receives_documents_only_under_live_permissions(self):
        source = self.document('SQL Injection Prevention', 'Prevent SQL injection with prepared statements.')
        safe = SafeKnowledgeRetrievalService(self.service)
        for actor in (self.admin, self.teacher):
            self.assertTrue(safe.retrieve(query='SQL injection', user=actor))
        self.assertEqual(safe.retrieve(query='SQL injection', user=self.student), [])
        self.assertEqual(safe.retrieve(query='SQL injection'), [])
        source.visibility = 'staff'
        source.save(update_fields=['visibility'])
        self.assertEqual(safe.retrieve(query='SQL injection', user=self.teacher), [])
        self.assertTrue(safe.retrieve(query='SQL injection', user=self.admin))
        source.status = 'failed'
        source.save(update_fields=['status'])
        self.assertEqual(safe.retrieve(query='SQL injection', user=self.admin), [])

    def test_source_filter_cannot_expand_the_assistant_allowlist(self):
        self.document('Public-looking document', 'SQL injection', visibility='learner')
        safe = SafeKnowledgeRetrievalService(self.service)
        for filters in ({'source_type': 'document'}, {'source_type': []}, {'source_type': 'challenge'}):
            self.assertEqual(safe.retrieve(query='SQL injection', user=self.student, extra_filters=filters), [])
        with self.settings(KNOWLEDGE_RAG_SAFE_SOURCE_TYPES=['challenge', 'document']):
            self.assertEqual(SafeKnowledgeRetrievalService(self.service).retrieve(query='SQL injection', user=self.student), [])

    def test_registered_course_document_stays_in_the_course_scope_gateway(self):
        source = self.document('Restricted lesson', 'SQL injection teacher answer.')
        catalog = CatalogVersion.objects.create(version='recall-course', label='Course')
        Material.objects.create(catalog=catalog, owner=self.admin, material_class='teacher_answer',
                                source_type='document', source_object_id=source.pk)
        self.assertEqual(SafeKnowledgeRetrievalService(self.service).retrieve(query='SQL injection', user=self.admin), [])

    def test_modified_chunk_hash_is_not_retrieved(self):
        source = self.document('SQL Injection Prevention', 'Use prepared statements for SQL injection.')
        LegalKnowledgeEmbedding.objects.filter(object_id=source.pk).update(text='UNVERIFIED SQL injection')
        self.assertEqual(self.service.retrieve(query='SQL injection', user=self.admin), [])

    def test_visibility_is_rechecked_after_ranking(self):
        source = self.document('SQL Injection Prevention', 'Use prepared statements for SQL injection.')
        from .services.lexical_ranking import rank_chunks

        def withdraw(*args, **kwargs):
            ranked = rank_chunks(*args, **kwargs)
            source.visibility = 'staff'
            source.save(update_fields=['visibility'])
            return ranked

        with patch('legal_kb.services.retrieval_service.rank_chunks', side_effect=withdraw):
            self.assertEqual(self.service.retrieve(query='SQL injection', user=self.teacher), [])

    def test_knowledge_context_propagates_the_authenticated_caller(self):
        source = self.document('SQL Injection Prevention', 'Prepared statements prevent SQL injection.')
        service = MultiAgentChatService()
        with patch.object(service, 'search_simple_knowledge', return_value={'items': []}):
            admin = service.build_knowledge_context('SQL injection', user=self.admin)
            student = service.build_knowledge_context('SQL injection', user=self.student)
            anonymous = service.build_knowledge_context('SQL injection')
        self.assertIn(source.title, admin['context_text'])
        self.assertEqual(student['semantic_count'], 0)
        self.assertEqual(anonymous['semantic_count'], 0)

    def test_real_catalogue_list_and_detail_keep_source_attribution(self):
        source = self.document('SQL Injection Prevention', 'Use prepared statements.')
        client = APIClient()
        client.force_authenticate(self.teacher)
        listing = client.get('/api/legal-kb/library/', {'source_type': 'document'})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['results'][0]['object_id'], source.pk)
        detail = client.get(f'/api/legal-kb/library/document/{source.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail['Cache-Control'], 'private, no-store')
        self.assertEqual(detail.data['source_url'], 'https://example.org/source')
        self.assertEqual(detail.data['chunks'][0]['text'], 'Use prepared statements.')
