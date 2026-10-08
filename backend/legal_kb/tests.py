"""Tests for legal knowledge-base ingestion and retrieval."""

import io
import tempfile
import zipfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from audit.models import AuditLedgerEntry
from articles.models import Article, Category as ArticleCategory
from challenges.models import Category as ChallengeCategory, Challenge, ChallengeSolution
from resources.models import Resource

from .models import KbIngestionJob, LegalClause, LegalDocument, LegalKnowledgeEmbedding, LegalRetrievalLog
from .services.chunking_service import ChunkingService
from .services.embedding_service import EmbeddingService
from .services.flk_client import FlkClient
from .services.hashing import sha256_text
from .services.ingestion_service import LegalKbIngestionService
from .services.platform_indexing_service import PlatformContentIndexingService
from .services.rag_answer_service import RagAnswerService
from .services.retrieval_service import LegalRetrievalService


User = get_user_model()


class FailingEmbeddingService:
    """Test embedding service that raises after a clause is created."""

    model = 'failing-test-model'

    def embed_text(self, text):
        raise RuntimeError('embedding provider unavailable')


class FakeProvider:
    """Minimal async chat provider used to test RAG provider routing."""

    def __init__(self, name, content='模型审计结论'):
        self.name = name
        self.content = content

    def is_available(self):
        return True

    async def chat(self, messages):
        from ai_providers import ChatResponse

        return ChatResponse(content=self.content, provider=self.name, model=f'{self.name}-model')


class FakeProviderManager:
    """Provider manager with only DeepSeek available as fallback."""

    def __init__(self):
        self.deepseek = FakeProvider('deepseek')
        self._instances = {'deepseek': self.deepseek}

    def get_provider_for_agent(self, agent_id):
        return None

    def get_provider(self, name):
        return self._instances.get(name)


