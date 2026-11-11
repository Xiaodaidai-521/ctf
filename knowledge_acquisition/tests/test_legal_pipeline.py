import contextlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import legal_pipeline as legal


SOURCE = {
    'id': 'cn-test-law', 'title': '测试法律', 'bbbs': 'a' * 32,
    'published_date': '2025-10-28', 'effective_date': '2026-01-01',
    'document_type': 'law', 'expected_articles': 3, 'summary': 'Testing',
}
PARAGRAPHS = ['测试法律', '第一章\u3000总则', '第一条\u3000目的。',
              '（一）第一项；', '（二）第二项。', '第二章\u3000附则',
              '第二条\u3000义务。', '第三条\u3000本法自2017年6月1日起施行。']


def docx(paragraphs):
    root = ElementTree.Element(legal.W + 'document')
    body = ElementTree.SubElement(root, legal.W + 'body')
    for text in paragraphs:
        paragraph = ElementTree.SubElement(body, legal.W + 'p')
        run = ElementTree.SubElement(paragraph, legal.W + 'r')
        ElementTree.SubElement(run, legal.W + 't').text = text
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('word/document.xml', ElementTree.tostring(root, encoding='utf-8'))
    return output.getvalue()


class ParsingTests(unittest.TestCase):
    def test_numbers_cover_the_civil_code_range(self):
        for text, expected in [('十', 10), ('八十一', 81), ('一百零一', 101),
                               ('一千零三十二', 1032), ('一千二百六十', 1260)]:
            self.assertEqual(legal.chinese_number(text), expected)

    def test_clauses_preserve_subitems_and_exclude_next_chapter(self):
        text, articles = legal.normalize(SOURCE, PARAGRAPHS)
        self.assertEqual([a['article_number'] for a in articles], [1, 2, 3])
        self.assertIn('（一）第一项；\n\n（二）第二项。', articles[0]['text'])
        self.assertNotIn('第二章', articles[0]['text'])
        self.assertEqual(articles[1]['chapter'], '第二章\u3000附则')
        self.assertIn('## 第二章', text)

    def test_missing_or_duplicate_article_rejects_incomplete_text(self):
        for paragraphs in [PARAGRAPHS[:-1], PARAGRAPHS + ['第三条\u3000重复。']]:
            with self.assertRaisesRegex(ValueError, 'Article sequence incomplete'):
                legal.normalize(SOURCE, paragraphs)

    def test_excerpt_keeps_original_numbers_and_no_other_articles(self):
        source = deepcopy(SOURCE)
        source['display_title'] = '测试法律（节选）'
        source['article_range'] = [2, 3]
        text, articles = legal.normalize(source, PARAGRAPHS)
        self.assertEqual([a['article_number'] for a in articles], [2, 3])
        self.assertTrue(text.startswith('# 测试法律（节选）'))
        self.assertNotIn('第一条', text)

    def test_docx_roundtrip_preserves_chinese_punctuation(self):
        self.assertEqual(legal.paragraphs_from_docx(docx(PARAGRAPHS)), PARAGRAPHS)

    def test_xml_entity_declaration_is_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('word/document.xml', b'<!DOCTYPE test><test/>')
        with self.assertRaisesRegex(ValueError, 'Unsupported document XML'):
            legal.paragraphs_from_docx(output.getvalue())


class LegalBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = {'as_of_date': '2026-11-12', 'sources': [SOURCE], 'pending_sources': []}
        self.details = {'title': SOURCE['title'], 'gbrq': SOURCE['published_date'],
                        'sxrq': SOURCE['effective_date'], 'sxx': 3, 'zdjgName': '测试发布机关'}

    def request_response(self, url, body=None, limit=None):
        if 'flfgDetails' in url:
            return json.dumps({'code': 200, 'data': self.details}).encode('utf-8')
        if '/download/pc' in url:
            return json.dumps({'code': 200, 'data': {'url': 'https://flkoss.obs-bj2.cucloud.cn/test.docx?X-Amz-Signature=temporary'}}).encode()
        return docx(PARAGRAPHS)

    def run_fixture(self):
        with patch.object(legal, 'request', side_effect=self.request_response), contextlib.redirect_stdout(io.StringIO()):
            legal.collect(SOURCE, self.root)
            legal.clean(self.config, self.root)

    def test_version_effective_date_is_not_replaced_by_original_law_final_article(self):
        self.run_fixture()
        root = self.root / 'staged_legal'
        record = json.loads((root / 'documents.jsonl').read_text(encoding='utf-8'))
        self.assertEqual(record['effective_date'], '2026-01-01')
        self.assertIn('2017年6月1日', record['source_snapshot'])
        self.assertIsNone(record['verified_at'])
        self.assertEqual(record['review_status'], 'pending')
        self.assertFalse(record['published'])
        self.assertEqual(legal.verify(root), (1, 3))

    def test_expiring_download_signature_does_not_enter_manifest_or_bundle(self):
        self.run_fixture()
        for path in list((self.root / 'raw').rglob('*.json')) + list((self.root / 'staged_legal').glob('*.json')):
            self.assertNotIn('X-Amz-Signature', path.read_text(encoding='utf-8'))

    def test_superseded_or_mismatched_official_version_is_rejected(self):
        for key, value in [('sxx', 2), ('title', '其他法律'), ('sxrq', '2017-06-01')]:
            original = self.details[key]
            self.details[key] = value
            with patch.object(legal, 'request', side_effect=self.request_response):
                with self.assertRaises(ValueError):
                    legal.collect(SOURCE, self.root)
            self.details[key] = original

    def test_raw_tampering_preserves_existing_bundle(self):
        self.run_fixture()
        before = (self.root / 'staged_legal' / 'documents.jsonl').read_bytes()
        (self.root / 'raw' / 'chinese_laws' / SOURCE['id'] / SOURCE['bbbs'] / 'source.docx').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Raw official source hash mismatch'):
            legal.clean(self.config, self.root)
        self.assertEqual((self.root / 'staged_legal' / 'documents.jsonl').read_bytes(), before)

    def test_tampered_clause_fails_verification(self):
        self.run_fixture()
        root = self.root / 'staged_legal'
        records = [json.loads(line) for line in (root / 'clauses.jsonl').read_text(encoding='utf-8').splitlines()]
        records[0]['text'] = '修改的条文。'
        content = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records).encode('utf-8')
        (root / 'clauses.jsonl').write_bytes(content)
        report = legal.read_json(root / 'quality_report.json')
        report['clauses_sha256'] = legal.sha256(content)
        legal.write_json(root / 'quality_report.json', report)
        with self.assertRaisesRegex(ValueError, 'article hash'):
            legal.verify(root)

    def test_refresh_does_not_replace_the_owasp_bundle(self):
        owasp = self.root / 'staged' / 'documents.jsonl'
        owasp.parent.mkdir()
        owasp.write_bytes(b'Existing OWASP bundle')
        self.run_fixture()
        self.assertEqual(owasp.read_bytes(), b'Existing OWASP bundle')


if __name__ == '__main__':
    unittest.main()
