from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from agents.specialists.resource_agent import ResourceAgent
from articles.models import Article, Category as ArticleCategory
from resources.models import Resource, ResourceCache
from resources.serializers import ResourceSerializer, ResourceUploadSerializer
from resources.views import resource_download_view


User = get_user_model()


class ResourceAgentCacheTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='student',
            password='pass12345',
            role='student',
        )
        self.teacher = User.objects.create_user(
            username='teacher',
            password='pass12345',
            role='teacher',
        )
        self.article_category = ArticleCategory.objects.create(name='Web Security')
        self.article = Article.objects.create(
            title='SQL injection basic intro course',
            content='Parameterized queries keep user input as data.',
            summary='SQL injection foundations and beginner examples.',
            author=self.teacher,
            category=self.article_category,
            status='approved',
            tags='sql,basic,intro',
        )

    def test_second_same_student_knowledge_point_uses_cache_without_rag(self):
        agent = ResourceAgent()
        rag_result = [{
            'source_type': 'article',
            'object_id': self.article.id,
            'title': self.article.title,
            'text': self.article.summary,
            'score': 0.87,
            'metadata': {},
        }]

        with patch('legal_kb.services.retrieval_service.LegalRetrievalService.retrieve', return_value=rag_result) as retrieve:
            first = agent.prepare(
                query='How should I study SQL injection?',
                student_id=self.student.id,
                student_level='beginner',
            )

        self.assertFalse(first['cacheHit'])
        self.assertEqual(first['knowledgePoint'], 'SQL\u6ce8\u5165')
        self.assertTrue(first['resourceList'])
        self.assertEqual(retrieve.call_count, 1)

        with patch('legal_kb.services.retrieval_service.LegalRetrievalService.retrieve', side_effect=AssertionError('RAG should not be called')):
            second = agent.prepare(
                query='Please explain SQL injection again.',
                student_id=self.student.id,
                student_level='beginner',
                knowledge_point='SQL\u6ce8\u5165',
            )

        self.assertTrue(second['cacheHit'])
        self.assertEqual(second['resourceList'][0]['title'], self.article.title)
        cache = ResourceCache.objects.get(studentId=self.student.id, knowledgePoint='SQL\u6ce8\u5165')
        self.assertEqual(cache.cacheHitCount, 1)

    def test_no_matched_resource_is_cached_as_empty_without_fabrication(self):
        agent = ResourceAgent()

        with patch('legal_kb.services.retrieval_service.LegalRetrievalService.retrieve', return_value=[]):
            first = agent.prepare(
                query='zz-unmatched-topic',
                student_id=self.student.id,
                student_level='beginner',
                knowledge_point='zz-unmatched-topic',
            )

        self.assertFalse(first['cacheHit'])
        self.assertTrue(first['noMatchedResource'])
        self.assertEqual(first['resourceList'], [])

        with patch('legal_kb.services.retrieval_service.LegalRetrievalService.retrieve', side_effect=AssertionError('RAG should not be called')):
            second = agent.prepare(
                query='zz-unmatched-topic again',
                student_id=self.student.id,
                student_level='beginner',
                knowledge_point='zz-unmatched-topic',
            )

        self.assertTrue(second['cacheHit'])
        self.assertTrue(second['noMatchedResource'])
        self.assertEqual(second['resourceList'], [])

    @override_settings(TUTOR_RESOURCE_CACHE_ENABLED=False)
    def test_resource_cache_switch_bypasses_cache_read_and_write(self):
        ResourceCache.objects.create(
            studentId=self.student.id,
            knowledgePoint='SQL\u6ce8\u5165',
            resourceList=[{'id': 'stale', 'title': 'Stale cached resource', 'type': 'article'}],
            studentLevel='beginner',
        )
        rag_result = [{
            'source_type': 'article',
            'object_id': self.article.id,
            'title': self.article.title,
            'text': self.article.summary,
            'score': 0.87,
            'metadata': {},
        }]

        with patch('legal_kb.services.retrieval_service.LegalRetrievalService.retrieve', return_value=rag_result) as retrieve:
            result = ResourceAgent().prepare(
                query='How should I study SQL injection?',
                student_id=self.student.id,
                student_level='beginner',
                knowledge_point='SQL\u6ce8\u5165',
            )

        self.assertFalse(result['cacheHit'])
        self.assertEqual(retrieve.call_count, 1)
        self.assertNotIn('Stale cached resource', {item['title'] for item in result['resourceList']})
        cache = ResourceCache.objects.get(studentId=self.student.id, knowledgePoint='SQL\u6ce8\u5165')
        self.assertEqual(cache.cacheHitCount, 0)

    def test_student_level_changes_resource_ordering(self):
        context = {
            'items': [
                {
                    'id': 'basic',
                    'title': 'SQL injection basic intro course',
                    'type': 'article',
                    'entry': '/articles/basic',
                    'summary': 'foundation example and prerequisite explanation',
                    'score': 0.5,
                },
                {
                    'id': 'advanced',
                    'title': 'SQL injection advanced challenge practice',
                    'type': 'challenge',
                    'entry': '/challenges/advanced',
                    'summary': 'hard lab and bypass practice',
                    'difficulty': 'hard',
                    'score': 0.5,
                },
            ]
        }
        agent = ResourceAgent()

        beginner = agent.prepare(
            query='sorting-only',
            student_level='beginner',
            existing_rag_context=context,
        )
        excellent = agent.prepare(
            query='sorting-only',
            student_level='excellent',
            existing_rag_context=context,
        )

        self.assertEqual(beginner['resourceList'][0]['id'], 'basic')
        self.assertEqual(excellent['resourceList'][0]['id'], 'advanced')


class ResourceVisibilityTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='teacher2',
            password='pass12345',
            role='teacher',
        )
        self.client = APIClient()

    def _resource(self, title, *, reserved=False, tags='visible', resource_type='document'):
        return Resource.objects.create(
            title=title,
            description=f'{title} description',
            resource_type=resource_type,
            file=SimpleUploadedFile(f'{title}.txt', b'demo'),
            category='Web',
            tags=tags,
            status='approved',
            uploader=self.teacher,
            is_tutoring_reserved=reserved,
        )

    def test_reserved_resources_are_hidden_from_public_resource_center_but_available_to_resource_agent(self):
        visible = self._resource('Visible resource', tags='ordinary')
        reserved = self._resource('Reserved tutoring resource', reserved=True, tags='reserved-only-resource')

        response = self.client.get('/api/resources/')

        self.assertEqual(response.status_code, 200)
        payload = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        titles = {item['title'] for item in payload}
        self.assertIn(visible.title, titles)
        self.assertNotIn(reserved.title, titles)

        with patch('legal_kb.services.retrieval_service.LegalRetrievalService.retrieve', return_value=[]):
            prepared = ResourceAgent().prepare(
                query='reserved-only-resource',
                student_level='beginner',
                knowledge_point='reserved-only-resource',
            )

        prepared_titles = {item['title'] for item in prepared['resourceList']}
        self.assertIn(reserved.title, prepared_titles)

    def test_highlight_resource_temporarily_exposes_approved_reserved_resource_first(self):
        visible = self._resource('Visible list resource', tags='ordinary-visible')
        reserved = self._resource('Reserved highlighted resource', reserved=True, tags='highlight-only')

        response = self.client.get(f'/api/resources/?highlight_resource={reserved.id}')

        self.assertEqual(response.status_code, 200)
        payload = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertGreaterEqual(len(payload), 2)
        self.assertEqual(payload[0]['id'], reserved.id)
        self.assertEqual(payload[0]['title'], reserved.title)
        self.assertTrue(payload[0]['is_ai_highlighted'])
        self.assertEqual(payload[0]['ai_generated_label'], 'AI多模态生成')
        self.assertIn(visible.title, {item['title'] for item in payload})

    def test_highlight_resources_temporarily_exposes_multiple_reserved_resources_first(self):
        visible = self._resource('Visible multi list resource', tags='ordinary-multi-visible')
        first = self._resource('First reserved highlighted resource', reserved=True, tags='highlight-multi-first')
        second = self._resource('Second reserved highlighted resource', reserved=True, tags='highlight-multi-second')

        response = self.client.get(f'/api/resources/?highlight_resources={first.id},{second.id}')

        self.assertEqual(response.status_code, 200)
        payload = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertGreaterEqual(len(payload), 3)
        self.assertEqual([payload[0]['id'], payload[1]['id']], [first.id, second.id])
        self.assertTrue(payload[0]['is_ai_highlighted'])
        self.assertTrue(payload[1]['is_ai_highlighted'])
        self.assertIn(visible.title, {item['title'] for item in payload})
    def test_reserved_resource_detail_requires_matching_highlight(self):
        reserved = self._resource('Reserved detail resource', reserved=True, tags='detail-highlight-only')

        direct = self.client.get(f'/api/resources/{reserved.id}/')
        highlighted = self.client.get(f'/api/resources/{reserved.id}/?highlight_resource={reserved.id}')

        self.assertEqual(direct.status_code, 404)
        self.assertEqual(highlighted.status_code, 200)
        self.assertEqual(highlighted.data['id'], reserved.id)
        self.assertTrue(highlighted.data['is_ai_highlighted'])
        self.assertEqual(highlighted.data['ai_generated_label'], 'AI多模态生成')

    def test_resource_agent_resource_entry_targets_highlight_and_preserves_ai_resource_type(self):
        ai_resource = self._resource(
            'Reserved AI generated resource',
            reserved=True,
            tags='agent-highlight-ai-resource',
            resource_type='ai_resource',
        )

        with patch('legal_kb.services.retrieval_service.LegalRetrievalService.retrieve', return_value=[]):
            prepared = ResourceAgent().prepare(
                query='agent-highlight-ai-resource',
                student_level='beginner',
                knowledge_point='agent-highlight-ai-resource',
            )

        self.assertTrue(prepared['resourceList'])
        item = prepared['resourceList'][0]
        self.assertEqual(item['id'], str(ai_resource.id))
        self.assertEqual(item['type'], 'ai_resource')
        self.assertEqual(item['entry'], f'/resources?highlight_resource={ai_resource.id}&resource={ai_resource.id}')
        self.assertEqual(item['ai_generated_label'], 'AI多模态生成')


