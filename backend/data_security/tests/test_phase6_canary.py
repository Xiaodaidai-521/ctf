"""Synthetic tool owners only; these do not stand in for business ACL or egress wiring."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock

from data_security.application.audit_gateway import AuditGateway
from data_security.application.canary import CanaryTools
from data_security.contracts import (
    AuditReceipt, BASELINE_LIMITS, BoundedPayload, CanarySeed, Category, ContractViolation,
    Durability, Environment, FrozenJSON, MediaType, Outcome, Outlet, PayloadKind,
    PolicyBinding, ProtectionContext, ProtectionError, Purpose, ReasonCode, TableSnapshot, canonical_bytes,
)
from data_security.core.redaction import detect
from data_security.tests.fixtures import AT, HASH, dto, examples


def text(value):
    return dto(BoundedPayload, kind=PayloadKind.TEXT, media_type=MediaType.TEXT,
               text=value, tree=None, binary=None, limits=BASELINE_LIMITS)


class CanaryToolFixture:
    def setUp(self):
        super().setUp()
        self.seed = examples()[CanarySeed]
        self.context = replace(examples()[ProtectionContext], outlet=Outlet.AUDIT,
            purpose=Purpose.SECURITY_AUDIT, object_ref=self.seed.target_ref, object_version=self.seed.target_version)
        self.events, self.packets = [], []
        def append(event, durability):
            self.events.append(event)
            return dto(AuditReceipt, event_id=event.event_id, durability=durability, stored_at=AT,
                chain_version='ds.audit.v2', entry_ref='audit/v2/' + str(len(self.events)),
                sequence=len(self.events), entry_hash=HASH, checkpoint_ref=None)
        def plant(seed, packet, context):
            self.packets.append(packet)
            return seed
        self.sink = Mock(append=Mock(side_effect=append))
        self.authorize = Mock(side_effect=lambda operation, context, seed: context)
        self.plant = Mock(side_effect=plant)
        self.options = dict(seeds=(self.seed,), environment=Environment.TEST, domain=self.seed.domain,
            limits=BASELINE_LIMITS, policy_binding=examples()[PolicyBinding], authorize=self.authorize,
            plant_target=self.plant, audit=AuditGateway(sink=self.sink), clock=lambda: AT,
            event_id=lambda: 'canary/event/' + str(len(self.events) + 1))
        self.service = CanaryTools(**self.options)

    def planted_values(self):
        self.assertEqual(self.service.tools['canary.plant'](seed_id=self.seed.seed_id, context=self.context), self.seed)
        return self.packets[-1].tree.to_value()['values']

    def check(self, value, outlet=Outlet.EXPORT):
        return self.service.tools['canary.check'](payload=value, context=replace(self.context, outlet=outlet))


class CanaryToolTests(CanaryToolFixture, TestCase):
    def test_seed_contract_rejects_original_values_production_and_unknown_targets(self):
        self.assertEqual(CanarySeed.from_wire(self.seed.to_wire()), self.seed)
        for changes in ({'target_kind': 'arbitrary'}, {'environment': Environment.PRODUCTION},
                        {'seed_id': 'original'}, {'seed_id': 'z' * 32}):
            with self.assertRaises(ContractViolation):
                replace(self.seed, **changes)
        with self.assertRaises(ContractViolation):
            CanarySeed.from_wire(dict(self.seed.to_wire(), email='unregistered@example.invalid'))
        with self.assertRaises(ContractViolation):
            CanaryTools(**dict(self.options, environment=Environment.PRODUCTION))

    def test_all_three_target_kinds_plant_labelled_values_detectable_by_only_existing_three_categories(self):
        for kind in ('knowledge', 'database', 'challenge'):
            seed = replace(self.seed, target_kind=kind)
            service = CanaryTools(**dict(self.options, seeds=(seed,)))
            self.assertEqual(service.plant(seed_id=seed.seed_id, context=self.context), seed)
            packet = self.packets[-1].tree.to_value()
            self.assertIs(packet['synthetic'], True)
            self.assertEqual(packet['seed'], seed.to_wire())
            values = packet['values']
            self.assertEqual(set(values), {c.value for c in (Category.EMAIL, Category.IPV4, Category.CARD)})
            self.assertTrue(values['email_address'].endswith('@example.invalid'))
            self.assertTrue(values['ip_address'].startswith(('192.0.2.', '198.51.100.', '203.0.113.')))
            self.assertTrue(values['payment_card_candidate'].startswith('000000'))
            found = detect(text(' '.join(values.values())), BASELINE_LIMITS)
            self.assertEqual({f.category for f in found}, {Category.EMAIL, Category.IPV4, Category.CARD})
        self.assertEqual(len(self.packets), 3)
        self.assertEqual(self.events, [])

    def test_only_explicit_current_owner_may_plant_not_role_or_boolean_approval(self):
        for authorized in (True, None, replace(self.context, authorization_ref='different/grant')):
            self.authorize.side_effect = None
            self.authorize.return_value = authorized
            self.assertEqual(self.service.plant(seed_id=self.seed.seed_id, context=self.context).code,
                             ReasonCode.AUTHORIZATION_DENIED)
        self.authorize.side_effect = lambda operation, context, seed: context
        for context in (replace(self.context, domain='another/domain'),
                        replace(self.context, object_ref='another/object'),
                        replace(self.context, outlet=Outlet.EXPORT)):
            self.assertEqual(self.service.plant(seed_id=self.seed.seed_id, context=context).code,
                             ReasonCode.AUTHORIZATION_DENIED)
        self.plant.assert_not_called()
        self.assertEqual(self.service.plant(seed_id='f' * 32, context=self.context).code,
                         ReasonCode.SOURCE_NOT_APPROVED)

    def test_plant_does_not_claim_persistence_on_boolean_or_error_receipt(self):
        self.plant.side_effect = None
        self.plant.return_value = True
        self.assertEqual(self.service.plant(seed_id=self.seed.seed_id, context=self.context).code,
                         ReasonCode.SOURCE_NOT_APPROVED)
        failure = dto(ProtectionError, code=ReasonCode.SOURCE_NOT_APPROVED, retryable=False, trace_id='canary/owner')
        self.plant.return_value = failure
        self.assertEqual(self.service.plant(seed_id=self.seed.seed_id, context=self.context), failure)

    def test_each_literal_at_each_supported_outlet_requires_v2_and_metadata_only_alert(self):
        values = self.planted_values()
        for outlet in (Outlet.MODEL, Outlet.EMBEDDING, Outlet.LOG, Outlet.EXPORT):
            for value in values.values():
                receipts = self.check(text('prefix ' + value + ' suffix'), outlet)
                self.assertEqual(len(receipts), 1)
                self.assertEqual(receipts[0].chain_version, 'ds.audit.v2')
                event = self.events[-1]
                self.assertEqual(event.counts, (('hit', 1),))
                self.assertEqual(event.outcome, Outcome.FAILED)
                self.assertIn('outlet/' + outlet.value, event.algorithm_versions)
                self.assertEqual((event.object_ref, event.object_version, event.correlation_ref),
                                 (self.seed.target_ref, self.seed.target_version, self.context.trace_id))
                wire = canonical_bytes(event)
                for original in values.values():
                    self.assertNotIn(original.encode(), wire)
        self.assertEqual(len(self.events), 12)

    def test_no_hit_partial_changed_or_longer_token_never_generates_alert(self):
        values = self.planted_values()
        clean = ('[EMAIL] [IPV4] [CARD]', 'other@example.invalid',
                 values['email_address'].upper(), 'x' + values['email_address'],
                 values['email_address'] + '.extra', values['ip_address'] + '0',
                 values['ip_address'][:-1], values['payment_card_candidate'] + '0')
        for value in clean:
            self.assertEqual(self.check(text(value)), ())
        self.sink.append.assert_not_called()

    def test_nested_json_keys_and_values_are_checked_without_joining_fragments(self):
        values = self.planted_values()
        payload = dto(BoundedPayload, kind=PayloadKind.JSON, media_type=MediaType.JSON, text=None, binary=None,
            tree=FrozenJSON({values['email_address']: ['safe', {'ip': values['ip_address'],
                                                      'card': values['payment_card_candidate']}]}),
            limits=BASELINE_LIMITS)
        self.assertEqual(len(self.check(payload)), 1)
        self.assertEqual(self.events[-1].counts, (('hit', 3),))
        fragments = list(values['email_address'])
        self.assertEqual(self.check(replace(payload, tree=FrozenJSON(fragments))), ())

    def test_binary_wrong_environment_and_unauthorized_checks_are_not_clean_results(self):
        binary = dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.BINARY,
                     text=None, tree=None, binary=b'not-decoded', limits=BASELINE_LIMITS)
        self.assertEqual(self.check(binary).code, ReasonCode.UNSUPPORTED_FORMAT)
        self.assertEqual(self.service.check(payload=text('safe'),
            context=replace(self.context, environment=Environment.EVALUATION, outlet=Outlet.EXPORT)).code,
            ReasonCode.AUTHORIZATION_DENIED)
        self.authorize.side_effect = None
        self.authorize.return_value = True
        self.assertEqual(self.check(text('safe')).code, ReasonCode.AUTHORIZATION_DENIED)
        self.sink.append.assert_not_called()

    def test_failed_wrong_or_legacy_audit_receipt_cannot_be_reported_as_success(self):
        value = next(iter(self.planted_values().values()))
        failure = dto(ProtectionError, code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='fixture/audit')
        self.sink.append.side_effect = None
        self.sink.append.return_value = failure
        self.assertEqual(self.check(text(value)).code, ReasonCode.AUDIT_UNAVAILABLE)
        legacy = dto(AuditReceipt, event_id='canary/event/1', durability=Durability.LEDGER_CONFIRMED,
            stored_at=AT, chain_version='v1', entry_ref='audit/legacy/1', sequence=1,
            entry_hash=HASH, checkpoint_ref=None)
        for receipt in (legacy, replace(legacy, chain_version='ds.audit.v2', event_id='wrong/event')):
            self.sink.append.return_value = receipt
            self.assertEqual(self.check(text(value)).code, ReasonCode.AUDIT_UNAVAILABLE)

    def test_explicit_limits_bound_catalog_and_checked_payload(self):
        limits = replace(BASELINE_LIMITS, max_findings=1)
        with self.assertRaises(ContractViolation):
            CanaryTools(**dict(self.options, limits=limits,
                seeds=(self.seed, replace(self.seed, seed_id='f' * 32))))
        # Construction itself also bounds the synthetic planting packet.
        with self.assertRaises(ContractViolation):
            CanaryTools(**dict(self.options, limits=replace(BASELINE_LIMITS, max_json_bytes=16)))
        self.service = CanaryTools(**dict(self.options, limits=replace(BASELINE_LIMITS, max_bytes=16)))
        self.assertEqual(self.check(text('x' * 32)).code, ReasonCode.LIMIT_EXCEEDED)

    def test_output_table_checks_original_cells_and_labels_not_normalized_text(self):
        values = self.planted_values()
        snapshot = examples()[TableSnapshot]
        cell = replace(snapshot.cells[0], original_text=values['ip_address'],
            normalized_text=values['payment_card_candidate'], mapping_proven=False, source_spans=())
        column = replace(snapshot.columns[0], label=values['email_address'])
        self.assertEqual(len(self.check(replace(snapshot, cells=(cell,), columns=(column,)))), 1)
        self.assertEqual(self.events[-1].counts, (('hit', 2),))
        clean = replace(snapshot, cells=(replace(cell, original_text='safe'),))
        self.assertEqual(self.check(clean), ())
        self.assertEqual(len(self.events), 1)

    def test_output_table_requires_export_and_tool_limits(self):
        snapshot = examples()[TableSnapshot]
        for outlet in (Outlet.MODEL, Outlet.EMBEDDING, Outlet.LOG):
            self.assertEqual(self.check(snapshot, outlet).code, ReasonCode.UNSUPPORTED_SCOPE)
        self.service = CanaryTools(**dict(self.options, limits=replace(BASELINE_LIMITS, max_bytes=8)))
        self.assertEqual(self.check(snapshot).code, ReasonCode.LIMIT_EXCEEDED)
        self.sink.append.assert_not_called()

    def test_shared_test_net_value_reports_both_possible_sources_not_a_unique_origin(self):
        second = replace(self.seed, seed_id=f'{int(self.seed.seed_id, 16) + 762:032x}', target_ref='synthetic/other')
        self.service = CanaryTools(**dict(self.options, seeds=(self.seed, second)))
        value = self.planted_values()['ip_address']
        self.assertEqual(len(self.check(text(value))), 2)
        self.assertEqual({e.object_ref for e in self.events}, {self.seed.target_ref, second.target_ref})
