"""Tests for the rag_ingestion document pipeline."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from legal_kb.models import LegalKnowledgeEmbedding

from .interfaces import Chunk, EmbeddedChunk
from .models import DocumentSource
from .pipeline import EmptyDocumentError, IngestionPipeline, UnsupportedFormatError
from .registry import select_parser
from .services import IngestionService

User = get_user_model()

MARKDOWN = (
    '# SQL 注入防御\n\n'
    'SQL 注入通过拼接恶意 SQL 语句读取数据库数据。\n\n'
    '## 防御手段\n\n'
    '使用参数化查询（预编译语句）并对输入做白名单校验，可以有效防御 SQL 注入。\n'
).encode('utf-8')


class RegistryTests(TestCase):
    def test_plain_parser_selected_for_markdown(self):
        parser = select_parser('note.md', 'text/markdown')
        self.assertIsNotNone(parser)
        self.assertEqual(parser.name, 'plain')

    def test_html_is_stripped_to_text(self):
        parser = select_parser('page.html', 'text/html')
        parsed = parser.parse(b'<html><body><h1>Hi</h1><script>bad()</script><p>Body</p></body></html>',
                              filename='page.html', mime='text/html')
        self.assertIn('Hi', parsed.text)
        self.assertIn('Body', parsed.text)
        self.assertNotIn('bad()', parsed.text)


class IngestionServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='kb-admin', password='pass12345', is_staff=True)

    def test_markdown_ingestion_writes_document_embeddings(self):
        document = IngestionService().ingest_bytes(
            data=MARKDOWN,
            filename='sql-defense.md',
            mime='text/markdown',
            uploaded_by=self.user,
        )

        self.assertEqual(document.status, 'completed')
        self.assertGreaterEqual(document.embedded_count, 1)
        content_type = ContentType.objects.get_for_model(DocumentSource)
        chunks = LegalKnowledgeEmbedding.objects.filter(
            source_type='document',
            content_type=content_type,
            object_id=document.id,
        )
        self.assertEqual(chunks.count(), document.embedded_count)
        self.assertTrue(chunks.filter(text__icontains='参数化查询').exists())
        self.assertEqual(chunks.first().metadata.get('visibility'), 'internal')

    def test_ingestion_is_idempotent_for_identical_content(self):
        service = IngestionService()
        first = service.ingest_bytes(data=MARKDOWN, filename='a.md', uploaded_by=self.user)
        second = service.ingest_bytes(data=MARKDOWN, filename='a.md', uploaded_by=self.user)

        self.assertEqual(first.id, second.id)
        content_type = ContentType.objects.get_for_model(DocumentSource)
        self.assertEqual(
            LegalKnowledgeEmbedding.objects.filter(
                source_type='document', content_type=content_type, object_id=first.id
            ).count(),
            first.embedded_count,
        )

    def test_empty_document_is_marked_failed(self):
        document = IngestionService().ingest_bytes(
            data=b'   \n  ', filename='empty.txt', uploaded_by=self.user,
        )
        self.assertEqual(document.status, 'failed')
        self.assertIn('EmptyDocumentError', document.error_message)

    def test_uploaded_documents_are_not_learner_facing_by_default(self):
        """'document' is outside the teaching-safe allowlist, so KnowledgeAgent
        and agent_runtime must not surface uploaded files to learners."""
        from legal_kb.services.knowledge_retrieval_service import SafeKnowledgeRetrievalService

        IngestionService().ingest_bytes(data=MARKDOWN, filename='sql.md', uploaded_by=self.user)
        items = SafeKnowledgeRetrievalService().retrieve(query='参数化查询 防御 SQL 注入', top_k=10)

        self.assertNotIn('document', {item['source_type'] for item in items})


class PipelineUnitTests(TestCase):
    def test_unsupported_format_raises(self):
        pipeline = IngestionPipeline(parser_selector=lambda filename, mime: None)
        with self.assertRaises(UnsupportedFormatError):
            pipeline.run(data=b'x', filename='mystery.xyz', document_id=1)

    def test_empty_text_raises(self):
        document = DocumentSource.objects.create(
            title='t', filename='t.txt', source_hash='hash-empty', status='running',
        )
        with self.assertRaises(EmptyDocumentError):
            IngestionPipeline().run(data=b'   ', filename='t.txt', document_id=document.id)


class RepositoryAtomicityTests(TestCase):
    """replace() must swap the index atomically: a mid-write failure keeps the old one."""

    def _embedded(self, order, text):
        chunk = Chunk(text=text, order=order, title='new', metadata={})
        return EmbeddedChunk(
            chunk=chunk, vector=[0.0] * 8, local_vector=[0.0] * 8,
            model='local-hash-v1', dimension=8,
        )

    def test_failed_rebuild_rolls_back_and_keeps_old_index(self):
        from .adapters.repository_legalkb import LegalKbChunkRepository

        doc = DocumentSource.objects.create(
            title='t', filename='t.md', source_hash='atomic-1', status='completed',
        )
        content_type = ContentType.objects.get_for_model(DocumentSource)
        LegalKnowledgeEmbedding.objects.create(
            source_type='document', content_type=content_type, object_id=doc.id,
            chunk_index=0, title='old', text='OLD_COMPLETE_INDEX', text_hash='oldhash',
            embedding=[0.0], embedding_model='local-hash-v1', embedding_dimension=1, metadata={},
        )

        embedded = [self._embedded(1, 'NEW_1'), self._embedded(2, 'NEW_2')]
        real_create = LegalKnowledgeEmbedding.objects.create
        state = {'n': 0}

        def failing_create(**kwargs):
            state['n'] += 1
            if state['n'] == 2:
                raise RuntimeError('simulated disk failure on 2nd chunk')
            return real_create(**kwargs)

        with patch.object(LegalKnowledgeEmbedding.objects, 'create', side_effect=failing_create):
            with self.assertRaises(RuntimeError):
                LegalKbChunkRepository().replace(
                    document_id=doc.id, source_type='document',
                    embedded=embedded, base_metadata={'title': 't'},
                )

        remaining = list(
            LegalKnowledgeEmbedding.objects
            .filter(content_type=content_type, object_id=doc.id)
            .values_list('text', flat=True)
        )
        self.assertEqual(remaining, ['OLD_COMPLETE_INDEX'])  # no partial NEW_1 left behind


class MarkItDownParserTests(TestCase):
    """markitdown adapter must close the temp file before convert reopens it."""

    def test_tempfile_closed_before_convert_and_cleaned_up(self):
        import os
        import sys
        import types

        from .adapters.parser_markitdown import MarkItDownParser

        captured = {}

        class FakeResult:
            def __init__(self, text):
                self.text_content = text

        class FakeMarkItDown:
            def convert(self, path):
                captured['path'] = path
                # Reopen by path — would raise PermissionError on Windows if the
                # writer handle were still open. Succeeds because parse() closes it.
                with open(path, 'rb') as handle:
                    data = handle.read()
                return FakeResult('converted:' + data.decode('utf-8', 'ignore'))

        fake_module = types.ModuleType('markitdown')
        fake_module.MarkItDown = FakeMarkItDown

        parser = MarkItDownParser()
        parser._available = True  # pretend the optional dependency is installed

        with patch.dict(sys.modules, {'markitdown': fake_module}):
            parsed = parser.parse(b'hello pptx', filename='deck.pptx', mime='')

        self.assertIn('converted:hello pptx', parsed.text)
        self.assertFalse(os.path.exists(captured['path']))  # temp file cleaned up
