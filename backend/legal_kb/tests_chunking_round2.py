"""Bounded teaching windows and long-article citation regressions."""

from django.test import SimpleTestCase, TestCase, override_settings

from .models import LegalDocument, LegalKnowledgeEmbedding
from .services.chunking_service import ChunkingService
from .services.hashing import sha256_text
from .services.ingestion_service import LegalKbIngestionService


class TeachingChunkingTests(SimpleTestCase):
    def test_long_article_is_split_with_stable_unique_citations(self):
        body = '第一条' + ('甲' * 99 + '。') * 25
        text = '第一章 教学规范\n' + body + '\n第二条 短条。\n第一条 同号短条。'
        chunks = ChunkingService.split_legal_text(text)
        long_parts = chunks[:-2]
        self.assertGreater(len(long_parts), 1)
        self.assertEqual(long_parts[0].clause_key, '第一条')
        self.assertEqual(long_parts[1].clause_key, '第一条-part-2')
        self.assertTrue(all(chunk.article_number == '第一条' for chunk in long_parts))
        self.assertTrue(all(chunk.title == '第一条' for chunk in long_parts))
        self.assertTrue(all(chunk.chapter == '第一章 教学规范' for chunk in long_parts))
        self.assertEqual(chunks[-2].text, '第二条短条。')
        self.assertEqual(chunks[-2].clause_key, '第二条')
        self.assertEqual(chunks[-1].clause_key, '第一条-2')
        self.assertEqual(len({chunk.clause_key for chunk in chunks}), len(chunks))
        self.assertEqual([chunk.order for chunk in chunks], list(range(1, len(chunks) + 1)))
        self.assertTrue(all(len(chunk.text) <= 1319 for chunk in chunks))
        self.assertEqual(long_parts[0].text + ''.join(c.text[160:] for c in long_parts[1:]), body)
        self.assertEqual(chunks, ChunkingService.split_legal_text(text))

    def test_line_start_articles_do_not_split_inline_references(self):
        text = '第一条 ' + ('按照第三条的规定，完成课后实验。' * 120) + '\n第二条 短条。'
        chunks = ChunkingService.split_legal_text(text, max_chars=800, overlap=100)
        self.assertGreater(len(chunks), 2)
        self.assertEqual({c.article_number for c in chunks[:-1]}, {'第一条'})
        self.assertEqual(chunks[-1].article_number, '第二条')
        self.assertTrue(all(len(c.text) <= 919 for c in chunks))

    def test_inline_short_articles_keep_v2_behavior(self):
        text = '第一条 为了保护个人信息权益。第二条 处理个人信息应当合法、正当、必要。'
        chunks = ChunkingService.split_legal_text(text)
        self.assertEqual([c.clause_key for c in chunks], ['第一条', '第二条'])
        self.assertEqual([c.text for c in chunks], ['第一条为了保护个人信息权益。', '第二条处理个人信息应当合法、正当、必要。'])

    def test_tail_is_absorbed_with_bounded_tolerance(self):
        for overlap in (0, 100):
            for suffix in (1, 19, 119):
                with self.subTest(overlap=overlap, suffix=suffix):
                    text = '甲' * 799 + '。' + '乙' * (suffix - 1) + '。'
                    chunks = ChunkingService.split_plain_text(text, max_chars=800, overlap=overlap)
                    self.assertEqual(len(chunks), 1)
                    self.assertEqual(chunks[0].text, text)
                    self.assertLessEqual(len(chunks[0].text), 919)
        chunks = ChunkingService.split_plain_text('甲' * 920, max_chars=800, overlap=0)
        self.assertEqual([len(c.text) for c in chunks], [800, 120])

    def test_no_tail_or_lost_characters_across_window_sizes(self):
        for size, overlap in ((800, 100), (800, 0), (1200, 160), (1200, 0)):
            for length in (801, 919, 920, 1601, 2419, 5000):
                with self.subTest(size=size, overlap=overlap, length=length):
                    text = ''.join(chr(0x4e00 + i) for i in range(length))
                    chunks = ChunkingService.split_plain_text(text, max_chars=size, overlap=overlap)
                    self.assertTrue(all(120 <= len(c.text) <= size + 119 for c in chunks))
                    rebuilt = chunks[0].text + ''.join(c.text[overlap:] for c in chunks[1:])
                    self.assertEqual(rebuilt, text)

    def test_sentence_end_wins_over_heading_or_comma(self):
        text = '甲' * 500 + '。\n\n## 小标题\n' + '乙' * 100 + '，' + '丙' * 400 + '。'
        chunks = ChunkingService.split_plain_text(text, max_chars=800, overlap=100)
        self.assertTrue(all(c.text.endswith('。') for c in chunks))
        self.assertEqual(len(chunks[0].text), 501)

    def test_sentence_in_first_half_is_used_before_hard_cut(self):
        text = '甲' * 199 + '。' + '乙' * 1500
        chunks = ChunkingService.split_plain_text(text, max_chars=800, overlap=100)
        self.assertEqual(chunks[0].text, text[:200])

    def test_comma_and_enumeration_comma_are_fallback_boundaries(self):
        for separator in ('，', '、', ','):
            with self.subTest(separator=separator):
                text = ('甲' * 172 + separator) * 15
                chunks = ChunkingService.split_plain_text(text, max_chars=800, overlap=100)
                self.assertGreater(len(chunks), 1)
                self.assertTrue(all(chunk.text.endswith(separator) for chunk in chunks))
                self.assertEqual(chunks[0].text + ''.join(c.text[100:] for c in chunks[1:]), text)
                self.assertTrue(all(120 <= len(c.text) <= 919 for c in chunks))

    def test_short_document_is_not_padded_or_dropped(self):
        chunks = ChunkingService.split_plain_text('  短文。\n', max_chars=800, overlap=100)
        self.assertEqual([chunk.text for chunk in chunks], ['短文。'])


