import copy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import timedelta, timezone
import inspect
import json
import math
import pickle
import unittest

from data_security.contracts import *
from data_security.contracts.schema import MAX_BYTES, MAX_WIRE_BYTES
from .fixtures import AT, HASH, approval, dto, examples


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = examples()

    def rejects(self, call, *args, **kwargs):
        with self.assertRaises(ContractViolation) as caught:
            call(*args, **kwargs)
        self.assertIn(caught.exception.code, ReasonCode)
        self.assertEqual(str(caught.exception), caught.exception.code.value)

    def test_every_registered_schema_has_a_valid_fixture(self):
        self.assertEqual(set(CONTRACT_TYPES), set(self.examples))
        self.assertEqual(len({cls.SCHEMA for cls in CONTRACT_TYPES}), len(CONTRACT_TYPES))

    def test_wire_roundtrips_and_server_only_objects_reject_clients(self):
        for cls, value in self.examples.items():
            with self.subTest(schema=cls.SCHEMA):
                wire = value.to_wire(include_payload=True)
                if cls.SERVER_ONLY:
                    self.rejects(cls.from_wire, wire)
                    self.rejects(cls.from_json, canonical_bytes(value, include_payload=True))
                else:
                    self.assertEqual(cls.from_wire(wire), value)
                    self.assertEqual(cls.from_json(canonical_bytes(value, include_payload=True)), value)

    def test_all_wire_schemas_reject_missing_extra_wrong_schema_and_types(self):
        for cls, value in self.examples.items():
            with self.subTest(schema=cls.SCHEMA):
                wire = value.to_wire(include_payload=True)
                for field in fields(value):
                    missing = dict(wire)
                    del missing[field.name]
                    self.rejects(cls.from_wire, missing)
                    malformed = dict(wire, **{field.name: object()})
                    self.rejects(cls.from_wire, malformed)
                self.rejects(cls.from_wire, dict(wire, extra='not-supported'))
                self.rejects(cls.from_wire, dict(wire, schema_version='unknown.v999'))
                self.rejects(cls.from_wire, tuple(wire.items()))

    def test_every_dto_is_frozen_redacted_and_has_no_dictionary(self):
        for value in self.examples.values():
            with self.subTest(schema=value.SCHEMA):
                self.assertEqual(repr(value), type(value).__name__ + '(<redacted>)')
                self.assertFalse(hasattr(value, '__dict__'))
                with self.assertRaises((FrozenInstanceError, AttributeError)):
                    value.schema_version = 'mutated'

    def test_nested_json_copies_mutable_input_and_preserves_json_types(self):
        raw = {'a': [None, False, 0, '', {'text': 'Ａ🙂'}]}
        frozen = FrozenJSON(raw)
        raw['a'].append('late mutation')
        self.assertEqual(len(frozen.to_value()['a']), 5)
        other = frozen.to_value()
        other['a'].clear()
        self.assertEqual(len(frozen.to_value()['a']), 5)
        self.assertEqual(copy.deepcopy(frozen), frozen)
        with self.assertRaises(AttributeError):
            frozen._bytes = b'changed'

    def test_empty_text_json_null_and_empty_binary_are_distinct(self):
        values = [
            dto(BoundedPayload, kind=PayloadKind.TEXT, media_type=MediaType.TEXT,
                text='', tree=None, binary=None, limits=BASELINE_LIMITS),
            dto(BoundedPayload, kind=PayloadKind.JSON, media_type=MediaType.JSON,
                text=None, tree=FrozenJSON(None), binary=None, limits=BASELINE_LIMITS),
            dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.BINARY,
                text=None, tree=None, binary=b'', limits=BASELINE_LIMITS),
        ]
        encoded = [canonical_bytes(v, include_payload=True) for v in values]
        self.assertEqual(len(set(encoded)), 3)
        for value, data in zip(values, encoded):
            self.assertEqual(BoundedPayload.from_json(data), value)
        self.rejects(replace, values[0], tree=FrozenJSON(None))

    def test_sensitive_payload_is_never_serialized_by_default(self):
        for cls in (BoundedPayload, TableSnapshot, TableCell, TableColumn, SourceDocument, AIRequest):
            self.rejects(self.examples[cls].to_wire)
        self.rejects(canonical_bytes, FrozenJSON({'fixture': 'content'}))

    def test_json_is_closed_and_bounded(self):
        for value in (float('nan'), float('inf'), -float('inf'), {'bad': object()}, {1: 'wrong-key'},
                      (1, 2), 2**53, '\ud800'):
            self.rejects(FrozenJSON, value)
        nested = 0
        for _ in range(17):
            nested = [nested]
        for value in (nested, [0] * 10001, {str(i): 0 for i in range(2049)}, 'x' * 65537):
            self.rejects(FrozenJSON, value)
        self.rejects(FrozenJSON, [1, 2], max_nodes=2)
        self.rejects(FrozenJSON, 'abc', max_bytes=4)

    def test_strict_json_rejects_duplicates_nan_surrogates_and_bad_root(self):
        for wire in (b'{"schema_version":"x","schema_version":"y"}', b'{"x":NaN}',
                     b'{"x":Infinity}', b'[]', b'null', b'\xff', b'{', b'"\\ud800"'):
            self.rejects(Limits.from_json, wire)
        self.rejects(Limits.from_json, b' ' * (MAX_WIRE_BYTES + 1))

    def test_limits_refuse_bool_noninteger_unknown_version_and_higher_caps(self):
        for name in (f.name for f in fields(BASELINE_LIMITS) if f.name.startswith('max_')):
            for invalid in (True, 1.0, 0, -1, getattr(BASELINE_LIMITS, name) + 1):
                self.rejects(replace, BASELINE_LIMITS, **{name: invalid})
        self.rejects(replace, BASELINE_LIMITS, version='latest')

    def test_payload_enforces_explicit_tighter_limits(self):
        limits = replace(BASELINE_LIMITS, max_bytes=3, max_text_chars=3)
        self.rejects(dto, BoundedPayload, kind=PayloadKind.TEXT, media_type=MediaType.TEXT,
                     text='🙂', tree=None, binary=None, limits=limits)
        self.rejects(dto, BoundedPayload, kind=PayloadKind.JSON, media_type=MediaType.JSON,
                     text=None, tree=FrozenJSON({'a': 1}), binary=None,
                     limits=replace(BASELINE_LIMITS, max_json_bytes=3))
        self.rejects(replace, self.examples[BoundedPayload], media_type=MediaType.JSON)

    def test_categories_are_exactly_the_four_authorized_families(self):
        self.assertEqual({v.value for v in Category},
                         {'email_address', 'ip_address', 'payment_card_candidate', 'secret_credential'})
        self.rejects(Finding.from_wire, dict(self.examples[Finding].to_wire(), category='unsupported'))
        self.rejects(replace, self.examples[Finding], category=Category.CARD)

    def test_coordinates_are_source_one_based_rows_and_codepoint_half_open_spans(self):
        location = self.examples[Location]
        snapshot = self.examples[TableSnapshot]
        snapshot.validate_location(location)
        for change in ({'source_row': 0}, {'start': -1}, {'start': 2, 'end': 2},
                       {'end': 65537}, {'column_id': None}, {'source_row': True}):
            self.rejects(replace, location, **change)
        for change in ({'end': 4}, {'sheet_id': 'xlsx:0'}, {'column_id': 'column:2'}, {'source_row': 3}):
            self.rejects(snapshot.validate_location, replace(location, **change))
        self.rejects(replace, self.examples[TableCell], source_spans=((1, 2), (0, 1), (2, 3)))
        self.rejects(replace, self.examples[TableCell], mapping_proven=False)

    def test_unproven_mapping_allows_no_span_action(self):
        cell = replace(self.examples[TableCell], mapping_proven=False, source_spans=())
        snapshot = replace(self.examples[TableSnapshot], cells=(cell,))
        self.rejects(snapshot.validate_location, self.examples[Location])
        snapshot.validate_location(replace(self.examples[Location], kind=LocationKind.CELL, start=None, end=None))

    def test_table_scope_and_identity_reject_duplicates_and_unknown_columns(self):
        snapshot = self.examples[TableSnapshot]
        self.rejects(replace, snapshot, cells=snapshot.cells * 2)
        self.rejects(replace, snapshot, columns=snapshot.columns * 2)
        self.rejects(replace, snapshot, sheet_ids=('csv:0', 'csv:0'))
        self.rejects(replace, self.examples[SheetScope], row_ranges=((1, 2), (3, 4)))
        self.rejects(replace, self.examples[SheetScope], row_ranges=((0, 1),))
        self.examples[ActionPlan].validate_snapshot(snapshot)
        self.rejects(self.examples[ActionPlan].validate_snapshot, replace(snapshot, asset_version='asset/v2'))

    def test_coverage_never_silently_counts_failures_unknown_or_exclusions(self):
        coverage = dto(Coverage, unit=Unit.CELL, total=10, eligible=8, processed=2,
                       excluded=2, failed=1, unknown=2, unscanned=3, version='v1')
        self.assertEqual(coverage.ratio, 0.25)
        self.rejects(replace, coverage, processed=8)
        self.rejects(replace, coverage, unknown=-1)
        self.rejects(replace, self.examples[ProtectedResult], coverage=coverage)
        empty = replace(coverage, total=0, eligible=0, processed=0, excluded=0, failed=0, unknown=0, unscanned=0)
        self.assertIsNone(empty.ratio)
        self.assertIsNone(self.examples[Metric].ratio)
        self.rejects(replace, self.examples[Metric], zero_reason=None)

    def test_metadata_hash_is_canonical_versioned_and_unicode_preserving(self):
        self.assertEqual(content_hash({'b': 2, 'a': 1}), content_hash({'a': 1, 'b': 2}))
        self.assertNotEqual(content_hash({'a': 'Ａ'}), content_hash({'a': 'A'}))
        self.assertNotEqual(content_hash({'a': 1}), content_hash({'a': 1.0}))
        self.rejects(content_hash, {'bad': math.nan})

    def test_policy_and_plan_hashes_cover_mutation_and_approval(self):
        self.rejects(replace, self.examples[PolicySnapshot], version='v2')
        self.rejects(replace, self.examples[PolicySnapshot], approval=None)
        self.rejects(replace, self.examples[ActionPlan], adapter_version='other-v2')
        self.rejects(replace, self.examples[ActionPlan], input_hash='0' * 64)
        self.rejects(replace, self.examples[Approval], approved_by='actor/requester')
        self.rejects(replace, self.examples[TeachingException], source_version='v2')
        self.rejects(replace, self.examples[TeachingException], category=Category.SECRET)

    def test_algorithms_are_parameter_closed_and_key_material_is_not_a_parameter(self):
        algorithm = self.examples[AlgorithmSpec]
        self.rejects(replace, algorithm, key_ref='mask-link/v1')
        self.rejects(replace, algorithm, version='unknown')
        for category in (Category.CARD, Category.SECRET):
            masking = dto(AlgorithmSpec, algorithm=Algorithm.MASK, version='v1', replacement=None,
                keep_prefix=0, keep_suffix=4, mask_symbol='*', max_length=None, ipv4_prefix=None,
                pseudonym_bits=None, key_ref=None)
            self.rejects(masking.validate_category, category)
        self.rejects(AlgorithmSpec.from_wire, dict(algorithm.to_wire(), key_material='forbidden'))

    def test_source_schema_and_original_digest_namespaces_are_not_reinterpreted(self):
        source = self.examples[SourcePlanBinding]
        self.assertEqual(source.source_version, 'mainline1.proposed.v1')
        self.rejects(replace, source, source_version='mainline1.coordinate.v1')
        self.rejects(replace, source, source_plan_hash=HASH)
        self.rejects(replace, source, source_state='approved')
        self.rejects(replace, source, source_trust=SourceTrust.PRODUCTION, provenance_ref=None)
        self.rejects(replace, self.examples[SourceDocument], source_version='mainline1.proposed.v1')

    def test_key_refs_cannot_contain_paths_wrong_purposes_or_versions(self):
        key = self.examples[KeyReference]
        for value in ('../key', '/etc/key', 'enc-data/../v1', 'enc-data//v1', 'provider/test/v1', 'enc-data/v2'):
            self.rejects(replace, key, key_ref=value)
        self.rejects(replace, key, purpose=KeyPurpose.AUDIT)

    def test_secret_material_is_scoped_immutable_nonserializable_and_redacted(self):
        value = bytes(range(32))
        secret = SecretMaterial(value, KeyPurpose.DATA)
        self.assertEqual(repr(secret), 'SecretMaterial(<redacted>)')
        self.assertTrue(secret.borrow(KeyPurpose.DATA).readonly)
        self.rejects(secret.borrow, KeyPurpose.PROVIDER)
        for call in (pickle.dumps, copy.copy, copy.deepcopy, canonical_bytes):
            with self.assertRaises((TypeError, ContractViolation)):
                call(secret)

    def test_envelope_rejects_unknown_format_lengths_and_plaintext_fallback(self):
        envelope = self.examples[CipherEnvelope]
        for change in ({'format_version': 'fernet'}, {'kdf_salt': b''}, {'nonce': b''},
                       {'ciphertext_and_tag': b''}, {'ciphertext_and_tag': b'x' * (MAX_BYTES + 17)}):
            self.rejects(replace, envelope, **change)
        wire = envelope.to_wire()
        self.rejects(CipherEnvelope.from_wire, dict(wire, nonce='not base64'))
        self.rejects(CipherEnvelope.from_wire, dict(wire, wrapped_key='forbidden'))

    def test_datetime_requires_utc_and_explicit_wire_format(self):
        self.rejects(replace, self.examples[SecurityEvent], occurred_at=AT.replace(tzinfo=None))
        self.rejects(replace, self.examples[SecurityEvent], occurred_at=AT.astimezone(timezone(timedelta(hours=1))))
        self.rejects(SecurityEvent.from_wire, dict(self.examples[SecurityEvent].to_wire(), occurred_at=AT.isoformat()))

    def test_audit_white_list_and_durability_are_distinct(self):
        event = self.examples[SecurityEvent]
        self.rejects(SecurityEvent.from_wire, dict(event.to_wire(), detail={'raw': 'not allowed'}))
        self.rejects(replace, event, counts=(('body', 1),))
        receipt = self.examples[AuditReceipt]
        self.rejects(replace, receipt, durability=Durability.LEDGER_CONFIRMED)
        self.rejects(replace, receipt, chain_version='v1')
        ledger = replace(receipt, durability=Durability.LEDGER_CONFIRMED, chain_version='v1',
                         entry_ref='ledger/1', sequence=1, entry_hash=HASH)
        self.rejects(replace, ledger, checkpoint_ref='checkpoint/1')

    def test_quota_preserves_exact_legacy_states_and_unknown_hold(self):
        self.assertEqual({state.value for state in QuotaState}, {'reserved', 'committed', 'released', 'unknown'})
        quota = self.examples[QuotaReceipt]
        self.assertEqual(quota.held_amount, quota.binding.quantity)
        self.assertIsNone(quota.settled_amount)
        self.rejects(replace, quota, settled_amount=0)
        zero = replace(quota, state=QuotaState.COMMITTED, settled_amount=0)
        self.assertEqual(zero.state, QuotaState.COMMITTED)
        self.assertEqual(zero.held_amount, 0)
        self.rejects(replace, zero, settled_amount=quota.binding.quantity + 1)
        self.rejects(replace, quota.binding, quantity=True)

    def test_reports_do_not_claim_success_with_unknown_scan_or_missing_output(self):
        report = self.examples[MaskReport]
        self.rejects(replace, report, rescan_state=ScanState.UNKNOWN)
        self.rejects(replace, report, output_hash=None)
        self.rejects(replace, report, output_hash='0' * 64)
        self.rejects(MaskReport.from_wire, report.to_wire())
        self.rejects(replace, self.examples[DeliveryReceipt], delivered_records=0)

    def test_reveal_is_server_only_bounded_approved_and_single_use(self):
        grant = self.examples[RevealGrant]
        self.rejects(RevealGrant.from_wire, grant.to_wire())
        self.rejects(replace, grant, expires_at=grant.issued_at + timedelta(seconds=901))
        self.rejects(replace, grant, state=GrantState.CONSUMED)
        self.rejects(replace, grant, consumed_at=grant.expires_at, state=GrantState.CONSUMED)
        consumed = replace(grant, consumed_at=grant.issued_at, state=GrantState.CONSUMED)
        self.assertIsNotNone(consumed.consumed_at)
        self.assertEqual({f.value for f in RevealField}, {'email', 'conversation', 'evidence', 'report'})

    def test_ports_are_protocols_with_no_variadic_sdk_argument_escape(self):
        for port in PORT_TYPES:
            self.assertTrue(port._is_protocol)
            for name, method in vars(port).items():
                if callable(method) and not name.startswith('_'):
                    signature = inspect.signature(method)
                    self.assertNotIn(inspect.Parameter.VAR_KEYWORD, {p.kind for p in signature.parameters.values()})
                    self.assertNotIn(inspect.Parameter.VAR_POSITIONAL, {p.kind for p in signature.parameters.values()})
        parameters = list(inspect.signature(SourcePlanAdapter.to_action_plan).parameters)
        self.assertEqual(parameters, ['self', 'source', 'snapshot', 'binding', 'resolved_actions'])

    def test_ai_wire_cannot_supply_raw_provider_url_or_sdk_options(self):
        wire = self.examples[AIRequest].to_wire(include_payload=True)
        for field in ('base_url', 'api_key', 'kwargs', 'raw_provider'):
            self.rejects(AIRequest.from_wire, dict(wire, **{field: 'not allowed'}))
        self.rejects(replace, self.examples[AIRequest], temperature=math.nan)
        self.rejects(replace, self.examples[EmbeddingResult], vectors=((math.inf,),))
