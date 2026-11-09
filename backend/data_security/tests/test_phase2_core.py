from dataclasses import replace
from datetime import timedelta
import unittest

from data_security.contracts import *
from data_security.tests.phase2_fixtures import *
from data_security.tests.synthetic import samples
from data_security.core import crypto, redaction


class CryptoCoreTests(unittest.TestCase):
    def test_public_aes256_gcm_nist_vectors(self):
        key, nonce = bytes(32), bytes(12)
        empty = bytes.fromhex('530f8afbc74536b9a963b4f1c4cb738b')
        block = bytes.fromhex('cea7403d4d606b6e074ec5d3baf39d18d0d1c8a799996bf0265b98b5d48ab919')
        self.assertEqual(crypto.aes_gcm_seal(key, nonce, b'', b''), empty)
        self.assertEqual(crypto.aes_gcm_seal(key, nonce, bytes(16), b''), block)
        self.assertEqual(crypto.aes_gcm_open(key, nonce, block, b''), bytes(16))

    def test_public_rfc5869_and_rfc4231_vectors(self):
        result = crypto.hkdf_sha256(bytes([11]) * 22, bytes(range(13)), bytes(range(240, 250)), length=42)
        self.assertEqual(result.hex(), '3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865')
        mac = crypto.hmac_sha256(bytes([11]) * 20, b'Hi There')
        self.assertEqual(mac.hex(), 'b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7')
        self.assertTrue(crypto.compare_authentication(mac, mac))
        self.assertFalse(crypto.compare_authentication(mac, bytes(32)))

    def test_envelope_round_trip_determinism_and_read_only_key(self):
        obj, key = examples()[ObjectContext], reference_key()
        envelope = crypto.seal(b'', obj, key, root_key(), salt=bytes(16), nonce=bytes(12))
        self.assertEqual(crypto.open_envelope(envelope, obj, replace(key, status=KeyStatus.READ_ONLY), root_key()), b'')
        self.assertEqual(envelope, crypto.seal(b'', obj, key, root_key(), salt=bytes(16), nonce=bytes(12)))
        self.assertEqual(len(envelope.ciphertext_and_tag), 16)
        self.assertNotIn(b'wrapped', canonical_bytes(envelope))
        self.assertEqual(CipherEnvelope.from_json(canonical_bytes(envelope)), envelope)
        self.assertEqual(crypto.open_envelope(envelope, replace(obj, authorization_ref='authorization/renewed'), key, root_key()), b'')

    def test_all_tampering_and_cross_context_copy_fail_closed(self):
        obj, key = examples()[ObjectContext], reference_key()
        envelope = crypto.seal(b'synthetic content', obj, key, root_key(), salt=bytes(16), nonce=bytes(12))
        flip = lambda value: bytes([value[0] ^ 1]) + value[1:]
        cases = [(replace(envelope, nonce=flip(envelope.nonce)), obj, key, root_key()),
                 (replace(envelope, kdf_salt=flip(envelope.kdf_salt)), obj, key, root_key()),
                 (replace(envelope, ciphertext_and_tag=flip(envelope.ciphertext_and_tag)), obj, key, root_key()),
                 (replace(envelope, ciphertext_and_tag=envelope.ciphertext_and_tag[:-1] + bytes([envelope.ciphertext_and_tag[-1] ^ 1])), obj, key, root_key()),
                 (envelope, obj, key, root_key('other'))]
        for name, value in (('project_ref', 'project/other'), ('environment', Environment.EVALUATION),
            ('object_uuid', '00000000-0000-4000-8000-000000000002'), ('field_ref', 'document/title'), ('object_version', 'v2')):
            cases.append((envelope, replace(obj, **{name: value}), key, root_key()))
        cases.append((envelope, obj, replace(key, version='v2', key_ref='enc-data/v2'), root_key()))
        for env, ctx, ref, material in cases:
            with self.assertRaises(ContractViolation):
                crypto.open_envelope(env, ctx, ref, material)
        with self.assertRaises(ContractViolation):
            replace(envelope, format_version='legacy')
        with self.assertRaises(ContractViolation):
            replace(envelope, ciphertext_and_tag=b'')

    def test_invalid_key_nonce_sizes_and_lifecycle(self):
        for size in (0, 16, 24, 31, 33):
            with self.assertRaises(ContractViolation):
                crypto.aes_gcm_seal(bytes(size), bytes(12), b'', b'')
        for size in (0, 8, 11, 13, 16):
            with self.assertRaises(ContractViolation):
                crypto.aes_gcm_seal(bytes(32), bytes(size), b'', b'')
        for status in (KeyStatus.READ_ONLY, KeyStatus.RETIRED):
            with self.assertRaises(ContractViolation):
                crypto.seal(b'', examples()[ObjectContext], reference_key(status=status), root_key(), salt=bytes(16), nonce=bytes(12))

    def test_stable_hmac_domain_purpose_scope_and_environment_separation(self):
        def mac(purpose=KeyPurpose.LINK, env=Environment.TEST, domain='domain/a', scope='field/a'):
            return crypto.scoped_hmac(b'value', root_key(), reference_key(purpose), environment=env, domain=domain, scope=scope)
        self.assertEqual(mac(), mac())
        self.assertEqual(len({mac(), mac(KeyPurpose.PSEUDONYM), mac(KeyPurpose.INDEX), mac(KeyPurpose.AUDIT),
                              mac(env=Environment.EVALUATION), mac(domain='domain/b'), mac(scope='field/b')}), 7)