class ChunkingProbeTests(SimpleTestCase):
    def test_original_samples_reproduce_v2_and_meet_round2_targets(self):
        from .evaluate_chunking import evaluate

        report = evaluate()
        results = report['results']
        self.assertEqual(results['v2_legal_1200_160']['legal-long-article']['max_chars'], 2435)
        self.assertEqual(results['v2_teaching_800_100']['article-md']['sentence_end_rate'], 0.5)
        for sample in results['v3_teaching_800_100'].values():
            self.assertGreaterEqual(sample['sentence_end_rate'], 0.9)
            self.assertEqual(sample['under_120'], 0)
            self.assertLessEqual(sample['max_chars'], 919)
        legal = results['v3_legal_1200_160']['legal-long-article']
        self.assertLessEqual(legal['max_chars'], 1319)
        self.assertEqual(legal['tiny_under_50'], 2)  # Intentionally atomic short articles.
        self.assertFalse(legal['tail_under_120'])
        self.assertEqual(report, evaluate())


@override_settings(EMBEDDING_PROVIDER='', EMBEDDING_MODEL='local-hash-v1', EMBEDDING_DIMENSION=128)
class LongArticleIngestionTests(TestCase):
    def test_persisted_subclauses_keep_article_and_hash_identity(self):
        document = LegalDocument.objects.create(
            title='教学长条测试', source_hash='round2-long-article',
            full_text='第一条 ' + '依法完成实验并保存授权记录。' * 220 + '\n第二条 短条。',
        )
        job = LegalKbIngestionService().ingest_document(document)
        clauses = list(document.clauses.all())
        self.assertGreater(len(clauses), 2)
        self.assertEqual(job.total_chunks, len(clauses))
        self.assertEqual(job.embedded_chunks, len(clauses))
        self.assertEqual([c.article_number for c in clauses[:-1]], ['第一条'] * (len(clauses) - 1))
        self.assertEqual(clauses[-1].clause_key, '第二条')
        for clause in clauses:
            row = LegalKnowledgeEmbedding.objects.get(source_type='legal_clause', object_id=clause.pk)
            self.assertEqual(row.text, clause.text)
            self.assertEqual(row.text_hash, sha256_text(clause.text))
            self.assertEqual(row.metadata['clause_key'], clause.clause_key)
            self.assertEqual(row.metadata['chunking_version'], ChunkingService.VERSION)
            self.assertTrue(row.index_version)
            self.assertLessEqual(len(row.text), 1319)
