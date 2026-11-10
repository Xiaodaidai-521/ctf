"""Tests for legal knowledge-base ingestion and retrieval."""

import io
import tempfile
import zipfile
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from audit.models import AuditLedgerEntry
from articles.models import Article, Category as ArticleCategory
from challenges.models import Category as ChallengeCategory, Challenge, ChallengeSolution
from learning_paths.models import KnowledgeConcept
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

    def test_retrieve_hybrid_fusion_exposes_rrf_scores_and_order(self):
        LegalKbIngestionService().ingest_document(self.document, actor=self.admin)
        results = LegalRetrievalService().retrieve(
            query='个人信息处理原则 合法 正当 必要',
            top_k=5,
            user=self.admin,
        )

        self.assertTrue(results)
        for item in results:
            self.assertIn('score', item)
            self.assertIn('rrf_score', item)
        rrf_scores = [item['rrf_score'] for item in results]
        self.assertEqual(rrf_scores, sorted(rrf_scores, reverse=True))

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
        KnowledgeConcept.objects.create(
            name='SQL注入',
            slug='sql-injection',
            description='SQL 注入是指将恶意 SQL 语句注入到应用查询中的漏洞。',
            concept_type='vul',
            difficulty_level=2,
            importance=0.9,
            cwe_id='CWE-89',
        )

        results = PlatformContentIndexingService().index_all(actor=self.admin)

        self.assertEqual(
            [item.source_type for item in results],
            ['challenge', 'challenge', 'article', 'resource', 'knowledge_concept'],
        )
        self.assertTrue(LegalKnowledgeEmbedding.objects.filter(source_type='challenge').exists())
        self.assertTrue(LegalKnowledgeEmbedding.objects.filter(
            source_type='challenge',
            text__icontains='audit evidence chain',
        ).exists())
        self.assertTrue(LegalKnowledgeEmbedding.objects.filter(source_type='article').exists())
        self.assertTrue(LegalKnowledgeEmbedding.objects.filter(source_type='resource').exists())
        concept_embedding = LegalKnowledgeEmbedding.objects.filter(
            source_type='knowledge_concept',
            text__icontains='SQL 注入',
        ).first()
        self.assertIsNotNone(concept_embedding)
        self.assertEqual(concept_embedding.metadata.get('cwe_id'), 'CWE-89')
        self.assertEqual(AuditLedgerEntry.objects.filter(event_category='kb_ingestion').count(), 5)

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


class DocumentVisibilityTests(TestCase):
    """Staff-only uploaded documents must not leak to teachers via any read path."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='vis-admin', password='pass12345', role='admin', is_staff=True,
        )
        self.teacher = User.objects.create_user(
            username='vis-teacher', password='pass12345', role='teacher',
        )
        from rag_ingestion.models import DocumentSource

        self.doc = DocumentSource.objects.create(
            title='内部红队手册', filename='redteam.md', source_hash='vis-hash-1',
            status='completed', visibility='staff',
        )
        content_type = ContentType.objects.get_for_model(DocumentSource)
        vector = EmbeddingService().embed_local_text('红队 内部 手册 高危 操作 仅限 员工')
        self.secret = '红队内部手册 高危操作 仅限员工 机密内容'
        LegalKnowledgeEmbedding.objects.create(
            source_type='document', content_type=content_type, object_id=self.doc.id,
            chunk_index=0, title='内部红队手册', text=self.secret,
            text_hash=sha256_text(self.secret), embedding=vector,
            embedding_model='local-hash-v1', embedding_dimension=len(vector),
            metadata={'visibility': 'staff', 'source_type': 'document'},
        )

    def _texts(self, response):
        data = response.data
        rows = data.get('results', data) if isinstance(data, dict) else data
        return ' '.join(row.get('text', '') for row in rows)

    def test_embeddings_api_hides_staff_doc_from_teacher_but_not_admin(self):
        self.client.force_authenticate(self.teacher)
        teacher_resp = self.client.get('/api/legal-kb/embeddings/')
        self.assertEqual(teacher_resp.status_code, 200)
        self.assertNotIn('机密内容', self._texts(teacher_resp))

        self.client.force_authenticate(self.admin)
        admin_resp = self.client.get('/api/legal-kb/embeddings/')
        self.assertEqual(admin_resp.status_code, 200)
        self.assertIn('机密内容', self._texts(admin_resp))

    def test_retrieve_hides_staff_doc_from_teacher_but_not_admin(self):
        query = '红队内部手册 高危操作'
        teacher_results = LegalRetrievalService().retrieve(query=query, top_k=10, user=self.teacher)
        self.assertFalse(any(item['source_type'] == 'document' for item in teacher_results))

        admin_results = LegalRetrievalService().retrieve(query=query, top_k=10, user=self.admin)
        self.assertTrue(any(item['source_type'] == 'document' for item in admin_results))

    def _make_document(self, *, doc_visibility, snapshot_visibility, text, hash_id):
        from rag_ingestion.models import DocumentSource

        doc = DocumentSource.objects.create(
            title=text[:50], filename=f'{hash_id}.md', source_hash=hash_id,
            status='completed', visibility=doc_visibility,
        )
        content_type = ContentType.objects.get_for_model(DocumentSource)
        vector = EmbeddingService().embed_local_text(text)
        LegalKnowledgeEmbedding.objects.create(
            source_type='document', content_type=content_type, object_id=doc.id,
            chunk_index=0, title=text[:50], text=text, text_hash=sha256_text(text),
            embedding=vector, embedding_model='local-hash-v1', embedding_dimension=len(vector),
            metadata={'visibility': snapshot_visibility, 'source_type': 'document'},
        )
        return doc

    def test_tightening_visibility_after_ingest_blocks_teacher(self):
        """Changing DocumentSource.visibility must take effect immediately, even
        though the chunk's metadata snapshot still says 'internal'."""
        doc = self._make_document(
            doc_visibility='internal', snapshot_visibility='internal',
            text='蓝队 内部 培训 资料 可见 性 测试 内容A', hash_id='vis-tighten-1',
        )
        query = '蓝队内部培训资料 可见性 内容A'

        # Teacher can read while it is internal.
        before = LegalRetrievalService().retrieve(query=query, top_k=10, user=self.teacher)
        self.assertTrue(any(item['object_id'] == doc.id for item in before))

        # Tighten to staff-only via the live model (snapshot left stale on purpose).
        doc.visibility = 'staff'
        doc.save(update_fields=['visibility'])

        after = LegalRetrievalService().retrieve(query=query, top_k=10, user=self.teacher)
        self.assertFalse(any(item['object_id'] == doc.id for item in after))

        self.client.force_authenticate(self.teacher)
        resp = self.client.get('/api/legal-kb/embeddings/')
        self.assertNotIn('内容A', self._texts(resp))

    def test_stale_internal_snapshot_does_not_grant_access_to_staff_doc(self):
        """Reviewer repro #2: old index kept after a failed re-ingest. The chunk
        snapshot says 'internal' but the live DocumentSource is 'staff'."""
        doc = self._make_document(
            doc_visibility='staff', snapshot_visibility='internal',
            text='渗透 测试 旧 索引 快照 过期 内容B', hash_id='vis-stale-1',
        )
        query = '渗透测试 旧索引 快照 内容B'

        teacher_results = LegalRetrievalService().retrieve(query=query, top_k=10, user=self.teacher)
        self.assertFalse(any(item['object_id'] == doc.id for item in teacher_results))

        admin_results = LegalRetrievalService().retrieve(query=query, top_k=10, user=self.admin)
        self.assertTrue(any(item['object_id'] == doc.id for item in admin_results))