class LegalKbServiceTests(TestCase):
    """Ingestion should create clauses, embeddings, and audit evidence."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin',
            password='pass12345',
            role='admin',
            is_staff=True,
        )
        full_text = '第一条 为了保护个人信息权益。第二条 处理个人信息应当合法、正当、必要。'
        self.document = LegalDocument.objects.create(
            title='Personal Information Protection Law',
            document_type='law',
            source_name='National Laws and Regulations Database',
            source_url='https://flk.npc.gov.cn/',
            source_hash=sha256_text(full_text),
            full_text=full_text,
            created_by=self.admin,
        )

    def test_ingest_document_creates_clauses_and_embeddings(self):
        job = LegalKbIngestionService().ingest_document(self.document, actor=self.admin)

        self.assertEqual(job.status, 'completed')
        self.assertEqual(LegalClause.objects.filter(document=self.document).count(), 2)
        self.assertEqual(LegalKnowledgeEmbedding.objects.count(), 2)
        embedding = LegalKnowledgeEmbedding.objects.first()
        self.assertEqual(embedding.embedding_model, 'local-hash-v1')
        self.assertEqual(embedding.embedding_dimension, 128)
        self.assertIsNone(embedding.embedding_vector)
        self.assertEqual(AuditLedgerEntry.objects.filter(event_category='kb_ingestion').count(), 1)

    @override_settings(
        EMBEDDING_PROVIDER='dashscope',
        EMBEDDING_API_KEY='test-key',
        EMBEDDING_MODEL='text-embedding-v3',
        EMBEDDING_DIMENSION=1024,
        EMBEDDING_BATCH_SIZE=3,
    )
    def test_dashscope_batch_size_uses_configured_value_with_provider_limit(self):
        service = EmbeddingService()
        calls = []

        def fake_remote_embed_many(texts):
            calls.append(len(texts))
            return [[0.0] * 1024 for _ in texts]

        with patch.object(service, '_remote_embed_many', side_effect=fake_remote_embed_many):
            vectors = service.embed_many([str(index) for index in range(7)])

        self.assertEqual(service.batch_size, 3)
        self.assertEqual(calls, [3, 3, 1])
        self.assertEqual(len(vectors), 7)

    def test_retrieve_returns_matching_chunks_and_logs_query(self):
        LegalKbIngestionService().ingest_document(self.document, actor=self.admin)
        results = LegalRetrievalService().retrieve(
            query='个人信息处理需要什么原则',
            top_k=1,
            user=self.admin,
        )

        self.assertEqual(len(results), 1)
        self.assertIn('个人信息', results[0]['text'])
        self.assertEqual(LegalRetrievalLog.objects.count(), 1)

    @patch('legal_kb.services.rag_answer_service.get_manager', return_value=FakeProviderManager())
    def test_rag_uses_deepseek_when_configured_agent_provider_missing(self, _mock_manager):
        LegalKbIngestionService().ingest_document(self.document, actor=self.admin)

        result = RagAnswerService().answer(
            query='SQL 行为审计',
            top_k=1,
            user=self.admin,
        )

        self.assertEqual(result['provider'], 'deepseek')
        self.assertEqual(result['model'], 'deepseek-model')
        self.assertEqual(result['answer'], '模型审计结论')
        self.assertNotIn('provider_error', result)


    def test_failed_ingestion_persists_failed_job(self):
        with self.assertRaises(RuntimeError):
            LegalKbIngestionService(
                embedding_service=FailingEmbeddingService(),
            ).ingest_document(self.document, actor=self.admin)

        job = KbIngestionJob.objects.get()
        self.assertEqual(job.status, 'failed')
        self.assertIn('embedding provider unavailable', job.error_message)
        self.assertEqual(LegalClause.objects.filter(document=self.document).count(), 0)
        self.assertEqual(LegalKnowledgeEmbedding.objects.count(), 0)

    def test_reingest_document_replaces_old_clause_embeddings(self):
        LegalKbIngestionService().ingest_document(self.document, actor=self.admin)
        LegalKbIngestionService().ingest_document(self.document, actor=self.admin)

        self.assertEqual(LegalClause.objects.filter(document=self.document).count(), 2)
        self.assertEqual(
            LegalKnowledgeEmbedding.objects.filter(
                source_type='legal_clause',
                metadata__document_id=self.document.id,
            ).count(),
            2,
        )

    def test_document_source_hash_is_unique(self):
        with self.assertRaises(IntegrityError):
            LegalDocument.objects.create(
                title='Duplicate source',
                document_type='law',
                source_hash=self.document.source_hash,
                full_text='duplicate text',
                created_by=self.admin,
            )


class PlatformContentIndexingTests(TestCase):
    """Platform content should be indexed into the unified embedding table."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='index-admin',
            password='pass12345',
            role='admin',
            is_staff=True,
        )

    def test_platform_content_indexing_creates_unified_embeddings(self):
        challenge_category, _ = ChallengeCategory.objects.get_or_create(name='Compliance')
        challenge = Challenge.objects.create(
            title='Consent Evidence Lab',
            description='Review whether consent evidence exists.',
            category=challenge_category,
            difficulty='easy',
            score=10,
            flag='flag{consent}',
            is_active=True,
        )
        ChallengeSolution.objects.create(
            challenge=challenge,
            answer_type='step',
            content='Step 1: identify consent records. Step 2: verify audit evidence chain.',
            is_enabled=True,
        )
        article_category = ArticleCategory.objects.create(name='Compliance')
        Article.objects.create(
            title='Privacy review note',
            content='Personal information processing requires consent and audit evidence.',
            summary='Privacy note',
            category=article_category,
            author=self.admin,
            status='approved',
        )
        Resource.objects.create(
            title='Data security checklist',
            description='Checklist for data processing and retention review.',
            resource_type='document',
            category='Compliance',
            status='approved',
            uploader=self.admin,
        )

        results = PlatformContentIndexingService().index_all(actor=self.admin)

        self.assertEqual([item.source_type for item in results], ['challenge', 'challenge', 'article', 'resource'])
        self.assertTrue(LegalKnowledgeEmbedding.objects.filter(source_type='challenge').exists())
        self.assertTrue(LegalKnowledgeEmbedding.objects.filter(
            source_type='challenge',
            text__icontains='audit evidence chain',
        ).exists())
        self.assertTrue(LegalKnowledgeEmbedding.objects.filter(source_type='article').exists())
        self.assertTrue(LegalKnowledgeEmbedding.objects.filter(source_type='resource').exists())
        self.assertEqual(AuditLedgerEntry.objects.filter(event_category='kb_ingestion').count(), 4)

    def test_prepare_command_can_seed_sql_exercises_and_index_platform_content(self):
        call_command('prepare_legal_kb', '--seed-sql-exercises', '--platform-only')

        self.assertGreaterEqual(
            Challenge.objects.filter(title__icontains='SQL', is_active=True).count(),
            3,
        )
        self.assertTrue(
            LegalKnowledgeEmbedding.objects.filter(
                source_type='challenge',
                title__icontains='SQL',
            ).exists()
        )


