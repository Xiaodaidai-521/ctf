"""Frozen byte contracts for the old, unauthenticated audit chain."""
import ast
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import unittest

from .legacy_hashes import canonical_json, sha256_hex, compute_payload_hash, compute_entry_hash


class LegacyHashTests(unittest.TestCase):
    def test_canonical_unicode_order_and_default_string_are_unchanged(self):
        value = {'z': '合成', 'at': datetime(2026, 11, 10, tzinfo=timezone.utc), 'a': [1, None]}
        expected = '{"a":[1,null],"at":"2026-11-10 00:00:00+00:00","z":"合成"}'
        self.assertEqual(canonical_json(value), expected)
        self.assertEqual(compute_payload_hash(value), hashlib.sha256(expected.encode('utf-8')).hexdigest())

    def test_falsy_payload_and_utf8_digest_keep_the_v1_contract(self):
        self.assertEqual(canonical_json(None), '{}')
        self.assertEqual(compute_payload_hash({}), '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a')
        self.assertEqual(sha256_hex('合成'), hashlib.sha256('合成'.encode('utf-8')).hexdigest())

    def test_entry_preimage_keeps_genesis_and_legacy_object_id_normalization(self):
        expected = ('{"actor_id":null,"chain_version":"v1","event_category":"fixture",'
                    '"object_id":"","object_type":"","payload_hash":"payload",'
                    '"previous_hash":"' + '0' * 64 + '"}')
        value = compute_entry_hash(previous_hash='', payload_hash='payload', event_category='fixture',
                                   object_type='', object_id=0, actor_id=None, chain_version='v1')
        self.assertEqual(value, hashlib.sha256(expected.encode('utf-8')).hexdigest())
        self.assertNotEqual(value, compute_entry_hash(previous_hash='prior', payload_hash='payload',
                            event_category='fixture', object_type='', object_id=0, actor_id=None, chain_version='v1'))

    def test_hash_module_only_imports_standard_library(self):
        source = Path(__file__).with_name('legacy_hashes.py')
        tree = ast.parse(source.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(alias.name in {'hashlib', 'json'} for alias in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.module, 'typing')
