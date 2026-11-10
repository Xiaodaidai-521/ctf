"""Synthetic marker scanning; no database, credentials, downloads or external tools."""
import base64
import gzip
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import zipfile

from tools.data_security.phase6_plaintext_scan import RUNTIME_CATEGORIES, scan_manifest


class PlaintextInventoryTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.markers = {'sample': 'b2-synthetic-original-marker'}
        self.manifest = {'schema_version': 'ds.b2-plaintext-scan.v1', 'scope': 'source-only',
            'targets': [{'category': 'production-source', 'path': str(self.root)}], 'max_expanded_bytes': 4 * 1024 * 1024}

    def test_hit_across_chunk_boundary_is_reported_without_value_or_snippet(self):
        value = self.markers['sample'].encode()
        (self.root / 'output.log').write_bytes(b'x' * (1024 * 1024 - 4) + value)
        result = scan_manifest(self.manifest, self.markers)
        self.assertTrue(result['complete'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['marker_hit_files'], 1)
        self.assertEqual(result['files'][0]['marker_ids'], ['sample'])
        self.assertNotIn(self.markers['sample'], json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_encoded_literals_and_filename_are_not_silently_ignored(self):
        value = self.markers['sample']
        (self.root / 'utf16.txt').write_bytes(value.encode('utf-16-le'))
        (self.root / 'base64.txt').write_bytes(base64.b64encode(value.encode()))
        (self.root / value).write_bytes(b'safe body')
        result = scan_manifest(self.manifest, self.markers)
        self.assertEqual(result['marker_hit_files'], 3)
        self.assertFalse(result['passed'])
        self.assertNotIn(value, json.dumps(result))

    def test_utf16_big_endian_and_json_escaped_originals_are_checked(self):
        self.markers = {'unicode': 'b2-合成原文-标记'}
        value = self.markers['unicode']
        (self.root / 'utf16-be.txt').write_bytes(value.encode('utf-16-be'))
        (self.root / 'escaped.json').write_text(json.dumps({'value': value}, ensure_ascii=True))
        result = scan_manifest(self.manifest, self.markers)
        self.assertTrue(result['complete'])
        self.assertEqual(result['marker_hit_files'], 2)
        self.assertNotIn(value, json.dumps(result, ensure_ascii=False))
        self.assertNotIn(json.dumps(value)[1:-1], json.dumps(result))

    def test_zip_and_gzip_members_are_scanned_without_extraction(self):
        value = self.markers['sample'].encode()
        with zipfile.ZipFile(self.root / 'table.xlsx', 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('xl/sharedStrings.xml', value)
        (self.root / 'log.gz').write_bytes(gzip.compress(value))
        before = sorted(path.name for path in self.root.iterdir())
        result = scan_manifest(self.manifest, self.markers)
        self.assertTrue(result['complete'])
        self.assertEqual(result['marker_hit_files'], 2)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), before)

    def test_visual_and_nested_encoded_content_remain_unscanned_even_with_zero_literal_hits(self):
        (self.root / 'image.bin').write_bytes(b'\x89PNG\r\n\x1a\nsynthetic pixels')
        nested = BytesIO()
        with zipfile.ZipFile(nested, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('member.txt', b'safe content')
        (self.root / 'nested.gz').write_bytes(gzip.compress(nested.getvalue()))
        with zipfile.ZipFile(self.root / 'outer.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('renamed.bin', nested.getvalue())
        result = scan_manifest(self.manifest, self.markers)
        self.assertFalse(result['complete'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['marker_hit_files'], 0)
        self.assertEqual(len(result['unscanned']), 3)

    def test_missing_category_missing_path_and_symlink_cannot_pass(self):
        runtime = {**self.manifest, 'scope': 'runtime'}
        self.assertFalse(scan_manifest(runtime, self.markers)['passed'])
        self.assertEqual(len(scan_manifest(runtime, self.markers)['missing_categories']), 8)
        (self.root / 'link').symlink_to(self.root / 'missing')
        result = scan_manifest(self.manifest, self.markers)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['unscanned']), 1)
        missing = {**self.manifest, 'targets': [{'category': 'production-source', 'path': str(self.root / 'absent')}]}
        self.assertFalse(scan_manifest(missing, self.markers)['passed'])

    def test_symlink_roots_and_noncanonical_targets_are_not_followed(self):
        directory = self.root / 'directory'
        directory.mkdir()
        link = self.root / 'linked-directory'
        link.symlink_to(directory, target_is_directory=True)
        for path in (link, directory / '..' / 'directory'):
            with self.subTest(path=path.name):
                manifest = {**self.manifest, 'targets': [{'category': 'production-source', 'path': str(path)}]}
                result = scan_manifest(manifest, self.markers)
                self.assertFalse(result['complete'])
                self.assertEqual(result['files'], [])
                self.assertEqual(result['unscanned'][0]['reason'], 'noncanonical-target')

    def test_runtime_categories_and_file_hashes_are_explicit_not_inferred(self):
        targets = []
        for category in sorted(RUNTIME_CATEGORIES):
            directory = self.root / category
            directory.mkdir()
            targets.append({'category': category, 'path': str(directory)})
        (self.root / 'private' / 'opaque.sealed').write_bytes(b'ciphertext-only-synthetic-fixture')
        runtime = {**self.manifest, 'scope': 'runtime', 'targets': targets}
        result = scan_manifest(runtime, self.markers)
        self.assertTrue(result['passed'])
        self.assertTrue(result['runtime_scope_verified'])
        self.assertTrue(result['declared_inventory_only'])
        self.assertEqual(len(result['files']), 1)
        self.assertEqual(len(result['files'][0]['sha256']), 64)
        source = scan_manifest(self.manifest, self.markers)
        self.assertFalse(source['runtime_scope_verified'])

    def test_corrupt_or_over_budget_archive_is_incomplete_not_a_zero_hit_success(self):
        (self.root / 'bad.zip').write_bytes(b'not a valid archive')
        with zipfile.ZipFile(self.root / 'large.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('text.txt', b'x' * 101)
        result = scan_manifest({**self.manifest, 'max_expanded_bytes': 100}, self.markers)
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['unscanned']), 2)

    def test_gzip_expansion_and_pdf_members_are_not_counted_as_complete(self):
        (self.root / 'large.gz').write_bytes(gzip.compress(b'x' * 101))
        with zipfile.ZipFile(self.root / 'document.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('document.pdf', b'%PDF-synthetic opaque content')
        result = scan_manifest({**self.manifest, 'max_expanded_bytes': 100}, self.markers)
        self.assertFalse(result['complete'])
        self.assertEqual(result['marker_hit_files'], 0)
        self.assertEqual(len(result['unscanned']), 2)
        self.assertNotIn('document.pdf', json.dumps(result))

    def test_marker_and_target_configuration_are_validated_without_echoing_values(self):
        for markers in ({}, {'bad-id/': self.markers['sample']}, {'short': 'tiny'}):
            with self.assertRaisesRegex(ValueError, '^invalid-marker'):
                scan_manifest(self.manifest, markers)
        invalid = {**self.manifest, 'targets': [{'category': 'private', 'path': 'relative'}]}
        with self.assertRaisesRegex(ValueError, '^absolute-target-required$'):
            scan_manifest(invalid, self.markers)
