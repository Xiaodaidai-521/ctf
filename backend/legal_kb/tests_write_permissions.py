"""Knowledge write API inventory, command roles, and platform trigger boundaries."""

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import Resolver404, resolve
from rest_framework.test import APIClient

from articles.models import Article, Category, Comment
from challenges.models import Challenge, Category as ChallengeCategory
from learning_paths.models import KnowledgeConcept
from resources.models import Resource, ResourceCache
from .models import KbIngestionJob, LegalCase, LegalClause, LegalDocument, LegalKnowledgeEmbedding, LegalTemplate
from .services.embedding_service import EmbeddingService
from .services.ingestion_service import LegalKbIngestionService
from .services.platform_indexing_service import PlatformContentIndexingService


@override_settings(EMBEDDING_PROVIDER='local')
class LegalWritePermissionTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.student = users.objects.create_user(username='legal-write-student', role='student')
        self.teacher = users.objects.create_user(username='legal-write-teacher', role='teacher')
        self.admin = users.objects.create_user(username='legal-write-admin', role='admin')
        self.client = APIClient()
        self.document = LegalDocument.objects.create(
            title='Synthetic law', full_text='第一条 仅在授权范围内检查。', source_hash='a' * 64,
        )
        self.clause = LegalClause.objects.create(
            document=self.document, clause_key='第一条', text='仅在授权范围内检查。', text_hash='b' * 64,
        )
        self.case = LegalCase.objects.create(title='Synthetic case', source_hash='c' * 64)
        self.template = LegalTemplate.objects.create(title='Synthetic template', content='Record evidence.')

    def families(self):
        return (
            ('documents', self.document, {'title': 'New law', 'full_text': '第一条 保存证据。'}),
            ('clauses', self.clause, {'document': self.document.pk, 'clause_key': '第二条', 'text': '保存证据。'}),
            ('cases', self.case, {'title': 'New case', 'summary': 'Synthetic evidence.'}),
            ('templates', self.template, {'title': 'New template', 'content': 'Evidence record.'}),
        )

    def test_student_denied_all_legal_crud_families_and_methods(self):
        self.client.force_authenticate(self.student)
        for family, instance, payload in self.families():
            for method in ('post', 'put', 'patch', 'delete'):
                url = f'/api/legal-kb/{family}/' + ('' if method == 'post' else f'{instance.pk}/')
                with self.subTest(family=family, method=method):
                    response = getattr(self.client, method)(url, payload, format='json')
                    self.assertEqual(response.status_code, 403, response.data)
            self.assertEqual(type(instance).objects.count(), 1)
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_teacher_can_create_update_patch_delete_all_legal_families(self):
        self.client.force_authenticate(self.teacher)
        # Delete documents last so the clause fixture is still valid.
        for family, _instance, payload in reversed(self.families()):
            with self.subTest(family=family):
                response = self.client.post(f'/api/legal-kb/{family}/', payload, format='json')
                self.assertEqual(response.status_code, 201, response.data)
                url = f'/api/legal-kb/{family}/{response.data["id"]}/'
                response = self.client.put(url, payload, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                response = self.client.patch(url, {'title': 'Teacher update'}, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(self.client.delete(url).status_code, 204)

    def test_student_ingest_denied_without_job_or_embedding(self):
        self.client.force_authenticate(self.student)
        with patch('legal_kb.views.LegalKbIngestionService') as service:
            response = self.client.post(f'/api/legal-kb/documents/{self.document.pk}/ingest/')
        self.assertEqual(response.status_code, 403)
        service.assert_not_called()
        self.assertFalse(KbIngestionJob.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_teacher_and_admin_ingest_success(self):
        for actor in (self.teacher, self.admin):
            with self.subTest(role=actor.role):
                self.client.force_authenticate(actor)
                response = self.client.post(f'/api/legal-kb/documents/{self.document.pk}/ingest/')
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data['status'], 'completed')
                self.assertGreater(response.data['embedded_chunks'], 0)
        self.assertEqual(KbIngestionJob.objects.count(), 2)
        self.assertEqual(LegalKnowledgeEmbedding.objects.count(), 1)

    def test_readonly_jobs_embeddings_and_logs_have_no_write_action(self):
        for family in ('ingestion-jobs', 'embeddings', 'retrieval-logs'):
            for method in ('post', 'put', 'patch', 'delete'):
                url = f'/api/legal-kb/{family}/' + ('' if method == 'post' else '1/')
                with self.subTest(family=family, method=method):
                    self.client.force_authenticate(self.student)
                    self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 403)
                    self.client.force_authenticate(self.admin)
                    self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 405)
        self.assertFalse(KbIngestionJob.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_prepare_rebuild_fetch_and_platform_index_commands_are_not_api_routes(self):
        for path in ('prepare', 'rebuild', 'prepare_legal_kb', 'rebuild_legal_kb', 'fetch_official_laws', 'index-platform'):
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(f'/api/legal-kb/{path}/')

    def test_registered_document_still_cannot_be_reingested_by_teacher(self):
        from learning_knowledge.models import Material
        from learning_map.models import CatalogVersion
        catalog = CatalogVersion.objects.create(version='legal-write-scope', label='Synthetic course')
        Material.objects.create(
            catalog=catalog, owner=self.teacher, material_class='lesson',
            source_type='legal_clause', source_object_id=self.clause.pk,
        )
        self.client.force_authenticate(self.teacher)
        with patch('legal_kb.views.LegalKbIngestionService') as service:
            self.assertEqual(self.client.post(f'/api/legal-kb/documents/{self.document.pk}/ingest/').status_code, 404)
        service.assert_not_called()

    def test_legal_service_denies_explicit_student_before_job_write(self):
        with patch.object(EmbeddingService, 'embed_text') as embed:
            with self.assertRaises(ValueError):
                LegalKbIngestionService().ingest_document(self.document, actor=self.student)
        embed.assert_not_called()
        self.assertFalse(KbIngestionJob.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_prepare_command_denies_student_before_seed_or_import(self):
        with patch('legal_kb.management.commands.prepare_legal_kb.PlatformContentIndexingService') as indexer:
            with self.assertRaises(CommandError):
                call_command('prepare_legal_kb', actor=self.student.username, seed_sql_exercises=True,
                             platform_only=True, stdout=io.StringIO())
        indexer.assert_not_called()
        self.assertFalse(Challenge.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_prepare_teacher_imports_and_indexes_local_law(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            (Path(directory) / 'law.json').write_text(json.dumps({
                'title': 'Teacher imported law', 'full_text': '第一条 保存可复核的证据。',
            }), encoding='utf-8')
            call_command('prepare_legal_kb', actor=self.teacher.username, laws_only=True,
                         laws_dir=directory, stdout=io.StringIO())
        document = LegalDocument.objects.get(title='Teacher imported law')
        self.assertEqual(document.created_by, self.teacher)
        self.assertTrue(KbIngestionJob.objects.filter(document=document, status='completed').exists())
        self.assertTrue(LegalKnowledgeEmbedding.objects.exists())

    def test_fetch_command_denies_student_before_network_or_files(self):
        with patch('legal_kb.management.commands.fetch_official_laws.FlkClient') as client:
            with self.assertRaises(CommandError):
                call_command('fetch_official_laws', actor=self.student.username, stdout=io.StringIO())
        client.assert_not_called()
        self.assertEqual(LegalDocument.objects.count(), 1)
        self.assertFalse(KbIngestionJob.objects.exists())

    def test_fetch_command_teacher_imports_with_mocked_official_source(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch('legal_kb.management.commands.fetch_official_laws.FlkClient') as client:
                client.return_value.fetch_target.return_value = {
                    'title': 'Teacher fetched fixture', 'document_type': 'law',
                    'full_text': '第一条 保存教学证据。', 'metadata': {},
                }
                call_command('fetch_official_laws', actor=self.teacher.username, query=['Synthetic law'],
                             cache_dir=directory, stdout=io.StringIO())
        document = LegalDocument.objects.get(title='Teacher fetched fixture')
        self.assertEqual(document.created_by, self.teacher)
        self.assertTrue(KbIngestionJob.objects.filter(document=document, status='completed').exists())

    def test_rebuild_denies_student_and_keeps_teacher_success(self):
        LegalKbIngestionService().ingest_document(self.document, actor=self.teacher)
        with patch.object(EmbeddingService, 'embed_many') as embed:
            with self.assertRaises(CommandError):
                call_command('rebuild_legal_kb', actor=self.student.username, stdout=io.StringIO())
        embed.assert_not_called()
        output = io.StringIO()
        call_command('rebuild_legal_kb', actor=self.teacher.username, stdout=output)
        self.assertIn('Rebuilt chunks: 1', output.getvalue())


@override_settings(EMBEDDING_PROVIDER='local')
class PlatformWriteBoundaryTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.student = users.objects.create_user(username='platform-write-student', role='student')
        self.teacher = users.objects.create_user(username='platform-write-teacher', role='teacher')
        self.admin = users.objects.create_user(username='platform-write-admin', role='admin', is_staff=True)
        self.client = APIClient()
        self.category = Category.objects.create(name='Synthetic community')
        self.article = Article.objects.create(
            title='Community lesson', content='Only work within the authorized scope.',
            category=self.category, author=self.student, status='approved',
        )
        self.resource = Resource.objects.create(
            title='Resource fixture', description='Keep evidence.', resource_type='document',
            uploader=self.teacher, status='approved',
        )
        self.concept = KnowledgeConcept.objects.create(name='Scope boundary', slug='scope-boundary', description='Keep authorization explicit.')
        self.challenge = Challenge.objects.create(
            title='Challenge fixture', description='Synthetic challenge.', difficulty='easy', score=100,
            category=ChallengeCategory.objects.create(name='Test'), flag='flag{fixture}',
        )

    def test_student_cannot_index_any_platform_source_even_with_local_provider(self):
        indexer = PlatformContentIndexingService()
        methods = ('index_all', 'index_articles', 'index_resources', 'index_knowledge_concepts',
                   'index_challenges', 'index_challenge_knowledge_packs')
        with patch.object(indexer.embedding_service, 'embed_text') as embed:
            for method in methods:
                with self.subTest(method=method), self.assertRaises(ValueError):
                    getattr(indexer, method)(actor=self.student)
        embed.assert_not_called()
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_teacher_explicitly_indexes_articles_resources_and_concepts(self):
        indexer = PlatformContentIndexingService()
        for method, source_type in (
            ('index_articles', 'article'), ('index_resources', 'resource'),
            ('index_knowledge_concepts', 'knowledge_concept'),
        ):
            with self.subTest(method=method):
                result = getattr(indexer, method)(actor=self.teacher)
                self.assertEqual(result.indexed_objects, 1)
                self.assertGreater(result.embedded_chunks, 0)
                self.assertTrue(LegalKnowledgeEmbedding.objects.filter(source_type=source_type).exists())

    def test_student_denied_concept_and_challenge_crud(self):
        self.client.force_authenticate(self.student)
        for root, instance in (
            ('/api/learning-paths/knowledge-concepts/', self.concept),
            ('/api/challenges/challenges/', self.challenge),
        ):
            for method in ('post', 'put', 'patch', 'delete'):
                with self.subTest(root=root, method=method):
                    url = root if method == 'post' else f'{root}{instance.pk}/'
                    self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 403)
        self.assertTrue(KnowledgeConcept.objects.filter(pk=self.concept.pk).exists())
        self.assertTrue(Challenge.objects.filter(pk=self.challenge.pk).exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_student_denied_resource_upload_review_and_article_review(self):
        self.client.force_authenticate(self.student)
        for url, payload in (
            ('/api/resources/upload/', {}),
            ('/api/resources/review/', {'resource_id': self.resource.pk, 'status': 'approved'}),
            (f'/api/articles/articles/{self.article.pk}/review/', {'status': 'approved'}),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, payload, format='json').status_code, 403)
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_teacher_concept_and_resource_create_do_not_implicitly_index(self):
        self.client.force_authenticate(self.teacher)
        with patch.object(EmbeddingService, 'embed_text') as embed:
            response = self.client.post('/api/learning-paths/knowledge-concepts/', {
                'name': 'Teacher concept', 'description': 'Synthetic teaching evidence.', 'concept_type': 'def',
            }, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
                with override_settings(MEDIA_ROOT=directory):
                    response = self.client.post('/api/resources/upload/', {
                        'title': 'Teacher source', 'description': 'Synthetic evidence.', 'resource_type': 'document',
                        'category': 'Teaching',
                        'file': SimpleUploadedFile('lesson.txt', b'Teaching fixture.', content_type='text/plain'),
                    }, format='multipart')
                    self.assertEqual(response.status_code, 201, response.data)
        embed.assert_not_called()
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_community_create_update_delete_contract_does_not_write_index(self):
        self.client.force_authenticate(self.student)
        # A sentinel proves neither index insertion nor deletion occurs on community saves.
        embedding = LegalKnowledgeEmbedding.objects.create(
            source_type='article', content_type=ContentType.objects.get_for_model(Article),
            object_id=self.article.pk, chunk_index=0, title=self.article.title,
            text=self.article.content, text_hash='d' * 64, embedding=[1.0],
        )
        with patch.object(EmbeddingService, 'embed_text') as embed:
            created = self.client.post('/api/articles/articles/', {
                'title': 'Student contribution', 'content': 'Community source only.', 'category': self.category.pk,
                'status': 'approved',
            }, format='json')
            self.assertEqual(created.status_code, 201, created.data)
            self.assertEqual(Article.objects.get(title='Student contribution').status, 'pending')
            response = self.client.patch(f'/api/articles/articles/{self.article.pk}/', {
                'content': 'Updated community text.',
            }, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, 'pending')
            # Existing API only exposes approved sources to nonstaff authors.
            Article.objects.filter(pk=self.article.pk).update(status='approved')
            self.assertEqual(self.client.delete(f'/api/articles/articles/{self.article.pk}/').status_code, 204)
        embed.assert_not_called()
        self.assertEqual(list(LegalKnowledgeEmbedding.objects.values_list('pk', flat=True)), [embedding.pk])
        embedding.refresh_from_db()
        self.assertNotEqual(embedding.text, 'Updated community text.')

    def test_student_interactions_and_resource_signal_do_not_index(self):
        self.client.force_authenticate(self.student)
        with patch.object(EmbeddingService, 'embed_text') as embed:
            self.assertEqual(self.client.get(f'/api/articles/articles/{self.article.pk}/').status_code, 200)
            for action in ('like', 'collect'):
                self.assertEqual(self.client.post(f'/api/articles/articles/{self.article.pk}/{action}/').status_code, 200)
            comment = self.client.post('/api/articles/comments/', {
                'article': self.article.pk, 'content': 'A community comment.',
            }, format='json')
            self.assertEqual(comment.status_code, 201, comment.data)
            self.assertEqual(self.client.delete(f'/api/articles/comments/{Comment.objects.get().pk}/').status_code, 204)
            with patch.object(ResourceCache.objects, 'all', wraps=ResourceCache.objects.all) as cache_rows:
                self.assertEqual(self.client.get(f'/api/resources/{self.resource.pk}/').status_code, 200)
                cache_rows.assert_called()
            self.concept.description = 'A trusted ORM change.'
            self.concept.save()
        embed.assert_not_called()
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())
