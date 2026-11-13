"""Both optional and built-in splitters obey the teaching size contract."""

import sys
from contextlib import nullcontext
from copy import deepcopy
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from legal_kb.services.chunking_service import ChunkingService

from .chunking import StructureAwareChunker


class StructureAwareChunkingTests(SimpleTestCase):
    def test_default_settings_match_platform_teaching_constants(self):
        chunker = StructureAwareChunker()
        self.assertEqual(settings.RAG_INGESTION_CHUNK_SIZE, ChunkingService.TEACHING_MAX_CHARS)
        self.assertEqual(settings.RAG_INGESTION_CHUNK_OVERLAP, ChunkingService.TEACHING_OVERLAP)
        self.assertEqual((chunker.chunk_size, chunker.chunk_overlap), (800, 100))

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False)
    def test_builtin_passes_custom_overlap_including_zero(self):
        text = ''.join(chr(0x4e00 + i) for i in range(1800))
        for overlap in (0, 37, 100):
            with self.subTest(overlap=overlap):
                with patch.object(ChunkingService, 'split_plain_text', wraps=ChunkingService.split_plain_text) as split:
                    chunks = StructureAwareChunker(chunk_size=800, chunk_overlap=overlap).split(text)
                split.assert_called_once_with(text, max_chars=800, overlap=overlap)
                self.assertEqual(chunks[0].text + ''.join(c.text[overlap:] for c in chunks[1:]), text)

    def test_invalid_settings_are_not_silently_replaced_or_backend_dependent(self):
        for enabled in (True, False):
            for size, overlap in ((0, 0), (-1, 0), (800, -1), (800, 800)):
                with self.subTest(enabled=enabled, size=size, overlap=overlap):
                    with override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=enabled):
                        with self.assertRaises(ValueError):
                            StructureAwareChunker(chunk_size=size, chunk_overlap=overlap)

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=True)
    def test_optional_dependency_missing_uses_builtin(self):
        text = '# 课程\n\n## 授权实验\n\n' + ('教学材料。' * 200) + '结尾。'
        with patch.dict(sys.modules, {'langchain_text_splitters': None}):
            chunks = StructureAwareChunker().split(text)
        expected = ChunkingService.split_plain_text(text, max_chars=800, overlap=100)
        self.assertEqual([c.text for c in chunks], [c.text for c in expected])
        self.assertTrue(all(c.metadata['heading_path'] == ['课程', '授权实验'] for c in chunks))

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=True)
    def test_optional_success_and_failures_preserve_overlap_and_heading_metadata(self):
        text = '# 课程\n\n## 授权实验\n\n' + '先确认授权范围，再执行教学实验。' * 100
        metadata = {'source': 'fixture', 'document': {'id': 17}, 'heading_path': ['旧路径']}
        original_metadata = deepcopy(metadata)
        for mode in ('success', 'header_failure', 'recursive_failure'):
            for overlap in (0, 37):
                with self.subTest(mode=mode, overlap=overlap):
                    module = ModuleType('langchain_text_splitters')
                    doc = SimpleNamespace(page_content='授权实验正文。', metadata={'h1': '课程', 'h2': '授权实验'})
                    header_splitter = Mock()
                    header_splitter.split_text.return_value = [doc]
                    recursive_splitter = Mock()
                    recursive_splitter.split_documents.return_value = [doc]
                    module.MarkdownHeaderTextSplitter = Mock(return_value=header_splitter)
                    module.RecursiveCharacterTextSplitter = Mock(return_value=recursive_splitter)
                    if mode == 'header_failure':
                        header_splitter.split_text.side_effect = RuntimeError('split failed')
                    elif mode == 'recursive_failure':
                        recursive_splitter.split_documents.side_effect = RuntimeError('split failed')
                    log_context = (
                        self.assertLogs('rag_ingestion.chunking', level='WARNING')
                        if mode != 'success' else nullcontext()
                    )
                    with patch.dict(sys.modules, {'langchain_text_splitters': module}), log_context:
                        chunks = StructureAwareChunker(chunk_size=400, chunk_overlap=overlap).split(
                            text, metadata=metadata,
                        )
                    self.assertGreater(len(chunks), 1)
                    self.assertEqual(chunks[0].text + ''.join(c.text[overlap:] for c in chunks[1:]), text)
                    if overlap:
                        for left, right in zip(chunks, chunks[1:]):
                            self.assertEqual(left.text[-overlap:], right.text[:overlap])
                    self.assertEqual([c.order for c in chunks], list(range(1, len(chunks) + 1)))
                    for chunk in chunks:
                        self.assertEqual(chunk.metadata['heading_path'], ['课程', '授权实验'])
                        self.assertIn(['课程', '授权实验'], chunk.metadata['heading_paths'])
                        self.assertEqual(chunk.title, '授权实验')
                        self.assertEqual(chunk.metadata['source'], 'fixture')
                        self.assertEqual(chunk.metadata['document'], {'id': 17})
                    self.assertEqual(metadata, original_metadata)
                    header_splitter.split_text.assert_called_once()
                    if mode != 'header_failure':
                        recursive_splitter.split_documents.assert_called_once()

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=True)
    def test_langchain_uses_chinese_separators_and_keeps_sentence_ends(self):
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError:
            self.skipTest('Optional langchain_text_splitters is not installed')
        text = '# 课程\n\n## 授权实验\n\n' + ('甲' * 199 + '。') * 12
        chunker = StructureAwareChunker()
        with patch('langchain_text_splitters.RecursiveCharacterTextSplitter', wraps=RecursiveCharacterTextSplitter) as factory:
            chunks = chunker._split_with_langchain(text, {'source': 'fixture'})
        self.assertIsNotNone(chunks)  # Exercise the installed backend, not fallback.
        options = factory.call_args.kwargs
        for separator in ('。', '；', '，', '、', '\n'):
            self.assertIn(separator, options['separators'])
        self.assertEqual(options['keep_separator'], 'end')
        self.assertEqual((options['chunk_size'], options['chunk_overlap']), (800, 100))
        self.assertTrue(all(120 <= len(c.text) <= 919 for c in chunks))
        self.assertTrue(all(c.text.endswith('。') for c in chunks))
        self.assertEqual(chunks[0].metadata['heading_path'], ['课程', '授权实验'])
        self.assertEqual(chunks[0].metadata['source'], 'fixture')

    def test_both_paths_remove_tiny_tail_and_preserve_content(self):
        text = '甲' * 799 + '。' + '乙' * 18 + '。'
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                with override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=enabled):
                    chunks = StructureAwareChunker().split(text)
                self.assertEqual([c.text for c in chunks], [text])
                self.assertLessEqual(len(chunks[0].text), 919)

    def test_both_paths_respect_custom_window_contract(self):
        text = ('甲' * 139 + '，乙' * 9 + '。') * 20
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                with override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=enabled):
                    chunks = StructureAwareChunker(chunk_size=500, chunk_overlap=60).split(text)
                self.assertGreater(len(chunks), 1)
                self.assertTrue(all(120 <= len(c.text) <= 619 for c in chunks))
                self.assertEqual([c.order for c in chunks], list(range(1, len(chunks) + 1)))

    def test_short_header_sections_are_rewindowed_without_losing_heading_context(self):
        text = '# 课程\n\n简介。\n\n## 实验\n\n' + '先确认授权范围，再执行教学实验。' * 60 + '\n\n## 总结\n\n遵守授权。'
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                with override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=enabled):
                    chunks = StructureAwareChunker().split(text, metadata={'source': 'fixture'})
                self.assertTrue(all(120 <= len(c.text) <= 919 for c in chunks))
                self.assertEqual(chunks[0].metadata['heading_path'], ['课程'])
                self.assertIn(['课程', '实验'], chunks[0].metadata['heading_paths'])
                self.assertIn('简介。', chunks[0].text)
                self.assertTrue(chunks[-1].text.endswith('遵守授权。'))
                self.assertTrue(all(c.metadata['source'] == 'fixture' for c in chunks))

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False)
    def test_fenced_code_is_not_heading_metadata(self):
        text = '# 课程\n\n```sh\n# not a heading\n```\n\n' + '练习。' * 60
        chunks = StructureAwareChunker().split(text)
        self.assertEqual(chunks[0].metadata['heading_path'], ['课程'])
        self.assertEqual(chunks[0].metadata['heading_paths'], [['课程']])

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False)
    def test_builtin_heading_preserves_csharp_and_strips_only_closing_markers(self):
        text = '# C#\n\n## 实验 ##\n\n' + '练习。' * 60
        chunks = StructureAwareChunker().split(text)
        self.assertEqual(chunks[0].metadata['heading_path'], ['C#', '实验'])
        self.assertEqual(chunks[0].title, '实验')
        self.assertIn(['C#'], chunks[0].metadata['heading_paths'])
        self.assertIn(['C#', '实验'], chunks[0].metadata['heading_paths'])

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False)
    def test_skipped_heading_levels_do_not_turn_siblings_into_descendants(self):
        for prefix, parent in (('# 课程\n\n', ['课程']), ('', [])):
            for level in (2, 3, 6):
                with self.subTest(prefix=prefix, level=level):
                    marker = '#' * level
                    text = f'{prefix}{marker} 实验一\n\n第一段。\n\n{marker} 实验二\n\n第二段。'
                    chunks = StructureAwareChunker().split(text)
                    paths = chunks[0].metadata['heading_paths']
                    self.assertIn(parent + ['实验一'], paths)
                    self.assertIn(parent + ['实验二'], paths)
                    self.assertNotIn(parent + ['实验一', '实验二'], paths)
                    self.assertEqual(chunks[0].metadata['heading_path'], parent + ['实验一'])

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False)
    def test_consecutive_parent_headings_use_first_body_section_as_primary_path(self):
        text = '# 课程\n\n## 第一章\n\n### 授权实验\n\n' + '先确认授权再操作。' * 180
        chunks = StructureAwareChunker().split(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(chunk.metadata['heading_path'], ['课程', '第一章', '授权实验'])
            self.assertEqual(chunk.title, '授权实验')
        self.assertIn(['课程'], chunks[0].metadata['heading_paths'])
        self.assertIn(['课程', '第一章'], chunks[0].metadata['heading_paths'])

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False)
    def test_invalid_fence_closers_do_not_expose_code_comments_as_headings(self):
        for opening, false_closing, closing in (
            ('```python', '``` trailing text', '```'),
            ('~~~~', '~~~~ trailing text', '~~~~'),
            ('````', '```', '````'),
            ('```python', '~~~', '```'),
        ):
            with self.subTest(opening=opening, false_closing=false_closing):
                text = (
                    f'# 课程\n\n{opening}\n{false_closing}\n# 代码中的注释\n{closing}\n\n'
                    '## 正文\n\n学习内容。'
                )
                chunks = StructureAwareChunker().split(text)
                self.assertEqual(chunks[0].metadata['heading_paths'], [['课程'], ['课程', '正文']])
                self.assertEqual(chunks[0].text, text)

    @override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=False)
    def test_overlap_starting_inside_heading_retains_complete_path(self):
        title = '较长的授权实验标题' * 3
        text = f'# 课程\n\n## {title}\n\n' + '正文内容' * 40
        chunks = StructureAwareChunker(chunk_size=40, chunk_overlap=15).split(text)
        second_start = 25
        self.assertLess(text.index('## '), second_start)
        self.assertGreater(text.index('\n', text.index('## ')), second_start)
        self.assertEqual(chunks[1].text, text[second_start:second_start + 40])
        self.assertEqual(chunks[0].text + ''.join(c.text[15:] for c in chunks[1:]), text)
        for chunk in chunks:
            self.assertEqual(chunk.metadata['heading_path'], ['课程', title])
            self.assertEqual(chunk.title, title)

    def test_empty_and_short_sources_do_not_gain_padding(self):
        for enabled in (True, False):
            with override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=enabled):
                chunker = StructureAwareChunker()
                self.assertEqual(chunker.split(' \n'), [])
                self.assertEqual([c.text for c in chunker.split('短文。')], ['短文。'])