class RedactionCoreTests(unittest.TestCase):
    def test_three_category_dataset_positive_negative_and_no_new_detector(self):
        positives = negatives = 0
        for case in samples():
            if case.category is Category.SECRET or case.teaching is not None:
                continue
            found = redaction.detect(text(case.text), BASELINE_LIMITS)
            self.assertIsInstance(found, tuple)
            self.assertEqual(any(f.category is case.category for f in found), case.positive)
            positives += case.positive
            negatives += not case.positive
        self.assertEqual((positives, negatives), (150, 150))
        self.assertFalse(redaction.detect(text('token=' + root_key().hex()), BASELINE_LIMITS))
        self.assertEqual(set(redaction.LEVELS), set(Category))  # SECRET can be supplied explicitly, not detected.

    def test_unicode_source_coordinates_and_same_snapshot_actions(self):
        value = '🙂 a@example.invalid / b@example.invalid.'
        found = redaction.detect(text(value), BASELINE_LIMITS)
        self.assertEqual([(f.location.start, f.location.end) for f in found], [(2, 19), (22, 39)])
        from data_security.core.policy import resolve_actions
        snap, binding = policy(context())
        actions = resolve_actions(
            snap, context(), found, binding, at=AT, field_ref='content/body')
        result = redaction.apply_actions(text(value), actions, BASELINE_LIMITS)
        self.assertEqual(result.text, '🙂 [REDACTED] / [REDACTED].')
        self.assertEqual(value, '🙂 a@example.invalid / b@example.invalid.')

    def test_overlap_union_priority_and_order_independence(self):
        source = text('abcdefghijklmnop')
        lower = action(Category.EMAIL, algorithm(Algorithm.MASK, keep_prefix=2, keep_suffix=2, mask_symbol='*'), start=0, end=10)
        higher = action(Category.SECRET, algorithm(replacement=Replacement.SECRET), start=8, end=16, number=1)
        for order in ((lower, higher), (higher, lower)):
            result = redaction.apply_actions(source, order, BASELINE_LIMITS)
            self.assertEqual(result.text, '[SECRET]')
        adjacent = action(start=10, end=16, number=2)
        result = redaction.apply_actions(source, (action(start=0, end=10), adjacent), BASELINE_LIMITS)
        self.assertEqual(result.text, '[REDACTED][REDACTED]')

    def test_algorithms_and_l3_floor(self):
        self.assertEqual(redaction.transform('abc', algorithm(Algorithm.DROP), Category.EMAIL), '')
        self.assertEqual(redaction.transform('abcdef', algorithm(Algorithm.MASK, keep_prefix=1, keep_suffix=1, mask_symbol='*'), Category.EMAIL), 'a****f')
        self.assertEqual(redaction.transform('a', algorithm(Algorithm.MASK, keep_prefix=64, keep_suffix=64, mask_symbol='*'), Category.EMAIL), '*')
        self.assertEqual(redaction.transform('192.0.2.91', algorithm(Algorithm.GENERALIZE, ipv4_prefix=24), Category.IPV4), '192.0.2.0/24')
        for category in (Category.CARD, Category.SECRET):
            for spec in (algorithm(Algorithm.MASK, keep_prefix=0, keep_suffix=0, mask_symbol='*'),
                         algorithm(Algorithm.TRUNCATE, max_length=1), algorithm(Algorithm.GENERALIZE, ipv4_prefix=24)):
                with self.assertRaises(ContractViolation):
                    redaction.transform('value', spec, category)
        for category in Category:
            with self.assertRaises(ContractViolation):
                redaction.transform('value', algorithm(Algorithm.TRUNCATE, max_length=1), category)
        with self.assertRaises(ContractViolation):
            algorithm(Algorithm.PSEUDONYM, key_ref='mask-pseudonym/v1', pseudonym_bits=32)
        with self.assertRaises(ContractViolation):
            algorithm(Algorithm.GENERALIZE, ipv4_prefix=16)

    def test_hmac_and_pseudonym_keep_at_least_128_bits(self):
        for kind, purpose in ((Algorithm.HMAC, KeyPurpose.LINK), (Algorithm.PSEUDONYM, KeyPurpose.PSEUDONYM)):
            spec = algorithm(kind, key_ref=purpose.value + '/v1', **({'pseudonym_bits': 128} if kind is Algorithm.PSEUDONYM else {}))
            kwargs = dict(material=(reference_key(purpose), root_key()), environment=Environment.TEST, domain='domain/test', scope='field/test')
            result = redaction.transform('value', spec, Category.CARD, **kwargs)
            self.assertEqual(result, redaction.transform('value', spec, Category.CARD, **kwargs))
            self.assertEqual(len(result), 64 if kind is Algorithm.HMAC else 22)
            with self.assertRaises(ContractViolation):
                redaction.transform('value', spec, Category.CARD)
            with self.assertRaises(ContractViolation):
                redaction.transform('value', spec, Category.SECRET, **kwargs)

    def test_protect_before_truncate_and_no_l3_tail(self):
        value = 'prefix-' + root_key().hex()
        result = redaction.apply_actions(text(value), (action(Category.SECRET, start=7, end=len(value)),),
            BASELINE_LIMITS, truncate=algorithm(Algorithm.TRUNCATE, max_length=12))
        self.assertEqual(result.text, 'prefix-[REDA')
        self.assertNotIn(value[7:12], result.text)

    def test_nested_json_drop_and_field_replace_use_original_indices(self):
        value = {'safe': True, 'rows': ['a@example.invalid', 'b@example.invalid', 'keep'], 'n': None}
        found = redaction.detect(tree(value), BASELINE_LIMITS)
        self.assertEqual(len(found), 2)
        actions = (action(spec=algorithm(Algorithm.DROP), path=('rows', 0)),
                   action(path=('rows', 1), number=1))
        result = redaction.apply_actions(tree(value), actions, BASELINE_LIMITS).tree.to_value()
        self.assertEqual(result, {'safe': True, 'rows': ['[REDACTED]', 'keep'], 'n': None})
        self.assertEqual(value['rows'][0], 'a@example.invalid')
        bad = redaction.detect(tree({'a@example.invalid': 'safe'}), BASELINE_LIMITS)
        self.assertIsInstance(bad, ProtectionError)
        with self.assertRaises(ContractViolation):
            redaction.apply_actions(tree(value), (action(path=('missing',)),), BASELINE_LIMITS)

    def test_json_limits_findings_actions_and_binary_fail_closed(self):
        for limits, value in ((replace(BASELINE_LIMITS, max_json_depth=1), {'x': {'y': 'a'}}),
                              (replace(BASELINE_LIMITS, max_json_nodes=2), ['a', 'b']),
                              (replace(BASELINE_LIMITS, max_json_fields=1), {'a': 1, 'b': 2}),
                              (replace(BASELINE_LIMITS, max_text_chars=2), {'a': 'abc'}),
                              (replace(BASELINE_LIMITS, max_json_bytes=4), {'x': 1})):
            result = redaction.detect(tree(value), limits)
            self.assertIsInstance(result, ProtectionError)
        two = text('a@example.invalid b@example.invalid')
        self.assertIsInstance(redaction.detect(two, replace(BASELINE_LIMITS, max_findings=1)), ProtectionError)
        with self.assertRaises(ContractViolation):
            redaction.apply_actions(two, (action(), action(number=1)), replace(BASELINE_LIMITS, max_actions=1))
        binary = dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.BINARY,
                     text=None, tree=None, binary=b'data', limits=BASELINE_LIMITS)
        self.assertEqual(redaction.detect(binary, BASELINE_LIMITS).code, ReasonCode.UNSUPPORTED_FORMAT)

    def test_table_mapping_and_unproven_upgrade_or_rejection(self):
        fixture = examples()[TableSnapshot]
        value = 'a@example.invalid'
        cell = replace(fixture.cells[0], original_text='🙂' + value, normalized_text=value,
                       source_spans=tuple((i + 1, i + 2) for i in range(len(value))))
        table = replace(fixture, cells=(cell,))
        found = redaction.detect_table(table, BASELINE_LIMITS)
        self.assertEqual((found[0].location.start, found[0].location.end), (1, len(value) + 1))
        snap, binding = policy()
        from data_security.core.policy import resolve_actions
        actions = resolve_actions(snap, context(), found, binding, at=AT, field_ref='content/body')
        result = redaction.apply_actions(table, actions, BASELINE_LIMITS)
        self.assertEqual(result.cells[0].original_text, '🙂[REDACTED]')
        unproven = replace(table, cells=(replace(cell, mapping_proven=False, source_spans=()),))
        found = redaction.detect_table(unproven, BASELINE_LIMITS)
        self.assertIs(found[0].location.kind, LocationKind.CELL)
        result = redaction.apply_actions(unproven, resolve_actions(snap, context(), found, binding, at=AT,
            field_ref='content/body'), BASELINE_LIMITS)
        self.assertEqual(result.cells[0].original_text, '[REDACTED]')
        masked, binding = policy(specs={Category.EMAIL: algorithm(Algorithm.MASK, keep_prefix=1, keep_suffix=1, mask_symbol='*')})
        with self.assertRaises(ContractViolation):
            resolve_actions(masked, context(), found, binding, at=AT, field_ref='content/body')
        with self.assertRaises(ContractViolation):
            redaction.detect_table(table, replace(BASELINE_LIMITS, max_rows=1))
        with self.assertRaises(ContractViolation):
            redaction.detect_table(replace(table, coverage=replace(table.coverage, processed=0, unknown=1)), BASELINE_LIMITS)

    def test_table_drop_all_columns_and_invalid_spans_rejected(self):
        table = examples()[TableSnapshot]
        loc = dto(Location, kind=LocationKind.COLUMN, sheet_id='csv:0', column_id='column:1', source_row=None,
                  start=None, end=None, json_path=())
        drop = replace(action(spec=algorithm(Algorithm.DROP)), location=loc)
        with self.assertRaises(ContractViolation):
            redaction.apply_actions(table, (drop,), BASELINE_LIMITS)
        with self.assertRaises(ContractViolation):
            redaction.apply_actions(text('a'), (action(end=2),), BASELINE_LIMITS)


