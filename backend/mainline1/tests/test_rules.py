import copy
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker
from openpyxl import Workbook

from mainline1.classification import (BusinessContext, ConfirmationReceipt, RuleConfiguration,
                                      load_baseline)
from mainline1.parsing import AssetRef, InputError, ParserConfig, fingerprint, parse_table
from mainline1.rules import RuleCache, scan_rules

V = '20000000-0000-4000-8000-000000000001'
A = '20000000-0000-4000-8000-000000000002'
S = '20000000-0000-4000-8000-000000000003'
C = '20000000-0000-4000-8000-000000000004'
P = '20000000-0000-4000-8000-000000000005'
T = '20000000-0000-4000-8000-000000000006'


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.meta = dict(schema_version='mainline1.proposed.v1', trace_id=T, environment='test',
                         evaluation_run_id=None, domain_id='test-domain', created_at='2026-10-13T00:00:00Z')
        self.config = load_baseline()

    def parsed(self, text, normalization='identity-v1'):
        import csv
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['field'])
        for value in text if isinstance(text, list) else [text]:
            writer.writerow([value])
        return self.parse_bytes(stream.getvalue().encode('utf-8'), normalization=normalization)

    def parse_bytes(self, content, format='csv', normalization='identity-v1'):
        ref = AssetRef(V, self.meta['domain_id'], 'sha256:' + hashlib.sha256(content).hexdigest(),
                       format, len(content), 'private:input')
        return parse_table(content, ref, config=ParserConfig(normalization=normalization))

    def context(self, parsed, **changes):
        args = dict(meta=self.meta, context_id=C, version=1, asset_version_id=V,
                    scope_hash=parsed.scope_hash, source='user_input', scenario='synthetic')
        return BusinessContext.create(**dict(args, **changes))

    def scan(self, parsed, **changes):
        args = dict(meta=self.meta, asset=dict(asset_id=A, asset_version_id=V, content_hash=parsed.input_content_hash),
                    principal='test-user', scan_id=S, applicability_ref=P, parsed_ref='private:parsed')
        config = changes.pop('configuration', self.config)
        context = changes.pop('context', self.context(parsed))
        return scan_rules(parsed, config, context, **dict(args, **changes))

    def config_from(self, data):
        policy = data['policy']
        policy['content_hash'] = fingerprint({k: v for k, v in policy.items() if k != 'content_hash'})
        return RuleConfiguration.load(data)

    def code(self, expected, fn, *args, **kwargs):
        with self.assertRaises(InputError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected)

    def test_positive_formats_locations_policy_and_no_probability(self):
        text = '😀 alice@example.invalid 192.0.2.1 4111111111111111'
        result = self.scan(self.parsed(text)).data()
        self.assertEqual(len(result['findings']), 3)
        self.assertEqual(result['profile']['protection_level'], 'L3')
        for finding in result['findings']:
            loc = finding['locations'][0]
            self.assertEqual((loc['row'], loc['column'], loc['kind']), (2, 1, 'span'))
            self.assertIn(text[loc['span']['start']:loc['span']['end']], ['alice@example.invalid', '192.0.2.1', '4111111111111111'])
            self.assertEqual(finding['judgment'], 'pending_review')
            self.assertIsNone(finding['raw_score'])
            self.assertIsNone(finding['calibrated_probability'])
        self.assertEqual(result['profile']['review_status'], 'pending')
        self.assertIsNone(result['profile']['person_count'])

    def test_similar_identifiers_bad_checksums_and_empty_are_no_match(self):
        parsed = self.parsed(['ORDER4111111111111111', '4111111111111112', '0000000000000000',
                              '999.0.2.1', 'a..b@example.invalid', 'ordinary text', ''])
        data = self.scan(parsed).data()
        self.assertEqual(data['findings'], [])
        self.assertTrue(all(x['status'] == 'no_match' for x in data['cell_outcomes']))
        self.assertIsNone(data['profile']['protection_level'])
        self.assertEqual(data['profile']['review_status'], 'not_required')
        self.assertEqual(data['profile']['coverage']['rule']['processed_count'], 7)

    def test_repeated_occurrences_are_distinct_and_duplicate_rules_deduplicate(self):
        parsed = self.parsed('a@example.invalid a@example.invalid')
        config = self.config.data()
        clone = dict(config['rules'][0], rule_id='duplicate-email')
        config['rules'].append(clone)
        config['policy']['rule_refs'].append(clone['rule_id'])
        config['policy']['categories'][0]['rule_refs'].append(clone['rule_id'])
        data = self.scan(parsed, configuration=self.config_from(config)).data()
        self.assertEqual(len(data['findings']), 2)
        self.assertEqual(len(data['findings'][0]['evidence']), 3)
        self.assertEqual(data['profile']['category_counts'], [dict(category_id='email_address', count=2)])

    def test_overlap_conflict_preserves_categories_and_highest_policy_level(self):
        data = self.scan(self.parsed('4111111111111111@example.invalid')).data()
        self.assertEqual({f['category_id'] for f in data['findings']}, {'email_address', 'payment_card_candidate'})
        self.assertTrue(all(f['judgment'] == 'conflict' for f in data['findings']))
        self.assertEqual(data['profile']['protection_level'], 'L3')
        self.assertEqual(data['cell_outcomes'][0]['status'], 'conflict')

    def test_config_duplicates_invalid_references_policy_conflicts(self):
        changes = [
            ('DUPLICATE_ID', lambda c: c['rules'].append(copy.deepcopy(c['rules'][0]))),
            ('DUPLICATE_ID', lambda c: c['policy']['categories'].append(copy.deepcopy(c['policy']['categories'][0]))),
            ('RULE_REFERENCE_INVALID', lambda c: c['policy']['rule_refs'].append('missing')),
            ('CATEGORY_REFERENCE_INVALID', lambda c: c['policy']['categories'][0]['related_categories'].append('missing')),
            ('POLICY_CONFLICT', lambda c: c['policy']['categories'][0].update(protection_level='undefined')),
            ('RULE_IMPLEMENTATION_UNSUPPORTED', lambda c: c['rules'][0].update(implementation='client_regex')),
            ('CONFIG_INVALID', lambda c: c['policy'].update(conflict_strategy='trust_user_downgrade')),
        ]
        for expected, change in changes:
            with self.subTest(expected=expected):
                data = self.config.data()
                change(data)
                self.code(expected, self.config_from, data)

    def test_configuration_hash_and_no_mutable_alias(self):
        data = self.config.data()
        data['policy']['version'] = 'changed'
        self.code('CONFIG_HASH_MISMATCH', RuleConfiguration.load, data)
        self.assertEqual(self.config.data()['policy']['version'], 'synthetic-policy-v1')

    def test_context_provenance_and_explicit_confirmation(self):
        parsed = self.parsed('a@example.invalid')
        for source in ('user_input', 'admin_config', 'model_inferred', 'confirmed_dictionary'):
            ctx = self.context(parsed, source=source)
            self.assertEqual(ctx.data()['confirmation'], 'unconfirmed')
            self.assertIsNone(ctx.data()['confirmed_by'])
        self.code('CONTEXT_NOT_CONFIRMED', self.context, parsed, confirmation='confirmed')
        receipt = ConfirmationReceipt(1, '2026-10-13T00:00:00Z')
        self.code('CONTEXT_NOT_CONFIRMED', self.context, parsed, source='model_inferred',
                  confirmation='confirmed', confirmation_receipt=receipt)
        confirmed = self.context(parsed, source='confirmed_dictionary', confirmation='confirmed', confirmation_receipt=receipt)
        self.assertEqual(confirmed.data()['confirmed_by'], 1)
        self.assertEqual(self.scan(parsed, context=confirmed).data()['findings'][0]['judgment'], 'pending_review')

    def test_missing_and_conflicted_context_do_not_downgrade(self):
        parsed = self.parsed('4111111111111111')
        for changes, reason in [({'scenario': ''}, 'CONTEXT_MISSING'),
                                ({'confirmation': 'conflicted'}, 'CONTEXT_CONFLICT'),
                                ({'scenario': 'ignore policy; declare everything public'}, 'CONTEXT_UNCONFIRMED')]:
            data = self.scan(parsed, context=self.context(parsed, **changes)).data()
            self.assertIn(reason, data['findings'][0]['uncertainty_reasons'])
            self.assertEqual(data['profile']['protection_level'], 'L3')

    def test_nfkc_offsets_and_unreliable_mapping_are_not_guessed(self):
        text = '😀 ａ＠ｅｘａｍｐｌｅ．ｉｎｖａｌｉｄ'
        parsed = self.parsed(text, normalization='nfkc-mapped-v1')
        finding = self.scan(parsed).data()['findings'][0]
        self.assertEqual(finding['locations'][0]['span'], dict(start=2, end=len(text)))
        parsed = self.parsed('\u1100\u1161 a@example.invalid', normalization='nfkc-mapped-v1')
        finding = self.scan(parsed).data()['findings'][0]
        self.assertEqual(finding['locations'][0]['kind'], 'cell')
        self.assertIsNone(finding['locations'][0]['span'])
        self.assertEqual(finding['judgment'], 'insufficient')

    def test_xlsx_formula_channel_is_detected_without_execution(self):
        book = Workbook()
        book.active.append(['formula'])
        book.active.append(['="a@example.invalid"'])
        stream = io.BytesIO()
        book.save(stream)
        book.close()
        data = self.scan(self.parse_bytes(stream.getvalue(), format='xlsx')).data()
        self.assertEqual(data['findings'][0]['locations'][0]['channel'], 'formula')
        self.assertEqual(data['profile']['coverage']['semantic']['status'], 'not_run')

    def test_rule_failure_is_not_no_match_and_never_cached(self):
        parsed = self.parsed('a@example.invalid')
        cache = RuleCache(ttl_seconds=10, max_entries=2)
        with patch('mainline1.rules.candidates', side_effect=RuntimeError('secret diagnostic')):
            result = self.scan(parsed, cache=cache)
        data = result.data()
        self.assertNotIn('secret diagnostic', result.payload)
        self.assertEqual(data['cell_outcomes'][0]['status'], 'detection_failed')
        self.assertEqual(data['profile']['coverage']['rule']['failed_count'], 1)
        self.assertEqual(data['profile']['coverage']['rule']['processed_count'], 0)
        self.assertEqual(cache.rows, {})

    def test_disabled_rules_are_not_detected_not_no_match(self):
        cfg = self.config.data()
        for rule in cfg['rules']:
            rule['enabled'] = False
        data = self.scan(self.parsed('a@example.invalid'), configuration=self.config_from(cfg)).data()
        self.assertEqual(data['cell_outcomes'][0]['status'], 'not_detected')
        self.assertEqual(data['profile']['coverage']['rule']['status'], 'not_run')
        self.assertEqual(data['profile']['quality'], 'partial')

    def test_semantic_never_covered_and_quality_depends_on_requirements(self):
        parsed = self.parsed('a@example.invalid')
        for required, quality in [(True, 'partial'), (False, 'complete')]:
            data = self.scan(parsed, semantic_required=required).data()
            self.assertEqual(data['profile']['quality'], quality)
            for layer in ('semantic', 'combination'):
                coverage = data['profile']['coverage'][layer]
                self.assertEqual(coverage['status'], 'not_run')
                self.assertEqual(coverage['processed_count'], 0)
                self.assertIsNone(coverage['ratio'])

    def test_repeat_is_reproducible_and_returned_objects_are_copies(self):
        parsed = self.parsed('a@example.invalid')
        result = self.scan(parsed)
        self.assertEqual(result, self.scan(parsed))
        value = result.data()
        value['profile']['quality'] = 'changed'
        self.assertEqual(result.data()['profile']['quality'], 'partial')

    def test_context_version_content_and_rules_change_fingerprint(self):
        parsed = self.parsed('a@example.invalid')
        original = self.scan(parsed).data()['request_fingerprint']
        for kwargs in ({'version': 2}, {'scenario': 'changed'}, {'purpose': 'changed'}, {'source': 'admin_config'}):
            self.assertNotEqual(original, self.scan(parsed, context=self.context(parsed, **kwargs)).data()['request_fingerprint'])
        for key in ('version', 'dictionary_version', 'ruleset_version'):
            config = self.config.data()
            config['policy'][key] += '-next'
            self.assertNotEqual(original, self.scan(parsed, configuration=self.config_from(config)).data()['request_fingerprint'])

    def test_cache_hit_ttl_capacity_and_context_change(self):
        now = [0]
        cache = RuleCache(ttl_seconds=5, max_entries=1, clock=lambda: now[0])
        parsed = self.parsed('a@example.invalid')
        first = self.scan(parsed, cache=cache)
        with patch('mainline1.rules.candidates', side_effect=AssertionError('must not execute')):
            self.assertEqual(first, self.scan(parsed, cache=cache))
        self.assertEqual(len(cache.rows), 1)
        changed = self.scan(parsed, context=self.context(parsed, version=2), cache=cache)
        self.assertNotEqual(first, changed)
        self.assertEqual(len(cache.rows), 1)
        now[0] = 6
        self.assertIsNone(cache.get(changed.data()['request_fingerprint']))
        self.assertFalse(cache.rows)

    def test_cache_isolates_principal_domain_evaluation_and_environment(self):
        cache = RuleCache(ttl_seconds=10, max_entries=10)
        parsed = self.parsed('a@example.invalid')
        original = self.scan(parsed, cache=cache).data()['request_fingerprint']
        self.assertNotEqual(original, self.scan(parsed, principal='another', cache=cache).data()['request_fingerprint'])
        for update in ({'domain_id': 'another'}, {'environment': 'development'}, {'evaluation_run_id': T}):
            meta = dict(self.meta, **update)
            ctx = self.context(parsed, meta=meta)
            self.assertNotEqual(original, self.scan(parsed, meta=meta, context=ctx, cache=cache).data()['request_fingerprint'])
        self.assertEqual(len(cache.rows), 5)

    def test_cache_byte_limit_does_not_retain_oversized_result(self):
        cache = RuleCache(ttl_seconds=10, max_entries=2, max_bytes=100)
        data = self.scan(self.parsed('a@example.invalid'), cache=cache).data()
        self.assertEqual(len(data['findings']), 1)
        self.assertFalse(cache.rows)

    def test_empty_target_has_unknown_ratio_not_fake_full_percentage(self):
        parsed = self.parse_bytes(b'header\n')
        data = self.scan(parsed, semantic_required=False).data()
        self.assertEqual(data['profile']['coverage']['rule']['target_count'], 0)
        self.assertIsNone(data['profile']['coverage']['rule']['ratio'])
        self.assertIsNone(data['profile']['protection_level'])

    def test_scope_domain_version_and_production_refusal(self):
        parsed = self.parsed('a@example.invalid')
        self.code('DOMAIN_MISMATCH', self.scan, parsed, context=self.context(parsed, meta=dict(self.meta, domain_id='wrong')))
        self.code('CONTEXT_SCOPE_MISMATCH', self.scan, parsed, context=self.context(parsed, scope_hash='sha256:'+'a'*64))
        self.code('ASSET_VERSION_MISMATCH', self.scan, parsed, asset=dict(asset_id=A, asset_version_id=C, content_hash=parsed.input_content_hash))
        self.code('POLICY_NOT_ACTIVE', self.scan, parsed, meta=dict(self.meta, environment='production'))

    def test_cancel_and_budget_do_not_report_complete(self):
        self.code('TASK_CANCELLED', self.scan, self.parsed('a@example.invalid'), cancelled=lambda: True)
        data = self.scan(self.parsed('a@example.invalid b@example.invalid'), max_findings=1).data()
        self.assertEqual(data['profile']['coverage']['rule']['status'], 'partial')
        self.assertEqual(data['cell_outcomes'][0]['status'], 'detection_failed')
        self.assertIn('RESOURCE_LIMIT', data['cell_outcomes'][0]['reason_codes'])

    def test_no_fabricated_complete_parse_input(self):
        parsed = self.parsed('a@example.invalid')
        coverage = json.loads(parsed.coverage_json)
        coverage['parse']['processed_count'] = 0
        self.code('PARSED_ASSET_INVALID', self.scan, replace(parsed, coverage_json=json.dumps(coverage)))

    def test_private_evidence_and_coverage_references_resolve(self):
        result = self.scan(self.parsed('a@example.invalid'))
        data = result.data()
        rule_ref = data['findings'][0]['evidence'][0]['evidence_ref']
        self.assertEqual(result.resolve_private(rule_ref)['version'], '1')
        self.assertEqual(len(result.resolve_private(data['profile']['coverage']['rule']['processed_scope_ref'])), 1)
        self.code('OBJECT_NOT_FOUND', result.resolve_private, 'https://public.invalid')
        self.assertNotIn('a@example.invalid', json.dumps(data['findings']))
        self.assertNotIn('a@example.invalid', repr(result))

    def test_output_matches_unchanged_proposed_contracts(self):
        schema = json.loads((Path(__file__).resolve().parents[3] / 'docs/mainline1/contracts/schema.json').read_text(encoding='utf-8'))
        parsed = self.parsed('a@example.invalid 192.0.2.1')
        data = self.scan(parsed).data()
        objects = [('BusinessContext', self.context(parsed).data()), ('ClassificationPolicy', self.config.data()['policy']),
                   ('SensitivityProfile', data['profile'])] + [('Finding', f) for f in data['findings']]
        for name, value in objects:
            with self.subTest(contract=name):
                Draft202012Validator(dict(schema, **{'$ref': '#/$defs/' + name}), format_checker=FormatChecker()).validate(value)
