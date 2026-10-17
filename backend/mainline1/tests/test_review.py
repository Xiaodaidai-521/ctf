"""Real rule findings; memory repository/ACL/event doubles, no production claims."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from threading import Barrier
import unittest
from uuid import uuid4

import jsonschema

from mainline1.parsing import InputError
from mainline1.review import MemoryReviewRepository, ReviewPrincipal, ReviewService, ReviewOutbox, ReviewConflict
from mainline1.tests import test_rules


class AccessDouble:
    def __init__(self):
        self.denied = set()

    def allowed(self, principal, asset, operation):
        return principal.actor_id in (1, 2) and (principal.actor_id, operation) not in self.denied


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_rules.RuleTests()
        self.fixture.setUp()
        self.parsed = self.fixture.parsed('😀 a@example.invalid 192.0.2.1 4111111111111111 unrecognized')
        self.result = self.fixture.scan(self.parsed)
        self.repo, self.access = MemoryReviewRepository(), AccessDouble()
        self.service = ReviewService(self.repo, self.access)
        self.actor = ReviewPrincipal(1, 'test-domain', 'test')
        self.pid = self.service.register(self.actor, self.result, self.parsed)
        self.findings = self.result.data()['findings']
        self.email = next(f for f in self.findings if 'email' in f['category_id'])
        self.card = next(f for f in self.findings if 'L3' == self.category(f['category_id'])['protection_level'])
        self.schema = json.loads((Path(__file__).resolve().parents[3] / 'docs/mainline1/contracts/schema.json').read_text(encoding='utf-8'))

    def category(self, category_id):
        return next(c for c in self.fixture.config.data()['policy']['categories'] if c['category_id'] == category_id)

    def code(self, expected, fn, *args, **kwargs):
        with self.assertRaises(InputError) as error:
            fn(*args, **kwargs)
        self.assertEqual(error.exception.code, expected)

    def submit(self, **changes):
        request = dict(base_profile_id=self.pid, expected_state_version=1, idempotency_key='one',
                       action='confirm', reason='synthetic evidence reviewed', finding_id=self.email['finding_id'])
        return self.service.submit_review(self.actor, **dict(request, **changes))

    def snapshot(self):
        return self.repo.atomic(lambda s: s)

    def validate(self, kind, value):
        jsonschema.Draft202012Validator({'$ref': '#/$defs/' + kind, '$defs': self.schema['$defs']},
                                       format_checker=jsonschema.FormatChecker()).validate(value)

    def test_confirm_preserves_original_and_source_provenance(self):
        original = self.snapshot().bundles[self.pid]
        record = self.submit()
        state = self.snapshot()
        successor = state.bundles[record['successor_profile_id']]
        manual = next(f for f in successor['findings'] if f['source_type'] == 'manual')
        self.assertEqual(original, state.bundles[self.pid])
        self.assertEqual(manual['source_finding_ids'], [self.email['finding_id']])
        self.assertEqual((manual['created_by'], manual['detector_version'], manual['detector_id']), (1, None, None))
        self.assertEqual(record['conclusion'], 'confirmed')
        self.assertEqual(record['workflow_status'], 'completed')
        for kind, value in [('ReviewRecord', record), ('Finding', manual), ('SensitivityProfile', successor['profile'])]:
            self.validate(kind, value)

    def test_correct_recalculates_level_without_quality_upgrade(self):
        record = self.submit(action='correct', finding_id=self.card['finding_id'], category_id=self.email['category_id'])
        profile = self.service.get_profile(self.actor, record['successor_profile_id'])
        self.assertEqual(profile['protection_level'], 'L2')
        self.assertEqual(profile['quality'], 'partial')
        self.assertEqual(profile['coverage'], self.result.data()['profile']['coverage'])
        self.assertEqual(self.service.get_profile(self.actor, self.pid)['protection_level'], 'L3')

    def test_false_positive_removes_only_successor_reference(self):
        record = self.submit(action='false_positive', finding_id=self.card['finding_id'])
        self.assertEqual(record['conclusion'], 'false_positive')
        self.assertIsNone(record['after_category'])
        self.assertNotIn(self.card['finding_id'], self.service.get_profile(self.actor, record['successor_profile_id'])['finding_ids'])
        self.assertIn(self.card['finding_id'], self.service.get_profile(self.actor, self.pid)['finding_ids'])

    def test_manual_addition_and_same_asset_old_applicability(self):
        location = dict(self.email['locations'][0], kind='cell', span=None)
        record = self.submit(action='add_manual', finding_id=None, category_id=self.email['category_id'], locations=[location])
        state = self.snapshot()
        f = next(f for f in state.bundles[record['successor_profile_id']]['findings'] if f['review_id'] == record['review_id'])
        self.assertEqual(f['source_type'], 'manual')
        self.assertEqual(f['source_finding_ids'], [])
        self.validate('Finding', f)
        app = self.service.get_profile_applicability(self.actor, self.pid)
        self.validate('ProfileApplicability', app)
        self.assertEqual((app['status'], app['state_version'], app['historical_audit_available'], app['usable_for_new_decision']),
                         ('superseded', 2, True, False))
        self.assertEqual(state.bundles[self.pid]['profile']['asset'], state.bundles[record['successor_profile_id']]['profile']['asset'])
        event = next(iter(state.outbox.values()))['event']
        self.validate('ProfileChangedEvent', event)
        self.assertNotIn('synthetic evidence', json.dumps(event))

    def test_idempotency_replay_and_changed_body_conflict(self):
        first = self.submit()
        self.assertEqual(first, self.submit())
        self.code('IDEMPOTENCY_CONFLICT', self.submit, reason='different')
        self.assertEqual(len(self.snapshot().reviews), 1)
        self.assertEqual(len(self.snapshot().outbox), 1)

    def test_acl_rechecked_for_idempotency_and_each_query(self):
        record = self.submit()
        self.access.denied.add((1, 'review'))
        self.code('OBJECT_NOT_FOUND', self.submit)
        self.access.denied.add((1, 'read'))
        self.code('OBJECT_NOT_FOUND', self.service.get_profile, self.actor, self.pid)
        self.code('OBJECT_NOT_FOUND', self.service.get_profile_applicability, self.actor, self.pid)
        self.code('OBJECT_NOT_FOUND', self.service.list_findings, self.actor, self.pid)
        self.access.denied.add((1, 'read_review'))
        self.code('OBJECT_NOT_FOUND', self.service.get_review, self.actor, record['review_id'])

    def test_object_domain_environment_evaluation_and_actor_denied(self):
        for actor in [replace(self.actor, actor_id=3), replace(self.actor, domain_id='other'),
                      replace(self.actor, environment='production'), replace(self.actor, evaluation_run_id=str(uuid4()))]:
            self.code('OBJECT_NOT_FOUND', self.service.list_findings, actor, self.pid)
            self.code('OBJECT_NOT_FOUND', self.service.register, actor, self.result, self.parsed)
        self.code('OBJECT_NOT_FOUND', self.service.get_profile, self.actor, str(uuid4()))

    def test_two_reviewers_one_successor(self):
        barrier = Barrier(2)
        def submit(actor):
            barrier.wait(timeout=5)
            try:
                return self.service.submit_review(replace(self.actor, actor_id=actor), base_profile_id=self.pid,
                    expected_state_version=1, idempotency_key='race', action='confirm', reason='synthetic', finding_id=self.email['finding_id'])
            except ReviewConflict as exc:
                return exc
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(submit, [1, 2]))
        won = next(v for v in values if isinstance(v, dict))
        lost = next(v for v in values if isinstance(v, ReviewConflict))
        self.assertEqual(lost.latest_profile_id, won['successor_profile_id'])
        self.assertEqual(len(self.snapshot().reviews), 1)
        self.assertEqual(len(self.snapshot().bundles), 2)

    def test_wrong_expected_version_conflicts_without_writes(self):
        before = self.snapshot()
        self.code('REVIEW_VERSION_CONFLICT', self.submit, expected_state_version=2)
        self.assertEqual(before, self.snapshot())

    def test_invalid_manual_coordinates_and_categories_atomic(self):
        before = self.snapshot()
        for changes in [dict(row=100), dict(channel='cached'), dict(span={'start': -1, 'end': 2}),
                        dict(span={'start': 0, 'end': 1000}), dict(span={'start': True, 'end': 2})]:
            self.code('LOCATION_MISMATCH', self.submit, action='add_manual', finding_id=None,
                      category_id=self.email['category_id'], locations=[dict(self.email['locations'][0], **changes)])
        self.code('CATEGORY_INVALID', self.submit, action='correct', category_id='invented')
        self.code('REVIEW_INPUT_INVALID', self.submit, reason=' ')
        self.assertEqual(before, self.snapshot())

    def test_unicode_manual_span_source_bounds(self):
        # A codepoint span can address one emoji; UTF-16 offsets cannot be substituted.
        location = deepcopy(self.email['locations'][0])
        location['span'] = dict(start=0, end=1)
        record = self.submit(action='add_manual', finding_id=None, category_id=self.email['category_id'], locations=[location])
        self.assertEqual(record['conclusion'], 'manual_added')

    def test_pending_pagination_fixed_to_old_profile_and_masking(self):
        first = self.service.list_findings(self.actor, self.pid, limit=1)
        self.submit()
        second = self.service.list_findings(self.actor, self.pid, offset=first['next_offset'], limit=1)
        self.assertNotEqual(first['items'][0]['finding_id'], second['items'][0]['finding_id'])
        self.assertNotIn('example.invalid', json.dumps([first, second]))
        self.assertEqual(len(self.service.list_findings(self.actor, self.pid)['items']), 3)

    def test_other_scopes_conservatively_invalidated(self):
        from mainline1.parsing import AssetRef, parse_table
        # Reuse identical original bytes by generating the fixture's CSV format.
        import csv, io
        stream = io.StringIO(newline='')
        csv.writer(stream).writerows([['field'], ['😀 a@example.invalid 192.0.2.1 4111111111111111 unrecognized']])
        raw = stream.getvalue().encode()
        ref = AssetRef(test_rules.V, 'test-domain', self.parsed.input_content_hash, 'csv', len(raw), 'private:input')
        # Scope including header is distinct while retaining the same fixed asset.
        from mainline1.parsing import ParserConfig
        parsed = parse_table(raw, ref, config=ParserConfig(include_header=True))
        other = self.fixture.scan(parsed, scan_id=str(uuid4()), applicability_ref=str(uuid4()))
        pid = self.service.register(self.actor, other, parsed)
        self.submit(action='add_manual', finding_id=None, category_id=self.email['category_id'], locations=self.email['locations'])
        app = self.service.get_profile_applicability(self.actor, pid)
        self.assertEqual(app['status'], 'reevaluation_required')
        self.assertEqual(len(self.snapshot().outbox), 2)
        self.code('PROFILE_REEVALUATION_REQUIRED', self.submit, base_profile_id=pid, expected_state_version=2, idempotency_key='other')

    def test_no_automatic_reuse_after_input_change_or_newer_review(self):
        record = self.submit()
        pid = record['successor_profile_id']
        self.assertTrue(self.service.review_reuse_eligibility(self.actor, record['review_id'], pid)['eligible'])
        # New real scan of changed bytes at identical coordinates must not inherit.
        import hashlib
        from mainline1.parsing import AssetRef, parse_table
        from mainline1.classification import BusinessContext
        raw, version = b'field\nb@example.invalid\n', str(uuid4())
        digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        parsed = parse_table(raw, AssetRef(version, 'test-domain', digest, 'csv', len(raw), 'private:new-version'))
        context = BusinessContext.create(meta=self.fixture.meta, context_id=str(uuid4()), version=1,
            asset_version_id=version, scope_hash=parsed.scope_hash, scenario='synthetic')
        candidate = self.fixture.scan(parsed, scan_id=str(uuid4()), applicability_ref=str(uuid4()), context=context,
            asset=dict(asset_id=test_rules.A, asset_version_id=version, content_hash=digest))
        candidate_id = self.service.register(self.actor, candidate, parsed)
        reuse = self.service.review_reuse_eligibility(self.actor, record['review_id'], candidate_id)
        self.assertFalse(reuse['eligible'])
        self.assertFalse(reuse['automatic_inheritance'])
        self.submit(base_profile_id=pid, idempotency_key='second', finding_id=self.card['finding_id'])
        self.assertFalse(self.service.review_reuse_eligibility(self.actor, record['review_id'], pid)['eligible'])

    def test_notifications_not_connected_failure_retry_dedup_and_dead_letter(self):
        self.submit()
        self.assertEqual(ReviewOutbox(self.repo).dispatch()['status'], 'not_connected')
        self.assertEqual(next(iter(self.snapshot().outbox.values()))['attempts'], 0)
        class Sink:
            def __init__(self):
                self.seen, self.calls = set(), 0
            def publish(self, event):
                self.calls += 1
                self.seen.add(event['event_id'])
                if self.calls == 1:
                    raise RuntimeError('private transport detail')  # accepted but acknowledgement lost
                return True
        sink = Sink()
        dispatcher = ReviewOutbox(self.repo, sink)
        self.assertEqual(dispatcher.dispatch()['failed'], 1)
        self.assertEqual(dispatcher.dispatch()['acknowledged'], 1)
        self.assertEqual(dispatcher.dispatch()['acknowledged'], 0)
        self.assertEqual((sink.calls, len(sink.seen)), (2, 1))
        self.assertNotIn('private transport detail', repr(self.snapshot()))
        record = next(iter(self.snapshot().reviews.values()))
        self.submit(base_profile_id=record['successor_profile_id'], idempotency_key='two', finding_id=self.card['finding_id'])
        class Broken:
            def publish(self, event):
                return False
        bad = ReviewOutbox(self.repo, Broken(), max_attempts=1)
        bad.dispatch()
        self.assertEqual(bad.dispatch()['failed'], 0)
        self.assertIn('dead_letter', [r['status'] for r in self.snapshot().outbox.values()])
        self.assertEqual(len(self.snapshot().reviews), 2)

    def test_repository_failure_rolls_back_history_head_and_outbox(self):
        before = self.snapshot()
        original = self.service._event
        def fail(state, app):
            original(state, app)
            raise RuntimeError('simulated storage failure')
        self.service._event = fail
        with self.assertRaises(RuntimeError):
            self.submit()
        self.assertEqual(before, self.snapshot())

    def test_returns_cannot_mutate_history_and_draft_not_new_authorization(self):
        profile = self.service.get_profile(self.actor, self.pid)
        profile['finding_ids'].clear()
        self.assertEqual(len(self.service.get_profile(self.actor, self.pid)['finding_ids']), 3)
        self.assertFalse(self.service.get_profile_applicability(self.actor, self.pid)['usable_for_new_decision'])

    def test_combination_rejected_instead_of_losing_protection(self):
        self.repo.atomic(lambda s: s.bundles[self.pid]['profile']['combination_finding_ids'].append('test-only'))
        self.code('COMBINATION_REVIEW_UNSUPPORTED', self.submit)

    def test_rejected_request_has_no_false_positive_record(self):
        self.code('REVIEW_INPUT_INVALID', self.submit, action='reject')
        self.assertEqual(len(self.snapshot().reviews), 0)

    def test_successive_reviews_keep_state_history_monotonic(self):
        one = self.submit()
        two = self.submit(base_profile_id=one['successor_profile_id'], idempotency_key='two', finding_id=self.card['finding_id'])
        self.assertEqual(self.service.get_profile(self.actor, two['successor_profile_id'])['supersedes_profile_id'], one['successor_profile_id'])
        self.assertEqual([a['state_version'] for a in self.snapshot().state_history if a['profile_id'] == self.pid], [1, 2])
        self.assertEqual(self.service.get_review(self.actor, one['review_id']), one)


if __name__ == '__main__':
    unittest.main()