class ReviewRegressionTests(unittest.TestCase):
    def test_whole_field_strength_is_independent_of_action_ids(self):
        mask = action(spec=algorithm(Algorithm.MASK, keep_prefix=2, keep_suffix=1, mask_symbol='*'), path=('x',))
        replacement = action(path=('x',), number=1)
        for first, second in ((mask, replacement), (replace(mask, action_id='action/1'),
                                                   replace(replacement, action_id='action/0'))):
            result = redaction.apply_actions(tree({'x': 'abcdef'}), (first, second), BASELINE_LIMITS)
            self.assertEqual(result.tree.to_value(), {'x': '[REDACTED]'})

    def test_json_root_span_drop_has_same_coordinates_as_text(self):
        drop = action(spec=algorithm(Algorithm.DROP), start=1, end=2)
        self.assertEqual(redaction.apply_actions(tree('abcde'), (drop,), BASELINE_LIMITS).tree.to_value(), 'acde')
        with self.assertRaises(ContractViolation):
            redaction.apply_actions(tree('abcde'), (replace(drop, location=replace(drop.location, start=50, end=60)),), BASELINE_LIMITS)

    def test_truncate_cannot_shorten_pseudonym_or_hmac_container(self):
        for name, purpose in ((Algorithm.PSEUDONYM, KeyPurpose.PSEUDONYM), (Algorithm.HMAC, KeyPurpose.LINK)):
            spec = algorithm(name, key_ref=purpose.value + '/v1', **({'pseudonym_bits': 128} if name is Algorithm.PSEUDONYM else {}))
            kwargs = dict(materials=((reference_key(purpose), root_key()),), environment=Environment.TEST,
                          domain='domain/test', scope='field/test', truncate=algorithm(Algorithm.TRUNCATE, max_length=4))
            for payload, selected in ((text('abcde'), action(spec=spec)),
                                      (tree({'x': 'abcde'}), action(spec=spec, path=('x',)))):
                with self.assertRaises(ContractViolation):
                    redaction.apply_actions(payload, (selected,), BASELINE_LIMITS, **kwargs)

    def test_existing_credential_match_removes_complete_value(self):
        from data_security.adapters.django.legacy import LEGACY_INTERNAL, LEGACY_SECRET, LEGACY_TOKEN
        marker = root_key().hex()
        for profile, value in (('legal-v1', 'Authorization: Bearer ' + marker),
            ('legal-v1', 'cookie=part=' + marker + '; extra=' + marker),
            ('legal-v1', 'password="' + marker[:12] + ' ' + marker[12:] + '"'),
            ('output-v1', 'password=' + marker[:12] + './' + marker[12:]),
            ('output-v1', 'sk-' + marker[:48] + marker[48:])):
            output, _ = redaction.legacy_confidentiality(value, profile, secret_patterns=LEGACY_SECRET,
                token_pattern=LEGACY_TOKEN, internal_patterns=LEGACY_INTERNAL)
            self.assertNotIn(marker, output)
            self.assertNotIn(marker[-8:], output)

    def test_table_action_groups_preserve_coordinate_validation(self):
        table = examples()[TableSnapshot]
        template = table.cells[0]
        cells = tuple(replace(template, source_row=i + 1, logical_record=i + 1) for i in range(2000))
        table = replace(table, cells=cells, coverage=replace(table.coverage, total=2000, eligible=2000, processed=2000))
        loc = dto(Location, kind=LocationKind.CELL, sheet_id=template.sheet_id, column_id=template.column_id,
                  source_row=1, start=None, end=None, json_path=())
        actions = tuple(replace(action(number=i), location=replace(loc, source_row=i + 1)) for i in range(1000))
        result = redaction.apply_actions(table, actions, BASELINE_LIMITS)
        self.assertEqual(len(result.cells), 2000)
        self.assertEqual(sum(c.original_text == '[REDACTED]' for c in result.cells), 1000)
        with self.assertRaises(ContractViolation):
            redaction.apply_actions(table, (replace(actions[0], location=replace(loc, source_row=3000)),), BASELINE_LIMITS)