class OfficialLawFetchTests(TestCase):
    """Official FLK ingestion should avoid network in tests and still vectorize."""

    def test_extract_docx_text_reads_paragraphs(self):
        docx_bytes = self._build_docx([
            '中华人民共和国个人信息保护法',
            '第一条 为了保护个人信息权益，规范个人信息处理活动。',
        ])

        text = FlkClient.extract_docx_text(docx_bytes)

        self.assertIn('中华人民共和国个人信息保护法', text)
        self.assertIn('第一条', text)

    def test_extract_civil_code_privacy_scope_keeps_privacy_chapter(self):
        text = (
            '第四编 人格权\n'
            '第一章 一般规定\n'
            '第六章 隐私权和个人信息保护\n'
            '第五编 婚姻家庭\n'
            '第五章 名誉权和荣誉权\n'
            '第一千零二十四条 民事主体享有名誉权。\n'
            '第六章 隐私权和个人信息保护\n'
            '第一千零三十二条 自然人享有隐私权。\n'
            '第一千零三十四条 自然人的个人信息受法律保护。\n'
            '第七章 婚姻家庭'
        )

        section = FlkClient.extract_civil_code_privacy_scope(text)

        self.assertIn('第六章 隐私权和个人信息保护', section)
        self.assertIn('第一千零三十四条', section)
        self.assertNotIn('第一千零二十四条', section)

    def test_chunking_prefers_line_start_articles_over_inline_references(self):
        text = (
            '中华人民共和国个人信息保护法\n'
            '第一条 为了保护个人信息权益。\n'
            '第二条 自然人的个人信息受法律保护，本法第三条第二款另有规定。\n'
            '第三条 在中华人民共和国境内处理自然人个人信息的活动，适用本法。'
        )

        chunks = ChunkingService.split_legal_text(text)

        self.assertEqual([chunk.article_number for chunk in chunks], ['第一条', '第二条', '第三条'])
        self.assertEqual(len(chunks), 3)

    def test_plain_text_chunking_does_not_split_on_article_references(self):
        text = '解题文档：第一步定位入口。第二步根据本法第三条类比审计证据。'

        chunks = ChunkingService.split_plain_text(text)

        self.assertEqual(len(chunks), 1)
        self.assertIn('解题文档', chunks[0].text)

    @patch('legal_kb.management.commands.fetch_official_laws.FlkClient')
    def test_fetch_official_laws_command_imports_and_vectorizes(self, client_class):
        client = client_class.return_value
        client.fetch_target.return_value = {
            'title': '中华人民共和国个人信息保护法',
            'document_type': 'law',
            'jurisdiction': 'CN',
            'issuing_authority': '全国人民代表大会常务委员会',
            'version_label': '2021-08-20',
            'source_url': 'https://flk.npc.gov.cn/law-search/search/flfgDetails?bbbs=test',
            'source_name': '国家法律法规数据库',
            'full_text': (
                '中华人民共和国个人信息保护法\n'
                '第一条 为了保护个人信息权益，规范个人信息处理活动。\n'
                '第二条 自然人的个人信息受法律保护。'
            ),
            'status': 'active',
            'effective_date': '2021-11-01',
            'published_date': '2021-08-20',
            'metadata': {'bbbs': 'test', 'official_source': '国家法律法规数据库'},
        }

        with tempfile.TemporaryDirectory() as cache_dir:
            call_command('fetch_official_laws', '--query', '个人信息保护法', '--cache-dir', cache_dir)

        self.assertEqual(LegalDocument.objects.count(), 1)
        self.assertEqual(LegalClause.objects.count(), 2)
        self.assertEqual(LegalKnowledgeEmbedding.objects.filter(source_type='legal_clause').count(), 2)

    @staticmethod
    def _build_docx(paragraphs):
        body = ''.join(
            f'<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>'
            for paragraph in paragraphs
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{body}</w:body>'
            '</w:document>'
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('word/document.xml', xml)
        return buffer.getvalue()


class LegalKbApiTests(TestCase):
    """Knowledge-base APIs should enforce role permissions."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin',
            password='pass12345',
            role='admin',
            is_staff=True,
        )
        self.teacher = User.objects.create_user(
            username='teacher',
            password='pass12345',
            role='teacher',
        )
        self.student = User.objects.create_user(
            username='student',
            password='pass12345',
            role='student',
        )
        full_text = '第一条 为了保护个人信息权益。第二条 处理个人信息应当合法、正当、必要。'
        self.document = LegalDocument.objects.create(
            title='Personal Information Protection Law',
            document_type='law',
            source_hash=sha256_text(full_text),
            full_text=full_text,
            created_by=self.admin,
        )
        LegalKbIngestionService().ingest_document(self.document, actor=self.admin)

    def test_student_cannot_browse_documents(self):
        self.client.force_authenticate(self.student)
        response = self.client.get('/api/legal-kb/documents/')

        self.assertEqual(response.status_code, 403)

    def test_teacher_can_retrieve_knowledge(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post('/api/legal-kb/retrieve/', {
            'query': '个人信息处理原则',
            'top_k': 2,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('answer', response.data)
        self.assertIn('sections', response.data)
        self.assertIn('citations', response.data)
        self.assertIn('multi_agent_views', response.data['sections'])
        self.assertGreaterEqual(len(response.data['citations']), 1)
        self.assertNotIn('results', response.data)

    def test_teacher_cannot_request_raw_retrieval_results(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post('/api/legal-kb/retrieve/', {
            'query': '个人信息处理原则',
            'top_k': 2,
            'include_raw': True,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('answer', response.data)
        self.assertIn('citations', response.data)
        self.assertNotIn('results', response.data)

    def test_admin_can_request_raw_retrieval_results_for_debugging(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/legal-kb/retrieve/', {
            'query': '个人信息处理原则',
            'top_k': 2,
            'include_raw': True,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('answer', response.data)
        self.assertIn('citations', response.data)
        self.assertGreaterEqual(len(response.data['results']), 1)

    def test_admin_can_ingest_document(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/legal-kb/documents/{self.document.id}/ingest/')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'completed')

    def test_admin_cannot_create_duplicate_document_source(self):
        self.client.force_authenticate(self.admin)
        payload = {
            'title': 'API-created legal document',
            'document_type': 'law',
            'source_url': 'https://example.test/legal',
            'full_text': 'Article 1. API-created legal document text.',
        }
        first_response = self.client.post('/api/legal-kb/documents/', payload, format='json')
        self.assertEqual(first_response.status_code, 201)

        response = self.client.post('/api/legal-kb/documents/', payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('source_hash', response.data)

    def test_patch_recomputes_document_source_hash(self):
        self.client.force_authenticate(self.admin)
        old_hash = self.document.source_hash

        response = self.client.patch(f'/api/legal-kb/documents/{self.document.id}/', {
            'title': 'Updated Personal Information Protection Law',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        expected_hash = sha256_text(
            f'{self.document.title}|{self.document.source_url}|{self.document.full_text}'
        )
        self.assertNotEqual(self.document.source_hash, old_hash)
        self.assertEqual(self.document.source_hash, expected_hash)