class AIResourceTypeTests(TestCase):
    def test_ai_resource_type_serializes_display_label(self):
        teacher = User.objects.create_user(
            username='ai-resource-teacher',
            password='pass12345',
            role='teacher',
        )
        resource = Resource.objects.create(
            title='AI resource guide',
            description='AI generated learning material',
            resource_type='ai_resource',
            file=SimpleUploadedFile('ai-guide.md', b'# AI guide', content_type='text/markdown'),
            category='AI学习',
            tags='AI资源',
            status='approved',
            uploader=teacher,
            file_size=10,
        )

        self.assertEqual(ResourceSerializer(resource).data['resource_type_display'], 'AI资源')


def png_upload(name='image.png', content_type='image/png'):
    image_data = BytesIO()
    Image.new('RGB', (1, 1), color='white').save(image_data, format='PNG')
    return SimpleUploadedFile(name, image_data.getvalue(), content_type=content_type)


class ResourceUploadValidationTests(TestCase):
    def serializer_for(self, upload, cover_image=None, resource_type='document'):
        data = {
            'title': 'Validated resource',
            'description': 'Validation test resource',
            'resource_type': resource_type,
            'category': 'security',
            'file': upload,
        }
        if cover_image:
            data['cover_image'] = cover_image
        return ResourceUploadSerializer(data=data)

    def test_accepts_utf8_text_with_matching_content_type(self):
        serializer = self.serializer_for(
            SimpleUploadedFile('notes.txt', b'safe text', content_type='text/plain')
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_accepts_mp4_video_with_matching_content_type(self):
        serializer = self.serializer_for(
            SimpleUploadedFile('lesson.mp4', b'\x00\x00\x00\x18ftypmp42', content_type='video/mp4'),
            resource_type='video',
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_disallowed_extension(self):
        serializer = self.serializer_for(
            SimpleUploadedFile('payload.html', b'<html></html>', content_type='text/html')
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)

    def test_rejects_mismatched_content_type(self):
        serializer = self.serializer_for(
            SimpleUploadedFile('notes.txt', b'safe text', content_type='text/html')
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)

    @override_settings(RESOURCE_MAX_UPLOAD_SIZE=4)
    def test_rejects_file_larger_than_configured_limit(self):
        serializer = self.serializer_for(
            SimpleUploadedFile('notes.txt', b'12345', content_type='text/plain')
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)

    def test_rejects_script_content_in_text_upload(self):
        serializer = self.serializer_for(
            SimpleUploadedFile('notes.md', b'<script>alert(1)</script>', content_type='text/markdown')
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)

    def test_rejects_invalid_zip_content(self):
        serializer = self.serializer_for(
            SimpleUploadedFile('archive.zip', b'PKnot-a-zip', content_type='application/zip')
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)

    @override_settings(RESOURCE_MAX_ARCHIVE_UNCOMPRESSED_SIZE=4)
    def test_rejects_zip_that_expands_beyond_limit(self):
        archive = BytesIO()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('notes.txt', b'12345')
        serializer = self.serializer_for(
            SimpleUploadedFile('archive.zip', archive.getvalue(), content_type='application/zip')
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)

    def test_rejects_invalid_cover_image(self):
        serializer = self.serializer_for(
            SimpleUploadedFile('notes.txt', b'safe text', content_type='text/plain'),
            SimpleUploadedFile('cover.png', b'not an image', content_type='image/png'),
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('cover_image', serializer.errors)

    def test_accepts_verified_cover_image(self):
        serializer = self.serializer_for(
            SimpleUploadedFile('notes.txt', b'safe text', content_type='text/plain'),
            png_upload(),
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)


class ResourceDownloadAccessTests(TestCase):
    def setUp(self):
        self.media_root = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.settings_override.enable()
        self.user = User.objects.create_user(username='resource-reader', password='pass12345')
        self.resource = Resource.objects.create(
            title='Approved resource',
            description='Download access test',
            resource_type='document',
            category='security',
            status='approved',
            uploader=self.user,
            file=SimpleUploadedFile('notes.txt', b'safe text', content_type='text/plain'),
            file_size=9,
        )
        self.factory = APIRequestFactory()

    def tearDown(self):
        self.settings_override.disable()
        self.media_root.cleanup()

    def test_download_requires_authentication(self):
        request = self.factory.get(f'/api/resources/{self.resource.id}/download/')
        response = resource_download_view(request, self.resource.id)

        self.assertEqual(response.status_code, 403)

    def test_download_is_attachment_with_nosniff(self):
        request = self.factory.get(f'/api/resources/{self.resource.id}/download/')
        force_authenticate(request, user=self.user)

        response = resource_download_view(request, self.resource.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.download_count, 1)
        for closer in getattr(response, '_resource_closers', []):
            closer()
        response._resource_closers.clear()

    def test_reserved_download_requires_matching_highlight(self):
        reserved = Resource.objects.create(
            title='Reserved downloadable resource',
            description='Hidden download access test',
            resource_type='document',
            category='security',
            status='approved',
            uploader=self.user,
            file=SimpleUploadedFile('reserved.txt', b'private', content_type='text/plain'),
            file_size=7,
            is_tutoring_reserved=True,
        )

        direct_request = self.factory.get(f'/api/resources/{reserved.id}/download/')
        force_authenticate(direct_request, user=self.user)
        direct_response = resource_download_view(direct_request, reserved.id)

        highlighted_request = self.factory.get(
            f'/api/resources/{reserved.id}/download/?highlight_resource={reserved.id}'
        )
        force_authenticate(highlighted_request, user=self.user)
        highlighted_response = resource_download_view(highlighted_request, reserved.id)

        self.assertEqual(direct_response.status_code, 404)
        self.assertEqual(highlighted_response.status_code, 200)
        for closer in getattr(highlighted_response, '_resource_closers', []):
            closer()
        highlighted_response._resource_closers.clear()