class PolicyCoreTests(unittest.TestCase):
    def test_exact_binding_status_expiry_role_purpose_and_authorization(self):
        from data_security.core.policy import resolve_actions, validate_snapshot
        snap, binding = policy()
        hits = redaction.detect(text('a@example.invalid'), BASELINE_LIMITS)
        actions = resolve_actions(snap, context(), hits, binding, at=AT, field_ref='content/body')
        self.assertEqual(actions, resolve_actions(snap, context(), hits, binding, at=AT, field_ref='content/body'))
        for invalid, stamp in ((replace(snap, status=PolicyStatus.RETIRED), AT),
            (replace(snap, status=PolicyStatus.DRAFT), AT), (snap, AT - timedelta(seconds=1)), (snap, snap.expires_at)):
            with self.assertRaises(ContractViolation):
                validate_snapshot(invalid, binding, at=stamp)
        with self.assertRaises(ContractViolation):
            validate_snapshot(snap, replace(binding, protection_hash=HASH), at=AT)
        for ctx in (replace(context(), role=Role.ADMIN), replace(context(), purpose=Purpose.ANALYSIS),
                    replace(context(), outlet=Outlet.MODEL), replace(context(), scope_refs=('unrelated/scope',))):
            with self.assertRaises(ContractViolation):
                resolve_actions(snap, ctx, hits, binding, at=AT, field_ref='content/body')

    def test_teaching_exact_source_field_outlet_purpose_and_expiry(self):
        from data_security.core.policy import resolve_actions
        ctx = replace(context(), purpose=Purpose.TEACHING, source_ref='fixture/published', source_version='v1', source_hash=HASH)
        exception = replace(examples()[TeachingException], field_refs=('content/endpoint',))
        snap, binding = policy(ctx, exceptions=(exception,))
        hits = redaction.detect(text('198.51.100.7'), BASELINE_LIMITS)
        ctx = replace(ctx, scope_refs=('content/endpoint',))
        self.assertEqual(resolve_actions(snap, ctx, hits, binding, at=AT, field_ref='content/endpoint'), ())
        for changed in (replace(ctx, source_ref=None, source_version=None, source_hash=None),
                        replace(ctx, source_version='v2'), replace(ctx, source_hash=content_hash({'other': True}))):
            self.assertEqual(len(resolve_actions(snap, changed, hits, binding, at=AT, field_ref='content/endpoint')), 1)
        nested = redaction.detect(tree({'content': '198.51.100.7'}), BASELINE_LIMITS)
        self.assertEqual(len(resolve_actions(snap, ctx, nested, binding, at=AT, field_ref='content/endpoint')), 1)
        table_hit = replace(hits[0], location=dto(Location, kind=LocationKind.CELL, sheet_id='csv:0',
            column_id='column:1', source_row=1, start=None, end=None, json_path=()))
        self.assertEqual(len(resolve_actions(snap, ctx, (table_hit,), binding, at=AT, field_ref='content/endpoint')), 1)


if __name__ == '__main__':
    unittest.main()
