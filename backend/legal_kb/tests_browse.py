"""Catalogue authorization and existing student Scope contract regressions."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from articles.models import Article
from learning_knowledge.models import CourseGrant, TaskMaterial
from learning_knowledge.tests.helpers import material, setup_case
from learning_paths.models import KnowledgeConcept
from rag_ingestion.models import DocumentSource
from resources.models import Resource
from users.models import CTFUser

from .models import LegalClause, LegalDocument, LegalKnowledgeEmbedding
from .services.hashing import sha256_text


class LibraryAPITests(TestCase):
    def setUp(self):
        self.teacher = CTFUser.objects.create_user(username='library-teacher', role='teacher')
        self.admin = CTFUser.objects.create_user(username='library-admin', role='admin')
        self.student = CTFUser.objects.create_user(username='library-student', role='student')
        self.client = APIClient()
        self.client.force_authenticate(self.teacher)
        self.document = LegalDocument.objects.create(title='授权资料', full_text='第一条 核查授权范围。', source_hash='legal')
        self.clause = LegalClause.objects.create(document=self.document, clause_key='第一条', article_number='第一条',
                                                chapter='总则', text=self.document.full_text, text_hash=sha256_text(self.document.full_text))
        self.article = Article.objects.create(title='安全文章', content='中文口令核查指南', author=self.teacher, status='approved')
        self.embed('article', self.article, self.article.content)

    def embed(self, kind, obj, text, **kwargs):
        return LegalKnowledgeEmbedding.objects.create(source_type=kind, content_type=ContentType.objects.get_for_model(obj),
            object_id=obj.pk, text=text, text_hash=sha256_text(text), embedding=[1, 0], embedding_model='test', **kwargs)

    def listing(self, **params):
        return self.client.get('/api/legal-kb/library/', params)

    def detail(self, kind, obj):
        return self.client.get(f'/api/legal-kb/library/{kind}/{obj.pk}/')

    def test_legal_browse_search_and_clause_provenance(self):
        self.embed('legal_clause', self.clause, self.clause.text)
        response = self.listing(q='授权范围')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        row = response.data['results'][0]
        self.assertEqual(row['title'], self.document.title)
        self.assertEqual(row['source_label'], '法律库文档')
        self.assertIn('第一条', row['locator'])
        detail = self.detail('legal_document', self.document)
        self.assertEqual(detail.data['full_text'], self.document.full_text)
        self.assertEqual(detail.data['chunks'][0]['index_status'], 'indexed')
        self.assertEqual(self.listing(q='not-present').data['count'], 0)

    def test_platform_browse_only_indexed_originals_and_keyword_chunk(self):
        Article.objects.create(title='未索引文章', content='中文', author=self.teacher, status='approved')
        response = self.listing(group='platform', q='口令')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual(row['id'], f'article:{self.article.pk}')
        self.assertEqual(row['source_path'], f'/community/article/{self.article.pk}')
        self.assertEqual(self.detail('article', self.article).data['chunks'][0]['text'], self.article.content)
        self.assertNotIn('embedding', self.detail('article', self.article).data)
        self.assertEqual(Article.objects.count(), 2)

    def test_platform_category_filters_cover_resources_and_concepts(self):
        resource = Resource.objects.create(title='资源说明', description='授权核查', resource_type='document', uploader=self.teacher, status='approved')
        concept = KnowledgeConcept.objects.create(name='边界验证', slug='boundary', description='授权边界', concept_type='tech')
        self.embed('resource', resource, resource.description)
        self.embed('knowledge_concept', concept, concept.description)
        for kind, obj in [('resource', resource), ('knowledge_concept', concept)]:
            with self.subTest(kind=kind):
                rows = self.listing(group='platform', source_type=kind).data['results']
                self.assertEqual([row['object_id'] for row in rows], [obj.pk])
                self.assertTrue(self.detail(kind, obj).data['source_path'].startswith('/'))

    def test_live_upload_visibility_tightening_removes_list_and_detail(self):
        upload = DocumentSource.objects.create(title='内部材料', filename='lesson.md', source_hash='upload', visibility='internal', status='completed')
        self.embed('document', upload, '内部授权教学片段')
        self.assertEqual(self.detail('document', upload).status_code, 200)
        upload.visibility = 'staff'
        upload.save(update_fields=['visibility'])
        self.assertEqual(self.listing(source_type='document').data['count'], 0)
        self.assertEqual(self.detail('document', upload).status_code, 404)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.detail('document', upload).data['chunks'][0]['text'], '内部授权教学片段')

    def test_failed_upload_does_not_expose_old_chunks_or_error_metadata(self):
        upload = DocumentSource.objects.create(title='失败上传', filename='lesson.md', source_hash='failed', visibility='internal', status='failed', error_message='SECRET', metadata={'token': 'SECRET'})
        self.embed('document', upload, 'SECRET OLD BODY')
        response = self.detail('document', upload)
        self.assertEqual(response.data['chunks'], [])
        self.assertNotIn('SECRET', str(response.data))
        self.assertEqual(self.listing(source_type='document', q='SECRET').data['count'], 0)

    def catalogue_sources(self):
        upload = DocumentSource.objects.create(title='内部资料', filename='lesson.md', source_hash='catalogue-upload',
                                               visibility='internal', status='completed')
        resource = Resource.objects.create(title='资源说明', description='资源授权说明', resource_type='document',
                                           uploader=self.teacher, status='approved')
        concept = KnowledgeConcept.objects.create(name='边界验证', slug='catalogue-boundary',
                                                   description='知识点授权边界', concept_type='tech')
        self.embed('document', upload, '上传文档授权正文')
        self.embed('resource', resource, resource.description)
        self.embed('knowledge_concept', concept, concept.description)
        return [
            ('legal', 'legal_document', self.document, self.document.full_text),
            ('legal', 'document', upload, '上传文档授权正文'),
            ('platform', 'article', self.article, self.article.content),
            ('platform', 'resource', resource, resource.description),
            ('platform', 'knowledge_concept', concept, concept.description),
        ]

    def test_student_and_anonymous_cannot_use_staff_catalogue_or_detail(self):
        sources = self.catalogue_sources()
        requests = [({}, '/api/legal-kb/library/'),
                    ({'group': 'legal'}, '/api/legal-kb/library/'),
                    ({'group': 'platform'}, '/api/legal-kb/library/')]
        for group, kind, obj, text in sources:
            for query in ['', text]:
                requests.append(({'group': group, 'source_type': kind, 'q': query}, '/api/legal-kb/library/'))
            requests.append(({}, f'/api/legal-kb/library/{kind}/{obj.pk}/'))
        for actor in [self.student, None]:
            self.client.force_authenticate(actor)
            for params, url in requests:
                with self.subTest(actor=actor, url=url, params=params):
                    response = self.client.get(url, params)
                    self.assertIn(response.status_code, [403] if actor else [401, 403])
                    self.assertNotIn('results', response.data)
                    self.assertNotIn('chunks', response.data)
                    for _, _, _, text in sources:
                        self.assertNotIn(text, str(response.data))

    def test_teacher_and_nonstaff_admin_can_browse_all_catalogue_sources(self):
        sources = self.catalogue_sources()
        self.assertFalse(self.admin.is_staff)
        for actor in [self.teacher, self.admin]:
            self.client.force_authenticate(actor)
            for params in [{}, {'group': 'legal'}, {'group': 'platform'}]:
                with self.subTest(actor=actor, params=params):
                    response = self.listing(**params)
                    self.assertEqual(response.status_code, 200)
                    expected = {f'{kind}:{obj.pk}' for group, kind, obj, _ in sources
                                if group == params.get('group', 'legal')}
                    self.assertEqual({row['id'] for row in response.data['results']}, expected)
            for group, kind, obj, text in sources:
                with self.subTest(actor=actor, kind=kind):
                    for query in ['', text]:
                        response = self.listing(group=group, source_type=kind, q=query)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual([row['id'] for row in response.data['results']], [f'{kind}:{obj.pk}'])
                    detail = self.detail(kind, obj)
                    self.assertEqual(detail.status_code, 200)
                    self.assertEqual(detail.data['id'], f'{kind}:{obj.pk}')
                    self.assertEqual(detail.data['chunks'][0]['text'], text)

    def test_validation_and_read_only_contract(self):
        for params in [{'group': 'teaching'}, {'source_type': 'challenge'}, {'page': 0}, {'q': 'a' * 501},
                       {'group': 'legal', 'source_type': 'article'}, {'include_raw': 'true'}]:
            self.assertEqual(self.listing(**params).status_code, 400)
        self.assertEqual(self.client.post('/api/legal-kb/library/', {}, format='json').status_code, 405)
        self.assertEqual(self.client.get('/api/legal-kb/library/challenge/1/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/legal-kb/library/article/{self.article.pk}/?scope=admin').status_code, 400)

    def test_pagination_stable_and_does_not_truncate_to_retrieval_top_k(self):
        LegalDocument.objects.bulk_create([LegalDocument(title=f'法规-{index:02}', full_text='正文', source_hash=f'page-{index}') for index in range(25)])
        first, second = self.listing(), self.listing(page=2)
        self.assertEqual(first.data['count'], 26)
        self.assertEqual(len(first.data['results']), 20)
        self.assertEqual(len(second.data['results']), 6)
        self.assertFalse({row['id'] for row in first.data['results']} & {row['id'] for row in second.data['results']})

    def test_removed_or_unapproved_platform_source_is_not_browsable(self):
        self.article.status = 'rejected'
        self.article.save(update_fields=['status'])
        self.assertEqual(self.listing(group='platform').data['count'], 0)
        self.assertEqual(self.detail('article', self.article).status_code, 404)
        self.article.delete()
        self.assertEqual(self.listing(group='platform').data['count'], 0)

    def test_bad_chunk_hash_and_arbitrary_metadata_are_not_projected(self):
        LegalKnowledgeEmbedding.objects.filter(source_type='article').update(text_hash='bad', metadata={'secret': 'PRIVATE'})
        self.assertEqual(self.detail('article', self.article).data['chunks'], [])
        self.assertNotIn('PRIVATE', str(self.listing(group='platform').data))

    def test_wrong_content_type_is_not_a_platform_index(self):
        LegalKnowledgeEmbedding.objects.filter(source_type='article').update(content_type=ContentType.objects.get_for_model(LegalDocument))
        self.assertEqual(self.listing(group='platform').data['count'], 0)
        self.assertEqual(self.detail('article', self.article).status_code, 404)

    def test_browsing_never_invokes_embedding_or_answer_generation(self):
        with (patch('legal_kb.services.embedding_service.EmbeddingService.embed_text', side_effect=AssertionError('No embedding')),
              patch('legal_kb.services.rag_answer_service.RagAnswerService.answer', side_effect=AssertionError('No LLM'))):
            self.assertEqual(self.listing(group='platform', q='口令').status_code, 200)


class StudentLibraryContractTests(TestCase):
    def setUp(self):
        setup_case(self)
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def search(self, query=''):
        return self.client.post('/api/learning-knowledge/search/', {
            'attempt_id': str(self.attempt.attempt_id), 'request_id': 'library-round3', 'query': query,
        }, format='json')

    def test_static_and_keyword_browse_use_only_authorized_lessons(self):
        lesson = material(self, text='密码哈希用于核验口令。')
        for kind in ['hint', 'teacher_answer', 'grading_secret', 'student_analysis']:
            material(self, kind, text=f'密码 SECRET-{kind}', level=1 if kind == 'hint' else None)
        material(self, status='draft', text='密码 SECRET-draft')
        for query in ['', '口令']:
            response = self.search(query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row['material_id'] for row in response.data['results']], [str(lesson.material.material_id)])
            self.assertNotIn('SECRET', str(response.data))
            card = response.data['results'][0]
            self.assertEqual(self.client.get(card['view_endpoint']).status_code, 200)
            self.assertEqual(card['locator'], {'paragraph': 1})

    def test_removing_task_binding_revokes_cached_list_search_and_detail(self):
        lesson = material(self)
        card = self.search().data['results'][0]
        TaskMaterial.objects.filter(revision=lesson).delete()
        for query in ['', '授权']:
            self.assertEqual(self.search(query).data['results'], [])
        self.assertEqual(self.client.get(card['view_endpoint']).status_code, 404)

    def test_course_revocation_and_cross_student_attempt_fail_closed(self):
        material(self)
        card = self.search().data['results'][0]
        self.client.force_authenticate(self.other)
        self.assertEqual(self.search().status_code, 404)
        self.assertEqual(self.client.get(card['view_endpoint']).status_code, 404)
        self.client.force_authenticate(self.student)
        CourseGrant.objects.filter(user=self.student).update(active=False)
        self.assertEqual(self.search('授权').status_code, 404)
        self.assertEqual(self.client.get(card['view_endpoint']).status_code, 404)

    def test_expired_revision_hides_previous_evidence_and_search(self):
        lesson = material(self)
        card = self.search().data['results'][0]
        lesson.recheck_due_at = timezone.now() - timedelta(seconds=1)
        lesson.save(update_fields=['recheck_due_at'])
        self.assertEqual(self.search().data['results'], [])
        self.assertEqual(self.client.get(card['view_endpoint']).status_code, 404)

    def test_registered_sources_stay_out_of_staff_legacy_catalogue(self):
        article = Article.objects.create(title='课程私有文章', content='密码', author=self.teacher, status='approved')
        material(self, text=article.content, source_type='article', source_id=article.pk)
        LegalKnowledgeEmbedding.objects.create(source_type='article', content_type=ContentType.objects.get_for_model(article),
            object_id=article.pk, text=article.content, text_hash=sha256_text(article.content))
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get('/api/legal-kb/library/?group=platform').data['count'], 0)
        self.assertEqual(self.client.get(f'/api/legal-kb/library/article/{article.pk}/').status_code, 404)

    def test_teacher_material_keyword_search_matches_body_and_keeps_management_scope(self):
        lesson = material(self, text='正文专用关键字：审计轨迹。')
        material(self, 'grading_secret', text='审计轨迹 SECRET')
        self.client.force_authenticate(self.teacher)
        response = self.client.get('/api/teaching-knowledge/material-search/', {'q': '审计轨迹'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual([row['material_id'] for row in response.data['results']], [str(lesson.material.material_id)])
        self.assertNotIn('SECRET', str(response.data))
        self.assertNotIn('source_snapshot', str(response.data))
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get('/api/teaching-knowledge/material-search/', {'q': '审计轨迹'}).status_code, 403)

    def test_student_cannot_use_management_search_even_with_course_or_staff_grants(self):
        material(self, text='正文专用关键字：审计轨迹。')
        for staff in [False, True]:
            self.student.is_staff = staff
            self.student.save(update_fields=['is_staff'])
            for params in [{}, {'q': ''}, {'q': '审计轨迹'}, {'q': 'no-match'}, {'q': 'a' * 501}, {'role': 'admin'}]:
                with self.subTest(staff=staff, params=params):
                    response = self.client.get('/api/teaching-knowledge/material-search/', params)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response['Cache-Control'], 'private, no-store')
                    self.assertNotIn('results', response.data)
                    self.assertNotIn('审计轨迹', str(response.data))
        # Keep the old management list contract; only the new search API is gated.
        legacy_list = self.client.get('/api/teaching-knowledge/materials/')
        self.assertEqual(legacy_list.status_code, 200)
        self.assertEqual(legacy_list.data['results'], [])

    def test_anonymous_cannot_use_management_search(self):
        self.client.force_authenticate(None)
        for params in [{}, {'q': '审计轨迹'}]:
            with self.subTest(params=params):
                response = self.client.get('/api/teaching-knowledge/material-search/', params)
                self.assertIn(response.status_code, [401, 403])
                self.assertNotIn('results', response.data)

    def test_admin_management_search_preserves_module_admin_and_secret_permissions(self):
        lesson = material(self, text='正文专用关键字：审计轨迹。')
        material(self, 'grading_secret', text='审计轨迹 SECRET')
        for staff in [False, True]:
            self.admin.is_staff = staff
            self.admin.save(update_fields=['is_staff'])
            self.client.force_authenticate(self.admin)
            for params in [{}, {'q': '审计轨迹'}]:
                with self.subTest(staff=staff, params=params):
                    response = self.client.get('/api/teaching-knowledge/material-search/', params)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual([row['material_id'] for row in response.data['results']],
                                     [str(lesson.material.material_id)])
                    self.assertNotIn('SECRET', str(response.data))
                    self.assertNotIn('source_snapshot', str(response.data))

    def test_management_search_rechecks_teacher_course_grant(self):
        material(self, text='课堂授权')
        self.client.force_authenticate(self.teacher)
        self.assertEqual(len(self.client.get('/api/teaching-knowledge/material-search/').data['results']), 1)
        CourseGrant.objects.filter(user=self.teacher).update(active=False)
        self.assertEqual(self.client.get('/api/teaching-knowledge/material-search/').data['results'], [])

    def test_management_search_is_additive_read_only_and_validated(self):
        material(self)
        self.client.force_authenticate(self.teacher)
        before = self.client.get('/api/teaching-knowledge/materials/').data
        self.assertEqual(self.client.get('/api/teaching-knowledge/material-search/').data, before)
        for params in [{'q': 'a' * 501}, {'role': 'admin'}]:
            self.assertEqual(self.client.get('/api/teaching-knowledge/material-search/', params).status_code, 400)
        self.assertEqual(self.client.post('/api/teaching-knowledge/material-search/', {}, format='json').status_code, 405)

    def test_registered_clause_parent_full_text_cannot_escape(self):
        document = LegalDocument.objects.create(title='课程法条', full_text='SECRET', source_hash='registered')
        clause = LegalClause.objects.create(document=document, clause_key='一', text='SECRET', text_hash=sha256_text('SECRET'))
        material(self, 'teacher_answer', text='SECRET', source_type='legal_clause', source_id=clause.pk)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get('/api/legal-kb/library/').data['count'], 0)
        self.assertEqual(self.client.get(f'/api/legal-kb/library/legal_document/{document.pk}/').status_code, 404)
