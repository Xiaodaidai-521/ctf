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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pipeline


SOURCE = {
    'id': 'example-docs', 'repository': 'OWASP/example', 'ref': 'v1',
    'commit': 'a' * 40, 'snapshot_date': '2026-11-11',
    'include': 'docs/*.md', 'exclude_names': ['README.md'],
    'publisher': 'Example contributors', 'language': 'en',
    'license_id': 'CC-BY-SA-4.0', 'license_path': 'LICENSE',
    'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
    'applicability': 'Pending teaching review',
}
DOCUMENT = '# SQL testing\n\n' + 'A useful security explanation. ' * 20 + '\n'


class MarkdownTests(unittest.TestCase):
    def test_inline_triple_backticks_do_not_hide_following_links(self):
        raw = b'```https://example.com/a```\n\n[next](next.md)\n'
        cleaned = pipeline.normalize_markdown(raw, SOURCE, 'docs/a.md')
        self.assertIn('```https://example.com/a```', cleaned)
        self.assertIn(pipeline.blob_url(SOURCE, 'docs/next.md'), cleaned)

    def test_list_links_images_and_balanced_destinations(self):
        raw = ('- Parent\n    - [nested](../docs/a(b).md)\n\n'
               '![image](../images/picture.png)\n'
               '[space](<other file.md>)\n'
               '`` `[example](unchanged.md)` ``\n').encode()
        cleaned = pipeline.normalize_markdown(raw, SOURCE, 'docs/a.md')
        self.assertIn(pipeline.blob_url(SOURCE, 'docs/a(b).md').replace('%28', '(').replace('%29', ')'), cleaned)
        self.assertIn('https://raw.githubusercontent.com/OWASP/example/' + SOURCE['commit'] + '/images/picture.png', cleaned)
        self.assertIn('other%20file.md', cleaned)
        self.assertIn('`` `[example](unchanged.md)` ``', cleaned)

    def test_inline_code_in_link_label_keeps_label_but_resolves_destination(self):
        raw = b'An `[Authorize]` attribute. [the `__Host-` cookie prefix](Session_Management.md#prefix)\n'
        cleaned = pipeline.normalize_markdown(raw, SOURCE, 'docs/a.md')
        self.assertIn('[the `__Host-` cookie prefix]', cleaned)
        self.assertIn('https://github.com/OWASP/example/blob/' + SOURCE['commit'] + '/docs/Session_Management.md#prefix', cleaned)

    def test_code_payloads_and_tables_survive_cleaning(self):
        raw = ('\ufeff---\r\ntitle: source\r\n---\r\n# Heading\r\n\r\n\r\n'
               '|a|b|\r\n|-|-|\r\n<script>alert(1)</script>\r\n'
               '```html\r\n[x](relative.md)  \r\n\r\n\r\n<!-- example -->\r\n```\r\n'
               '    [code](local.md)  \r\n'
               '`[inline](relative.md)`\r\n'
               '~~~~sql\r\nSELECT  * FROM users;  \r\n~~~~\r\n').encode('utf-8')
        cleaned = pipeline.normalize_markdown(raw, SOURCE, 'docs/a.md')
        self.assertTrue(cleaned.startswith('# Heading\n\n|a|b|'))
        self.assertIn('<script>alert(1)</script>', cleaned)
        self.assertIn('```html\n[x](relative.md)  \n\n\n<!-- example -->\n```', cleaned)
        self.assertIn('    [code](local.md)  ', cleaned)
        self.assertIn('`[inline](relative.md)`', cleaned)
        self.assertIn('SELECT  * FROM users;  ', cleaned)

    def test_relative_links_pin_version_but_external_and_anchors_stay(self):
        raw = ('[relative](../images/a.png)\n[root](/docs/root.md)\n'
               '[anchor](#summary) [external](https://example.com/a)\n'
               '[1]: other.md "a title"\n').encode()
        cleaned = pipeline.normalize_markdown(raw, SOURCE, 'docs/a.md')
        base = f"https://github.com/OWASP/example/blob/{SOURCE['commit']}/"
        self.assertIn(f'[relative]({base}images/a.png)', cleaned)
        self.assertIn(f'[root]({base}docs/root.md)', cleaned)
        self.assertIn('[anchor](#summary)', cleaned)
        self.assertIn('[external](https://example.com/a)', cleaned)
        self.assertIn(f'[1]: {base}docs/other.md "a title"', cleaned)


