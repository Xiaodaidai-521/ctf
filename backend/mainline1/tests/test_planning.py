"""Synthetic rules + real parser/review logic; authority/approval are TEST doubles."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import jsonschema

from mainline1.parsing import AssetRef, InputError, ParserConfig, Scope, Selection, fingerprint, parse_table
from mainline1.planning import PlanInputs, PlanPolicy, PlanService, plan_digest
from mainline1.review import MemoryReviewRepository, ReviewPrincipal, ReviewService
from mainline1.tests import test_rules
from mainline1.tests.test_review import AccessDouble


class SourceDouble:
    """The only ready-path approvals in this suite are explicitly fictitious."""
    def __init__(self, review, parsed, requirements, policy):
        self.review, self.parsed = review, parsed
        self.requirements, self.policy = requirements, policy
        self.overrides = {}
        self.synthetic_usable = True

    def read(self, actor, profile_id):
        basis = self.review.read_plan_basis(actor, profile_id)
        profile = basis['bundle']['profile']
        if self.synthetic_usable:
            basis['applicability']['usable_for_new_decision'] = True
        context = PlanInputs(**basis, parsed=self.parsed, current_asset=profile['asset'],
            asset_state='ready', asset_state_version=1, current_policy_version=profile['policy_version'],
            requirements=deepcopy(self.requirements), policy=self.policy)
        return replace(context, **deepcopy(self.overrides))


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_rules.RuleTests()
        self.fixture.setUp()
        self.parsed = self.fixture.parsed(['😀 a@example.invalid', 'b@example.invalid'])
        self.repo, self.access = MemoryReviewRepository(), AccessDouble()
        self.review = ReviewService(self.repo, self.access)
        self.actor = ReviewPrincipal(1, 'test-domain', 'test')
        self.register(self.parsed)
        self.requirements = [dict(requirement_id='protect-email', version='synthetic-v1',
            category_ids=[self.findings[0]['category_id']], allowed_operations=['mask_span', 'mask_cell'],
            allow_drop_column=False, require_complete_coverage=True, allow_unresolved=True)]
        self.policy = PlanPolicy('synthetic-approved-test-v1', 'mask_cell', True, True, True)
        self.source = SourceDouble(self.review, self.parsed, self.requirements, self.policy)
        self.now = datetime(2026, 10, 14, tzinfo=timezone.utc)
        self.service = PlanService(self.source, cursor_key=b'synthetic-test-only-cursor-key-32bytes', clock=lambda: self.now)

    def register(self, parsed):
        result = self.fixture.scan(parsed, semantic_required=False)
        self.pid = self.review.register(self.actor, result, parsed)
        self.findings = result.data()['findings']

    def build(self, key='one'):
        return self.service.build(self.actor, self.pid, idempotency_key=key)

    def check(self, plan):
        return self.service.validate(self.actor, plan)

    def rehash(self, plan):
        plan['plan_hash'] = plan_digest(plan)
        return plan

    def code(self, code, fn, *args, **kwargs):
        with self.assertRaises(InputError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def invalid(self, plan, code):
        result = self.check(plan)
        self.assertFalse(result['valid'])
        self.assertIn(code, result['error_codes'])

    def confirm_all(self):
        for index, finding in enumerate(self.findings):
            record = self.review.submit_review(self.actor, base_profile_id=self.pid, expected_state_version=1,
                idempotency_key='confirm-' + str(index), action='confirm', finding_id=finding['finding_id'], reason='synthetic review')
            self.pid = record['successor_profile_id']
        self.findings = self.review.read_plan_basis(self.actor, self.pid)['bundle']['findings']

    def test_correct_plan_schema_and_current_observation(self):
        plan = self.build()
        self.assertEqual(plan['status'], 'ready')
        self.assertEqual(plan['operation_count'], 2)
        result = self.check(plan)
        self.assertTrue(result['valid'], result)
        self.assertEqual(result['observed_applicability_version'], 1)
        schema = json.loads((Path(__file__).resolve().parents[3] / 'docs/mainline1/contracts/schema.json').read_text(encoding='utf-8'))
        jsonschema.Draft202012Validator({'$ref': '#/$defs/RedactionPlan', '$defs': schema['$defs']},
            format_checker=jsonschema.FormatChecker()).validate(plan)

    def test_draft_policy_and_actual_review_state_fail_closed(self):
        self.source.synthetic_usable = False
        self.source.policy = PlanPolicy()
        plan = self.build()
        self.assertEqual(plan['status'], 'invalid')
        self.assertIn('PLAN_APPROVAL_REQUIRED', plan['validation_errors'])
        self.invalid(plan, 'PROFILE_NOT_USABLE')

    def test_confirmed_unicode_character_spans(self):
        self.confirm_all()
        plan = self.build()
        self.assertEqual({o['type'] for o in plan['operations']}, {'mask_span'})
        op = next(o for o in plan['operations'] if o['target']['row'] == 2)
        self.assertEqual(op['target']['span'], {'start': 2, 'end': 19})
        self.assertTrue(self.check(plan)['valid'])

    def test_file_version_and_content_changes(self):
        plan = self.build()
        for key, value in [('content_hash', 'sha256:' + '0' * 64), ('asset_version_id', str(uuid4()))]:
            self.source.overrides = dict(current_asset=dict(plan['asset'], **{key: value}))
            self.invalid(plan, 'ASSET_VERSION_MISMATCH')

    def test_scope_parser_and_policy_changes(self):
        plan = self.build()
        for overrides, code in [(dict(parsed=replace(self.parsed, scope_hash='sha256:' + '0' * 64)), 'SCOPE_MISMATCH'),
                                (dict(parsed=replace(self.parsed, parser_version='changed')), 'PARSER_MISMATCH'),
                                (dict(current_policy_version='changed'), 'POLICY_MISMATCH')]:
            self.source.overrides = overrides
            self.invalid(plan, code)

    def test_requirements_and_redaction_policy_changes(self):
        plan = self.build()
        self.source.requirements[0]['version'] = 'v2'
        self.invalid(plan, 'PLAN_BINDING_MISMATCH')
        self.source.policy = replace(self.policy, version='v2')
        self.invalid(plan, 'PLAN_BINDING_MISMATCH')

    def test_manual_addition_same_asset_invalidates_old_plan(self):
        plan = self.build()
        before = deepcopy(plan)
        record = self.review.submit_review(self.actor, base_profile_id=self.pid, expected_state_version=1,
            idempotency_key='manual', action='add_manual', reason='synthetic missed finding',
            category_id=self.findings[0]['category_id'], locations=[dict(self.findings[0]['locations'][0], kind='cell', span=None)])
        self.invalid(plan, 'PROFILE_SUPERSEDED')
        self.assertEqual(self.check(plan)['observed_applicability_version'], 2)
        self.assertEqual(before, plan)
        self.assertEqual(self.review.get_profile(self.actor, record['successor_profile_id'])['asset'], plan['asset'])

    def test_private_content_mismatch_even_with_same_asset_hash(self):
        plan = self.build()
        changed = replace(self.parsed.cells[0], source_text='changed privately')
        self.source.parsed = replace(self.parsed, cells=(changed,) + self.parsed.cells[1:])
        self.invalid(plan, 'LOCATION_MISMATCH')

    def test_invalid_location_and_unknown_operation(self):
        for change, code in [(dict(type='eval'), 'OPERATION_UNSUPPORTED'),
                             (dict(replacement='=evil()'), 'OPERATION_PARAMETERS_INVALID'),
                             (dict(target=dict(self.build()['operations'][0]['target'], row=900)), 'LOCATION_MISMATCH'),
                             (dict(match_ref='sha256:' + '0' * 64), 'LOCATION_MISMATCH')]:
            plan = self.build()
            plan['operations'][0].update(change)
            self.invalid(self.rehash(plan), code)

    def test_overlap_conflict(self):
        self.confirm_all()
        plan = self.build()
        original = plan['operations'][0]
        duplicate = deepcopy(original)
        duplicate['operation_id'] = str(uuid4())
        duplicate['match_ref'] = 'private:plan-match:' + plan['plan_id'] + ':' + duplicate['operation_id']
        plan['operations'].append(duplicate)
        plan['operation_count'] += 1
        self.invalid(self.rehash(plan), 'PLAN_CONFLICT')

    def test_whole_cell_and_span_conflict(self):
        self.confirm_all()
        plan = self.build()
        op = deepcopy(plan['operations'][0])
        op.update(type='mask_cell', operation_id=str(uuid4()))
        op['target'].update(kind='cell', span=None)
        op['match_ref'] = 'private:plan-match:' + plan['plan_id'] + ':' + op['operation_id']
        plan['operations'].append(op)
        plan['operation_count'] += 1
        self.invalid(self.rehash(plan), 'PLAN_CONFLICT')

    def test_drop_column_requires_full_scope(self):
        self.source.requirements[0].update(allowed_operations=['drop_column'], allow_drop_column=True)
        plan = self.build()
        self.assertEqual(plan['status'], 'partial')
        self.assertEqual(plan['operations'], [])
        self.assertIn('protect-email:TARGET_UNCOVERED', plan['unresolved'])

    def setup_columns(self):
        content = b'colA,colB\na@example.invalid,192.0.2.1\n'
        ref = AssetRef(test_rules.V, 'test-domain', 'sha256:' + hashlib.sha256(content).hexdigest(), 'csv', len(content), 'private:synthetic')
        parsed = parse_table(content, ref, config=ParserConfig(include_header=True))
        self.repo = MemoryReviewRepository()
        self.review = ReviewService(self.repo, self.access)
        self.register(parsed)
        self.parsed = parsed
        self.source.review, self.source.parsed = self.review, parsed
        self.confirm_all()
        categories = {f['locations'][0]['column']: f['category_id'] for f in self.findings}
        self.source.requirements = [dict(self.requirements[0], category_ids=[categories[1]], allowed_operations=['drop_column'], allow_drop_column=True),
            dict(self.requirements[0], requirement_id='protect-ip', category_ids=[categories[2]], allowed_operations=['mask_span'])]

    def test_drop_a_and_span_original_b(self):
        self.setup_columns()
        plan = self.build()
        self.assertEqual(plan['status'], 'ready', plan)
        self.assertEqual({(o['type'], o['target']['column']) for o in plan['operations']}, {('drop_column', 1), ('mask_span', 2)})
        self.assertTrue(self.check(plan)['valid'])

    def test_same_column_drop_and_character_conflict(self):
        self.setup_columns()
        self.source.requirements.append(dict(self.source.requirements[0], requirement_id='other', allowed_operations=['mask_span'], allow_drop_column=False))
        plan = self.build()
        self.assertEqual(plan['status'], 'invalid')
        self.assertIn('PLAN_CONFLICT', plan['validation_errors'])

    def test_duplicate_requirements_deduplicate_operations(self):
        self.source.requirements.append(dict(self.requirements[0], requirement_id='second'))
        plan = self.build()
        self.assertEqual(plan['operation_count'], 2)
        self.assertEqual(len(plan['operations'][0]['requirement_ids']), 2)
        self.assertTrue(self.check(plan)['valid'])

    def test_unknown_requirements_and_no_arbitrary_expressions(self):
        for extra in [dict(expression='exec()'), dict(allowed_operations=['eval']), dict(category_ids=['invented'])]:
            self.source.requirements = [dict(self.requirements[0], **extra)]
            self.code('REQUIREMENTS_INVALID', self.build)

    def test_uncertainty_review_partial_and_no_silent_ready(self):
        self.source.policy = replace(self.policy, uncertain='review')
        plan = self.build()
        self.assertEqual(plan['status'], 'partial')
        self.assertEqual(plan['operations'], [])
        self.invalid(plan, 'COVERAGE_INCOMPLETE')
        self.source.requirements[0]['allow_unresolved'] = False
        self.assertEqual(self.build('new')['status'], 'invalid')

    def test_incomplete_coverage_even_when_no_findings(self):
        basis = self.review.read_plan_basis(self.actor, self.pid)['bundle']
        basis['profile']['quality'] = 'partial'
        basis['profile']['finding_ids'], basis['findings'] = [], []
        self.source.overrides['bundle'] = basis
        plan = self.build()
        self.assertEqual(plan['status'], 'partial')
        self.assertIn('protect-email:COVERAGE_INCOMPLETE', plan['unresolved'])

    def test_omitted_operation_and_forged_empty_unresolved(self):
        plan = self.build()
        plan['operations'].pop()
        plan['operation_count'] -= 1
        self.invalid(self.rehash(plan), 'PLAN_COVERAGE_MISMATCH')
        self.invalid(plan, 'COVERAGE_INCOMPLETE')

    def test_idempotency_copies_normalization_and_conflict(self):
        plan = self.build()
        self.source.requirements[0]['allowed_operations'].reverse()
        self.assertEqual(self.build(), plan)
        plan['operations'].clear()
        self.assertEqual(len(self.build()['operations']), 2)
        self.source.requirements[0]['version'] = 'different'
        self.code('IDEMPOTENCY_CONFLICT', self.build)

    def test_validation_no_business_writes_success_failure_and_read_errors(self):
        plan = self.build()
        before = self.repo.read(lambda s: s)
        cache = deepcopy((self.service._keys, self.service._plans))
        with patch.object(self.repo, 'atomic', side_effect=AssertionError('must not write')):
            self.assertTrue(self.check(plan)['valid'])
            self.source.overrides['asset_state'] = 'deleted'
            self.invalid(plan, 'ASSET_UNAVAILABLE')
        with patch.object(self.source, 'read', side_effect=RuntimeError('private text never returned')):
            self.invalid(plan, 'AUTHORITY_UNAVAILABLE')
        self.assertEqual(before, self.repo.read(lambda s: s))
        self.assertEqual(cache, (self.service._keys, self.service._plans))

    def test_access_domain_environment_and_actor(self):
        plan = self.build()
        for actor in [replace(self.actor, domain_id='other'), replace(self.actor, environment='production'),
                      replace(self.actor, actor_id=99), replace(self.actor, evaluation_run_id=str(uuid4()))]:
            self.code('OBJECT_NOT_FOUND', self.service.validate, actor, plan)
        self.access.denied.add((1, 'plan'))
        self.code('OBJECT_NOT_FOUND', self.check, plan)

    def test_pagination_fixed_plan_hash_after_review(self):
        plan = self.build()
        first = self.service.page(self.actor, plan['plan_id'], page_size=1)
        self.review.submit_review(self.actor, base_profile_id=self.pid, expected_state_version=1,
            idempotency_key='confirm', action='confirm', reason='synthetic', finding_id=self.findings[0]['finding_id'])
        second = self.service.page(self.actor, plan['plan_id'], page_size=1, cursor=first['next_cursor'])
        self.assertEqual(first['plan_header'], second['plan_header'])
        self.assertEqual(first['operations_hash'], fingerprint(first['operations'] + second['operations']))
        self.assertIsNone(second['next_cursor'])
        assembled = dict(first['plan_header'], operations=first['operations'] + second['operations'])
        self.assertEqual(plan_digest(assembled), plan['plan_hash'])
        self.invalid(assembled, 'PROFILE_SUPERSEDED')

    def test_cursor_signature_scope_expiry_and_page_size(self):
        plan = self.build()
        cursor = self.service.page(self.actor, plan['plan_id'], page_size=1)['next_cursor']
        self.code('CURSOR_INVALID', self.service.page, self.actor, plan['plan_id'], page_size=1, cursor=cursor + 'x')
        self.code('CURSOR_INVALID', self.service.page, self.actor, plan['plan_id'], page_size=2, cursor=cursor)
        self.code('CURSOR_INVALID', self.service.page, replace(self.actor, actor_id=2), plan['plan_id'], page_size=1, cursor=cursor)
        self.now += timedelta(minutes=16)
        self.code('CURSOR_EXPIRED', self.service.page, self.actor, plan['plan_id'], page_size=1, cursor=cursor)

    def test_public_plan_no_source_or_cell_value_digest(self):
        text = json.dumps(self.build(), ensure_ascii=False)
        for cell in self.parsed.cells:
            self.assertNotIn(cell.source_text, text)
            self.assertNotIn(hashlib.sha256(cell.source_text.encode()).hexdigest(), text)
        self.assertNotIn('parsed_cells_hash', text)

    def test_malformed_plan_is_invalid_not_crash(self):
        for value in [None, {}, [], {'profile_id': self.pid}, dict(self.build(), operations=None)]:
            self.assertFalse(self.check(value)['valid'])

    def test_hash_and_count_tampering(self):
        plan = self.build()
        plan['operation_count'] += 1
        self.invalid(plan, 'PLAN_HASH_MISMATCH')
        self.invalid(plan, 'PLAN_COUNT_MISMATCH')

    def test_trace_excluded_from_hash(self):
        plan = self.build()
        plan['meta']['trace_id'] = str(uuid4())
        self.assertEqual(plan['plan_hash'], plan_digest(plan))
        self.assertTrue(self.check(plan)['valid'])

    def test_mapping_failure_only_policy_cell_fallback(self):
        self.confirm_all()
        basis = self.review.read_plan_basis(self.actor, self.pid)['bundle']
        basis['findings'][0]['locations'][0]['span']['end'] = 900
        self.source.overrides['bundle'] = basis
        plan = self.build()
        self.assertEqual(plan['status'], 'ready')
        self.assertIn('mask_cell', {o['type'] for o in plan['operations']})
        self.source.policy = replace(self.policy, uncertain='review')
        self.assertEqual(self.build('review-only')['status'], 'partial')

    def test_bad_cell_coordinate_cannot_fallback(self):
        basis = self.review.read_plan_basis(self.actor, self.pid)['bundle']
        basis['findings'][0]['locations'][0]['row'] = 999
        self.source.overrides['bundle'] = basis
        plan = self.build()
        self.assertEqual(plan['status'], 'partial')
        self.assertIn('protect-email:LOCATION_UNRESOLVED', plan['unresolved'])

    def test_adjacent_spans_do_not_overlap(self):
        self.confirm_all()
        basis = self.review.read_plan_basis(self.actor, self.pid)['bundle']
        loc = basis['findings'][0]['locations'][0]
        loc['span'] = dict(start=2, end=3)
        other = deepcopy(basis['findings'][0])
        other['finding_id'] = str(uuid4())
        other['locations'][0]['span'] = dict(start=3, end=4)
        basis['findings'].append(other)
        basis['profile']['finding_ids'].append(other['finding_id'])
        self.source.overrides['bundle'] = basis
        plan = self.build()
        self.assertEqual(plan['status'], 'ready')
        self.assertTrue(self.check(plan)['valid'])

    def test_formula_channel_requires_whole_cell(self):
        import io
        from openpyxl import Workbook
        book = Workbook()
        book.active.append(['header'])
        book.active.append(['=HYPERLINK("https://example.invalid","a@example.invalid")'])
        stream = io.BytesIO()
        book.save(stream)
        parsed = self.fixture.parse_bytes(stream.getvalue(), format='xlsx')
        self.repo = MemoryReviewRepository()
        self.review = ReviewService(self.repo, self.access)
        self.register(parsed)
        self.source.review, self.source.parsed = self.review, parsed
        self.confirm_all()
        plan = self.build()
        self.assertEqual(plan['status'], 'ready')
        self.assertEqual(plan['operations'][0]['type'], 'mask_cell')
        self.assertEqual(plan['operations'][0]['target']['channel'], 'formula')
        self.assertTrue(self.check(plan)['valid'])