@skipUnless(connection.vendor == 'postgresql', 'pgvector ANN path requires PostgreSQL')
class PgvectorAnnRetrievalTests(TestCase):
    """Exercise the real pgvector ANN branch (_retrieve_with_pgvector) + visibility."""

    def _vec(self, index):
        vector = [0.0] * 1024
        vector[index] = 1.0
        return vector

    def setUp(self):
        from rag_ingestion.models import DocumentSource

        self.admin = User.objects.create_user(
            username='pg-admin', password='pass12345', role='admin', is_staff=True,
        )
        self.teacher = User.objects.create_user(
            username='pg-teacher', password='pass12345', role='teacher',
        )
        content_type = ContentType.objects.get_for_model(DocumentSource)
        self.doc_internal = DocumentSource.objects.create(
            title='A', filename='a.md', source_hash='pg-a', status='completed', visibility='internal',
        )
        self.doc_staff = DocumentSource.objects.create(
            title='B', filename='b.md', source_hash='pg-b', status='completed', visibility='staff',
        )
        for doc, idx, vis in [(self.doc_internal, 0, 'internal'), (self.doc_staff, 1, 'staff')]:
            LegalKnowledgeEmbedding.objects.create(
                source_type='document', content_type=content_type, object_id=doc.id,
                chunk_index=0, title=doc.title, text=f'doc {doc.title} body',
                text_hash=f'pgh-{doc.id}', embedding=[0.0] * 4, embedding_vector=self._vec(idx),
                embedding_model='fake-1024', embedding_dimension=1024,
                metadata={'visibility': vis, 'source_type': 'document'},
            )

    def _service(self, query_index):
        from legal_kb.services.retrieval_service import LegalRetrievalService

        vec = self._vec

        class Fake1024Embeddings:
            model = 'fake-1024'

            def embed_text(self, text):
                return vec(query_index)

            def embed_local_text(self, text):
                return [0.0] * 4

        return LegalRetrievalService(embedding_service=Fake1024Embeddings())

    def test_ann_returns_nearest_for_admin(self):
        results = self._service(1).retrieve(query='q', top_k=5, user=self.admin)
        self.assertTrue(results)
        self.assertEqual(results[0]['object_id'], self.doc_staff.id)  # nearest via pgvector ANN

    def test_ann_respects_visibility_for_teacher(self):
        results = self._service(1).retrieve(query='q', top_k=5, user=self.teacher)
        # staff doc is the nearest vector, but must be filtered out for a teacher
        self.assertFalse(any(item['object_id'] == self.doc_staff.id for item in results))