class StagingTests(unittest.TestCase):
    def test_open_windows_directory_is_updated_with_previous_bundle_backed_up(self):
        self.collect_and_clean()
        staged = self.root / 'staged'
        before = (staged / 'documents.jsonl').read_bytes()
        original_rename = Path.rename
        def rename(path, target):
            if path == staged:
                raise PermissionError('Open directory handle')
            return original_rename(path, target)
        with patch.object(Path, 'rename', rename), self.quiet:
            pipeline.clean([SOURCE], self.root)
        self.assertEqual(pipeline.verify(staged), 1)
        backups = list((self.root / '.working').glob('previous-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'documents.jsonl').read_bytes(), before)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        archive = self.root / 'raw' / '_archives' / f"{SOURCE['id']}-{SOURCE['commit']}.zip"
        archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('repo/LICENSE', 'Example CC BY-SA license')
            output.writestr('repo/docs/a.md', DOCUMENT)
            output.writestr('repo/docs/b.md', DOCUMENT)
            output.writestr('repo/docs/tiny.md', '# Too short\n')
            output.writestr('repo/docs/README.md', '# Navigation\n')
        self.quiet = contextlib.redirect_stdout(io.StringIO())

    def collect_and_clean(self):
        with self.quiet:
            pipeline.collect(SOURCE, self.root)
            pipeline.clean([SOURCE], self.root)

    def test_offline_collection_deduplicates_and_keeps_review_pending(self):
        self.collect_and_clean()
        staged = self.root / 'staged'
        report = pipeline.read_json(staged / 'quality_report.json')
        self.assertEqual((report['collected'], report['accepted']), (3, 1))
        self.assertEqual(len(report['duplicates']), 1)
        self.assertEqual(len(report['rejected']), 1)
        record = json.loads((staged / 'documents.jsonl').read_text(encoding='utf-8'))
        self.assertIsNone(record['verified_at'])
        self.assertIsNone(record['source_date'])
        self.assertEqual(record['review_status'], 'pending')
        self.assertFalse(record['published'])
        self.assertEqual(pipeline.verify(staged), 1)

    def test_raw_tampering_fails_without_replacing_previous_staging(self):
        self.collect_and_clean()
        before = (self.root / 'staged' / 'documents.jsonl').read_bytes()
        path = self.root / 'raw' / SOURCE['id'] / SOURCE['commit'] / 'docs/a.md'
        path.write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Raw content hash mismatch'):
            pipeline.clean([SOURCE], self.root)
        self.assertEqual((self.root / 'staged' / 'documents.jsonl').read_bytes(), before)

    def test_clean_is_repeatable_and_replaces_stale_markdown(self):
        self.collect_and_clean()
        before = (self.root / 'staged' / 'documents.jsonl').read_bytes()
        (self.root / 'staged' / 'markdown' / 'old.md').write_text('old', encoding='utf-8')
        with self.quiet:
            pipeline.clean([SOURCE], self.root)
        self.assertEqual((self.root / 'staged' / 'documents.jsonl').read_bytes(), before)
        self.assertFalse((self.root / 'staged' / 'markdown' / 'old.md').exists())
        self.assertEqual(pipeline.verify(self.root / 'staged'), 1)

    def test_modified_markdown_or_license_fails_verification(self):
        self.collect_and_clean()
        staged = self.root / 'staged'
        md = next((staged / 'markdown').glob('*.md'))
        original = md.read_bytes()
        md.write_text('tampered', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Markdown hash mismatch'):
            pipeline.verify(staged)
        md.write_bytes(original)
        (staged / 'licenses' / f"{SOURCE['id']}.txt").write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'License hash mismatch'):
            pipeline.verify(staged)

    def test_changed_configuration_requires_recollection(self):
        self.collect_and_clean()
        changed = deepcopy(SOURCE)
        changed['publisher'] = 'Different publisher'
        with self.assertRaisesRegex(ValueError, 'configuration changed'):
            pipeline.clean([changed], self.root)

    def test_redirects_and_deprecated_pages_do_not_become_teaching_content(self):
        archive = self.root / 'raw' / '_archives' / f"{SOURCE['id']}-{SOURCE['commit']}.zip"
        with zipfile.ZipFile(archive, 'a') as output:
            output.writestr('repo/docs/redirect.md',
                            '# Old topic\n\nThis content has been merged into: [New](new.md).\n')
            output.writestr('repo/docs/deprecated.md', '# DEPRECATED: Old topic\n\n' + DOCUMENT)
        self.collect_and_clean()
        report = pipeline.read_json(self.root / 'staged' / 'quality_report.json')
        self.assertEqual(report['accepted'], 1)
        self.assertEqual(sum(r['reason'] == 'redirect_or_retired' for r in report['rejected']), 2)

    def test_zip_traversal_cannot_write_outside_raw_directory(self):
        archive = self.root / 'raw' / '_archives' / f"{SOURCE['id']}-{SOURCE['commit']}.zip"
        with zipfile.ZipFile(archive, 'a') as output:
            output.writestr('repo/docs/../../escaped.md', DOCUMENT)
        with self.assertRaisesRegex(ValueError, 'Unsafe relative path'):
            with self.quiet:
                pipeline.collect(SOURCE, self.root)
        self.assertFalse((self.root / 'escaped.md').exists())


if __name__ == '__main__':
    unittest.main()
