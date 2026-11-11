"""Corpus import preserves provenance, legal identity and access boundaries."""
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from legal_kb.models import LegalClause, LegalDocument, LegalKnowledgeEmbedding
from legal_kb.services.corpus_import import digest, import_corpus, validate_corpus
from legal_kb.services.embedding_service import EmbeddingService
from legal_kb.services.retrieval_service import LegalRetrievalService
from rag_ingestion.models import DocumentSource
from rag_ingestion.services import IngestionService


def fixture(root):
    text = '# Authentication\n\nUse strong passwords and limit failed login attempts.\n'
    law_text = '# 测试法律\n\n第一条\u3000保护个人信息。\n\n第二条\u3000最小必要原则。\n'
    shared = {'license_sha256': digest(b'license'), 'source_url': 'https://example.com/',
              'review_status': 'pending', 'published': False, 'source_version': 'snapshot'}
    document = {**shared, 'id': 'owasp-test', 'source_id': 'owasp-test', 'title': 'Authentication',
                'markdown_path': 'markdown/auth.md', 'source_snapshot': text,
                'source_hash': digest(text.encode('utf-8'))}
    law = {**shared, 'id': 'cn-test', 'source_id': 'cn-official-laws', 'title': '测试法律',
           'original_title': '测试法律', 'document_type': 'law', 'scope': 'full_text',
           'publisher': '测试机关', 'source_name': '官方测试数据', 'version_label': '2025-10-28',
           'effective_date': '2026-01-01', 'published_date': '2025-10-28',
           'markdown_path': 'markdown/law.md', 'source_snapshot': law_text,
           'source_hash': digest(law_text.encode('utf-8')), 'article_range': [1, 2], 'article_count': 2}
    clauses = [{'document_id': 'cn-test', 'article_number': number, 'article_label': label,
                'chapter': '第一章', 'text': content, 'text_hash': digest(content.encode('utf-8'))}
               for number, label, content in [(1, '第一条', '第一条\u3000保护个人信息。'),
                                              (2, '第二条', '第二条\u3000最小必要原则。')]]
    for name, record in [('owasp', document), ('chinese_laws', law)]:
        bundle = root / name
        (bundle / 'markdown').mkdir(parents=True)
        (bundle / 'licenses').mkdir()
        license_name = record['source_id'] if name == 'owasp' else 'cn-official-laws'
        (bundle / 'licenses' / (license_name + '.txt')).write_bytes(b'license')
        (bundle / record['markdown_path']).write_bytes(record['source_snapshot'].encode('utf-8'))
        content = (json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8')
        (bundle / 'documents.jsonl').write_bytes(content)
        report = {'accepted': 1, 'documents_sha256': digest(content)}
        if name == 'chinese_laws':
            content = ''.join(json.dumps(clause, ensure_ascii=False) + '\n' for clause in clauses).encode('utf-8')
            (bundle / 'clauses.jsonl').write_bytes(content)
            report.update(article_count=2, clauses_sha256=digest(content))
        (bundle / 'quality_report.json').write_text(json.dumps(report), encoding='utf-8')
    return document, law


@override_settings(EMBEDDING_PROVIDER='', EMBEDDING_MODEL='local-hash-v1', EMBEDDING_DIMENSION=128)
class CorpusImportTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.document, self.law = fixture(self.root)
        self.admin = get_user_model().objects.create_user(username='corpus-admin', role='admin', is_staff=True)

    def test_import_keeps_exact_clauses_and_source_metadata_and_is_idempotent(self):
        first = import_corpus(self.root, self.admin.pk, local_index=True)
        self.assertEqual(first['total_documents'], 2)
        self.assertEqual(first['legal_articles'], 2)
        self.assertEqual(DocumentSource.objects.count(), 1)
        self.assertEqual(LegalDocument.objects.count(), 1)
        self.assertEqual(list(LegalClause.objects.order_by('order').values_list('text', flat=True)),
                         ['第一条\u3000保护个人信息。', '第二条\u3000最小必要原则。'])
        document = DocumentSource.objects.get()
        self.assertEqual(document.visibility, 'internal')
        self.assertEqual(document.metadata['source_url'], 'https://example.com/')
        self.assertFalse(document.metadata['published'])
        self.assertEqual(LegalDocument.objects.get().effective_date.isoformat(), '2026-01-01')
        original_ids = list(LegalKnowledgeEmbedding.objects.order_by('pk').values_list('pk', flat=True))
        second = import_corpus(self.root, self.admin.pk, local_index=True)
        self.assertEqual(second['skipped_documents'], 2)
        self.assertEqual(list(LegalKnowledgeEmbedding.objects.order_by('pk').values_list('pk', flat=True)), original_ids)

    def test_same_official_version_reuses_existing_legal_document_id(self):
        existing = LegalDocument.objects.create(title='测试法律', source_url='https://example.com/',
            source_hash='old-hash', full_text='old text', status='draft')
        import_corpus(self.root, self.admin.pk, local_index=True)
        self.assertEqual(LegalDocument.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.full_text, self.law['source_snapshot'])
        self.assertEqual(existing.status, 'draft')

    def test_existing_staff_document_visibility_is_preserved(self):
        document = IngestionService().ingest_bytes(data=self.document['source_snapshot'].encode(),
            filename='auth.md', title='Existing', visibility='staff', uploaded_by=self.admin)
        import_corpus(self.root, self.admin.pk, local_index=True)
        document.refresh_from_db()
        self.assertEqual(document.visibility, 'staff')
        self.assertEqual(document.title, 'Existing')

    def test_failure_mid_batch_rolls_back_all_new_documents(self):
        with patch('legal_kb.services.corpus_import.LegalKbIngestionService.ingest_document', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                import_corpus(self.root, self.admin.pk, local_index=True)
        self.assertFalse(DocumentSource.objects.exists())
        self.assertFalse(LegalDocument.objects.exists())
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    def test_corrupt_markdown_is_rejected_before_database_writes(self):
        (self.root / 'owasp' / 'markdown/auth.md').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Markdown hash mismatch'):
            import_corpus(self.root, self.admin.pk, local_index=True)
        self.assertFalse(DocumentSource.objects.exists())

    def test_student_cannot_import(self):
        student = get_user_model().objects.create_user(username='student', role='student')
        with self.assertRaises(PermissionError):
            import_corpus(self.root, student.pk, local_index=True)
        self.assertFalse(DocumentSource.objects.exists())

    @override_settings(EMBEDDING_PROVIDER='qwen', EMBEDDING_MODEL='text-embedding-v4')
    def test_explicit_local_index_is_not_mislabeled_as_remote_semantic_index(self):
        service = EmbeddingService(local_only=True)
        self.assertEqual(service.retrieval_mode, 'deterministic')
        self.assertEqual(service.model, 'local-hash-v1')
        self.assertEqual(len(service.embed_text('hello')), 128)
        import_corpus(self.root, self.admin.pk, local_index=True)
        self.assertTrue(all(e.metadata['retrieval_mode'] == 'deterministic' for e in LegalKnowledgeEmbedding.objects.all()))

    def test_imported_documents_can_be_retrieved_with_current_access_controls(self):
        import_corpus(self.root, self.admin.pk, local_index=True)
        service = LegalRetrievalService(embedding_service=EmbeddingService(local_only=True))
        found = service.retrieve(query='Authentication passwords', filters={'source_type': 'document'}, user=self.admin)
        self.assertTrue(found)
        student = get_user_model().objects.create_user(username='reader-student', role='student')
        self.assertEqual(service.retrieve(query='Authentication passwords', filters={'source_type': 'document'}, user=student), [])


class BundledCorpusTests(TestCase):
    def test_real_merged_corpus_is_complete(self):
        root = Path(__file__).resolve().parents[1] / 'data/knowledge_corpus'
        corpus = validate_corpus(root)
        self.assertEqual((len(corpus['owasp']), len(corpus['chinese_laws']), len(corpus['clauses'])), (246, 7, 393))

    def test_validation_command_does_not_require_an_admin_or_write_database(self):
        output = io.StringIO()
        call_command('import_knowledge_corpus', validate_only=True, stdout=output)
        self.assertIn('246 OWASP documents', output.getvalue())
        self.assertFalse(DocumentSource.objects.exists())
