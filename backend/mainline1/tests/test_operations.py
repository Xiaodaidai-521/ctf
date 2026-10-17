"""Backend-only workflow tests over synthetic assets and the real rule/parser paths."""
from copy import deepcopy
from dataclasses import asdict
from io import BytesIO
import hashlib
import unittest
from threading import Event, Thread
from uuid import uuid4

from mainline1.cleanup import CleanupPolicy
from mainline1.comparison import compare_bundles
from mainline1.operations import Operations
from mainline1.parsing import AssetRef, InputError, Limits, ParserConfig, fingerprint
from mainline1.review import MemoryReviewRepository, ReviewPrincipal
from mainline1.tests import test_rules
from mainline1.tests.test_review import AccessDouble


class Assets:
    def __init__(self):
        self.rows = {}
        self.created = []

    def add(self, asset_id, version_id, content, fmt='csv'):
        ref = AssetRef(version_id, 'test-domain', 'sha256:' + hashlib.sha256(content).hexdigest(),
                       fmt, len(content), 'private:synthetic:' + version_id)
        self.rows[version_id] = (asset_id, ref, content)
        return ref

    def resolve(self, principal, version_id, operation):
        try:
            asset_id, ref, _ = self.rows[version_id]
        except KeyError:
            raise InputError('OBJECT_NOT_FOUND') from None
        return asset_id, ref

    def open_version(self, ref, *, principal, domain_id):
        for _, candidate, content in self.rows.values():
            if candidate == ref:
                return BytesIO(content)
        raise InputError('OBJECT_NOT_FOUND')

    def create_version(self, principal, asset_id, content, fmt):
        version = str(uuid4())
        self.add(asset_id, version, content, fmt)
        self.created.append(version)
        return version


class Owner:
    def __init__(self):
        self.calls = []

    def invalidate(self, principal, asset, *, reason, audit_ref):
        self.calls.append((principal.actor_id, asset['asset_version_id'], reason, audit_ref))
        return True


class BlockingAssets(Assets):
    def __init__(self):
        super().__init__()
        self.entered, self.release = Event(), Event()

    def open_version(self, ref, *, principal, domain_id):
        self.entered.set()
        if not self.release.wait(5):
            raise TimeoutError('synthetic timeout')
        return super().open_version(ref, principal=principal, domain_id=domain_id)


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_rules.RuleTests()
        self.fixture.setUp()
        self.actor = ReviewPrincipal(1, 'test-domain', 'test')
        self.asset_store = Assets()
        self.repo = MemoryReviewRepository()
        self.access = AccessDouble()
        self.content = b'field\nalice@example.invalid\n'
        self.ref = self.asset_store.add(test_rules.A, test_rules.V, self.content)
        self.parsed = self.fixture.parse_bytes(self.content)
        self.ops = Operations(self.repo, self.access, self.asset_store, clock=lambda: 1000,
            cleanup_policy=CleanupPolicy(retention_seconds=10))

    def scan(self, version=test_rules.V, key='scan-1', base=None, content=None):
        if content is not None:
            version = str(uuid4())
            ref = self.asset_store.add(test_rules.A, version, content)
            from mainline1.parsing import parse_table
            parsed = parse_table(content, ref, config=ParserConfig())
            context = self.fixture.context(parsed)
        else:
            if version == test_rules.V:
                parsed = self.parsed
            else:
                from mainline1.parsing import parse_table
                ref = self.asset_store.rows[version][1]
                parsed = parse_table(self.asset_store.rows[version][2], ref, config=ParserConfig())
            context = self.fixture.context(parsed)
        if version != test_rules.V:
            context = self.fixture.context(parsed, asset_version_id=version)
        result = self.ops.create_scan(self.actor, version, configuration=self.fixture.config,
            context=context, idempotency_key=key, config=ParserConfig(), limits=Limits(),
            scope=parsed.scope, base_profile_id=base, semantic_required=False)
        return self.ops.execute_one(self.actor, result['scan_id'])

    def bundle(self, profile_id):
        return self.repo.read(lambda s: deepcopy(s.bundles[profile_id]))

    def test_create_version_checks_asset_permission_before_owner_call(self):
        self.access.denied.add((self.actor.actor_id, 'create_version'))
        with self.assertRaises(InputError) as caught:
            self.ops.create_version(self.actor, test_rules.A, b'field\nvalue\n', 'csv')
        self.assertEqual(caught.exception.code, 'OBJECT_NOT_FOUND')
        self.assertEqual(self.asset_store.created, [])
        self.access.denied.remove((self.actor.actor_id, 'create_version'))
        version = self.ops.create_version(self.actor, test_rules.A, b'field\nvalue\n', 'csv')
        self.assertIn(version, self.asset_store.rows)

    def test_scan_task_is_bound_to_creating_actor(self):
        created = self.ops.create_scan(self.actor, test_rules.V, configuration=self.fixture.config,
            context=self.fixture.context(self.parsed), idempotency_key='private-scan', scope=self.parsed.scope,
            semantic_required=False)
        other = ReviewPrincipal(2, 'test-domain', 'test')
        with self.assertRaises(InputError) as caught:
            self.ops.get_scan(other, created['scan_id'])
        self.assertEqual(caught.exception.code, 'OBJECT_NOT_FOUND')
        with self.assertRaises(InputError) as caught:
            self.ops.cancel_scan(other, created['scan_id'])
        self.assertEqual(caught.exception.code, 'OBJECT_NOT_FOUND')

    def test_create_execute_query_and_private_result_access(self):
        created = self.ops.create_scan(self.actor, test_rules.V, configuration=self.fixture.config,
            context=self.fixture.context(self.parsed), idempotency_key='first', scope=self.parsed.scope,
            semantic_required=False)
        self.assertEqual(created['status'], 'queued')
        finished = self.ops.execute_one(self.actor, created['scan_id'])
        self.assertEqual(finished['status'], 'succeeded')
        self.assertEqual(finished['quality'], 'complete')
        self.assertEqual(self.ops.get_scan(self.actor, created['scan_id'])['profile_id'], finished['profile_id'])
        payload = self.ops.read_private_parsed(self.actor, created['scan_id'])
        self.assertEqual(len(payload['cells']), 1)

    def test_idempotency_and_active_concurrency(self):
        first = self.ops.create_scan(self.actor, test_rules.V, configuration=self.fixture.config,
            context=self.fixture.context(self.parsed), idempotency_key='same', scope=self.parsed.scope,
            semantic_required=False)
        replay = self.ops.create_scan(self.actor, test_rules.V, configuration=self.fixture.config,
            context=self.fixture.context(self.parsed), idempotency_key='same', scope=self.parsed.scope,
            semantic_required=False)
        self.assertEqual(first, replay)
        with self.assertRaises(InputError) as caught:
            self.ops.create_scan(self.actor, test_rules.V, configuration=self.fixture.config,
                context=self.fixture.context(self.parsed), idempotency_key='same', scope=self.parsed.scope,
                semantic_required=True)
        self.assertEqual(caught.exception.code, 'IDEMPOTENCY_CONFLICT')
        self.ops.cancel_scan(self.actor, first['scan_id'])
        self.assertEqual(self.ops.get_scan(self.actor, first['scan_id'])['status'], 'cancelled')
        with self.assertRaises(InputError) as caught:
            self.ops.execute_one(self.actor, first['scan_id'])
        self.assertEqual(caught.exception.code, 'TASK_NOT_QUEUED')

    def test_workflow_pagination_and_private_acl(self):
        finished = self.scan(content=b'field\nalice@example.invalid\nbob@example.invalid\n', key='pages')
        first = self.ops.list_findings(self.actor, finished['profile_id'], limit=1)
        second = self.ops.list_findings(self.actor, finished['profile_id'], limit=1,
                                        offset=first['next_offset'])
        self.assertEqual(len(first['items']), 1)
        self.assertEqual(len(second['items']), 1)
        self.assertNotEqual(first['items'][0]['finding_id'], second['items'][0]['finding_id'])
        self.assertIsNone(second['next_offset'])
        self.assertEqual(first['items'][0]['sample'], '[REDACTED]')
        self.access.denied.add((self.actor.actor_id, 'view_source'))
        with self.assertRaises(InputError) as denied:
            self.ops.read_private_parsed(self.actor, finished['scan_id'])
        self.assertEqual(denied.exception.code, 'OBJECT_NOT_FOUND')
        self.assertEqual(self.ops.get_scan(self.actor, finished['scan_id'])['status'], 'succeeded')
        self.access.denied.add((self.actor.actor_id, 'read'))
        with self.assertRaises(InputError) as denied:
            self.ops.list_findings(self.actor, finished['profile_id'], limit=1, offset=1)
        self.assertEqual(denied.exception.code, 'OBJECT_NOT_FOUND')

    def test_failed_scan_can_be_retried_with_new_attempt(self):
        bad = self.ops.create_scan(self.actor, test_rules.V, configuration=self.fixture.config,
            context=self.fixture.context(self.parsed), idempotency_key='bad', scope=self.parsed.scope,
            semantic_required=False)
        self.asset_store.rows[test_rules.V] = (test_rules.A, self.ref, b'field\n"unterminated\n')
        bad = self.ops.execute_one(self.actor, bad['scan_id'])
        self.assertEqual(bad['status'], 'failed')
        retried = self.ops.retry_scan(self.actor, bad['scan_id'], expected_attempt=1, idempotency_key='retry-1')
        self.assertEqual(retried['status'], 'queued')
        failed_again = self.ops.execute_one(self.actor, bad['scan_id'])
        self.assertEqual(failed_again['status'], 'failed')
        with self.assertRaises(InputError) as caught:
            self.ops.retry_scan(self.actor, bad['scan_id'], expected_attempt=2, idempotency_key='retry-2')
        self.assertEqual(caught.exception.code, 'RETRY_LIMIT')

    def test_rescan_new_version_requires_new_run_and_does_not_inherit_moved_finding(self):
        first = self.scan(key='initial')
        old_id = first['profile_id']
        old_bundle = self.bundle(old_id)
        finding = old_bundle['findings'][0]
        self.ops.submit_review(self.actor, base_profile_id=old_id, expected_state_version=1,
            idempotency_key='review', action='confirm', finding_id=finding['finding_id'], reason='synthetic')
        # The successor is the only current head in this synthetic scope.
        current = self.repo.read(lambda s: next(pid for pid, app in s.applicability.items() if app['status'] == 'current'))
        newer = self.scan(content=b'field\nother@example.invalid\n', key='rescan', base=current)
        self.assertNotEqual(newer['scan_id'], first['scan_id'])
        new_bundle = self.bundle(newer['profile_id'])
        self.assertIn('PRIOR_REVIEW_RECHECK_REQUIRED', new_bundle['profile']['limitations'])
        self.assertEqual(new_bundle['profile']['review_status'], 'pending')

    def test_same_input_rescan_inherits_manual_conclusion_only_with_exact_binding(self):
        first = self.scan(key='base')
        old = self.bundle(first['profile_id'])
        finding = old['findings'][0]
        review = self.ops.submit_review(self.actor, base_profile_id=first['profile_id'], expected_state_version=1,
            idempotency_key='review-same', action='confirm', finding_id=finding['finding_id'], reason='synthetic')
        newer = self.scan(key='same-input-rescan', base=review['successor_profile_id'])
        bundle = self.bundle(newer['profile_id'])
        self.assertEqual(bundle['snapshot']['inherited_profile_id'], review['successor_profile_id'])
        self.assertEqual(bundle['profile']['review_status'], 'completed')
        self.assertTrue(all(f['judgment'] == 'determined' for f in bundle['findings']))

    def test_compare_reports_category_change_and_movement_as_unmatched(self):
        first = self.scan(key='compare-a')
        before = self.bundle(first['profile_id'])
        after = deepcopy(before)
        after['profile']['profile_id'] = str(uuid4())
        after['profile']['scan_id'] = str(uuid4())
        after['findings'][0]['finding_id'] = str(uuid4())
        after['findings'][0]['category_id'] = 'ip_address'
        changed = compare_bundles(before, after)
        self.assertEqual(len(changed['category_changes']), 1)
        moved = deepcopy(after)
        moved['findings'][0]['locations'][0]['row'] = 99
        moved['findings'][0]['finding_id'] = str(uuid4())
        moved_result = compare_bundles(before, moved)
        self.assertIn(before['findings'][0]['finding_id'], moved_result['unmatched'])
        self.assertIn(moved['findings'][0]['finding_id'], moved_result['unmatched'])
        self.assertEqual(moved_result['added'], [])
        self.assertEqual(moved_result['disappeared'], [])
        moved['findings'][0]['locations'][0].update(row=2, column=99)
        self.assertEqual(len(compare_bundles(before, moved)['unmatched']), 2)
        absent = deepcopy(before)
        absent['findings'], absent['profile']['finding_ids'] = [], []
        self.assertEqual(compare_bundles(before, absent)['disappeared'], before['profile']['finding_ids'])
        self.assertEqual(compare_bundles(absent, before)['added'], before['profile']['finding_ids'])

    def test_policy_regrade_requires_compatible_evidence_and_creates_new_profile(self):
        first = self.scan(key='grade')
        data = deepcopy(self.fixture.config.data())
        data['policy']['version'] = 'synthetic-policy-v2'
        data['policy']['categories'][0]['protection_level'] = 'L2'
        config = self.fixture.config_from(data)
        profile = self.ops.regrade(self.actor, first['profile_id'], config,
            expected_state_version=1, idempotency_key='grade-1')
        self.assertNotEqual(profile['profile_id'], first['profile_id'])
        self.assertEqual(profile['policy_version'], 'synthetic-policy-v2')
        incompatible = deepcopy(self.fixture.config.data())
        incompatible['rules'][0]['implementation'] = 'ipv4_v1'
        incompatible['policy']['content_hash'] = fingerprint({k: v for k, v in incompatible['policy'].items() if k != 'content_hash'})
        with self.assertRaises(InputError) as caught:
            self.ops.regrade(self.actor, profile['profile_id'], self.fixture.config_from(incompatible),
                expected_state_version=1, idempotency_key='grade-incompatible')
        self.assertEqual(caught.exception.code, 'RESCAN_REQUIRED')

    def test_cleanup_preview_protects_active_and_requires_approved_policy(self):
        first = self.scan(key='cleanup')
        self.repo.atomic(lambda state: state.resources['parsed:' + first['scan_id']].update(expires_at=1))
        preview = self.ops.cleanup_preview(self.actor)
        self.assertEqual(preview['candidate_count'], 1)
        self.assertEqual(preview['blocked'], [])
        with self.assertRaises(InputError) as caught:
            self.ops.cleanup_execute(self.actor, dry_run=False, reason='RETENTION_EXPIRED', preview_hash=preview['preview_hash'])
        self.assertEqual(caught.exception.code, 'CLEANUP_NOT_APPROVED')
        self.assertTrue(self.ops.cleanup_execute(self.actor, dry_run=True)['deleted'] == [])
        approved = Operations(self.repo, self.access, self.asset_store, clock=lambda: 1000,
            cleanup_policy=CleanupPolicy(approved=True, retention_seconds=10))
        approved_preview = approved.cleanup_preview(self.actor)
        deleted = approved.cleanup_execute(self.actor, dry_run=False, reason='RETENTION_EXPIRED',
                                           preview_hash=approved_preview['preview_hash'])
        self.assertEqual(deleted['deleted'], ['parsed:' + first['scan_id']])
        with self.assertRaises(InputError) as caught:
            approved.read_private_parsed(self.actor, first['scan_id'])
        self.assertEqual(caught.exception.code, 'ARTIFACT_DELETED')

    def test_cleanup_blocks_active_task_and_scope_escape(self):
        created = self.ops.create_scan(self.actor, test_rules.V, configuration=self.fixture.config,
            context=self.fixture.context(self.parsed), idempotency_key='active', scope=self.parsed.scope,
            semantic_required=False)
        self.repo.atomic(lambda state: state.resources.update({'r': dict(resource_id='r', kind='temporary_parse',
            scope=['test-domain', 'test', None], asset={'asset_id': test_rules.A}, run_id=created['scan_id'],
            created_at=0, expires_at=1, hold=False, active_refs=[], deleted=False, payload={'secret': 'synthetic'})}))
        preview = self.ops.cleanup_preview(self.actor)
        self.assertEqual(preview['candidate_count'], 0)
        self.assertIn('TASK_ACTIVE', {row['reason_code'] for row in preview['blocked']})
        with self.assertRaises(InputError) as caught:
            self.ops.cleanup_preview(self.actor, scope={'domain_id': 'other'})
        self.assertEqual(caught.exception.code, 'OBJECT_NOT_FOUND')

    def test_expired_cache_and_reference_changes_are_rechecked(self):
        finished = self.scan(key='cache')
        def seed(state):
            template = deepcopy(state.resources['parsed:' + finished['scan_id']])
            for key in ('expired-cache', 'held-cache', 'unknown-cache'):
                row = deepcopy(template)
                row.update(resource_id=key, kind='detection_cache', profile_ids=[],
                           created_at=0, expires_at=1)
                state.resources[key] = row
            state.resources['held-cache']['active_refs'] = ['private:active-consumer']
            state.resources['unknown-cache'].update(created_at=None, expires_at=None)
        self.repo.atomic(seed)
        ops = Operations(self.repo, self.access, self.asset_store, clock=lambda: 1000,
            cleanup_policy=CleanupPolicy(approved=True, retention_seconds=10))
        preview = ops.cleanup_preview(self.actor)
        self.assertEqual([r['resource_id'] for r in preview['candidates']], ['expired-cache'])
        self.assertTrue({'REFERENCE_ACTIVE', 'RETENTION_UNKNOWN'} <=
                        {r['reason_code'] for r in preview['blocked']})
        self.repo.atomic(lambda s: s.resources['expired-cache'].update(active_refs=['private:new-consumer']))
        with self.assertRaises(InputError) as stale:
            ops.cleanup_execute(self.actor, dry_run=False, reason='RETENTION_EXPIRED',
                                preview_hash=preview['preview_hash'])
        self.assertEqual(stale.exception.code, 'CLEANUP_PREVIEW_STALE')
        self.assertFalse(self.repo.read(lambda s: s.resources['expired-cache']['deleted']))
        self.repo.atomic(lambda s: s.resources['expired-cache'].update(active_refs=[]))
        preview = ops.cleanup_preview(self.actor)
        result = ops.cleanup_execute(self.actor, dry_run=False, reason='RETENTION_EXPIRED',
                                     preview_hash=preview['preview_hash'])
        self.assertEqual(result['deleted'], ['expired-cache'])
        row = self.repo.read(lambda s: s.resources['expired-cache'])
        self.assertTrue(row['deleted'])
        self.assertNotIn('payload', row)
        self.assertFalse(self.repo.read(lambda s: s.resources['held-cache']['deleted']))
        self.assertEqual(self.repo.read(lambda s: s.cleanup_audit[-1]['deleted_ids']), ['expired-cache'])

    def test_owner_invalidation_is_delegated_and_audited(self):
        owner = Owner()
        asset = dict(asset_id=test_rules.A, asset_version_id=test_rules.V,
                     **asdict(self.ref))
        approved = Operations(self.repo, self.access, self.asset_store, clock=lambda: 1000,
            cleanup_policy=CleanupPolicy(approved=True, retention_seconds=10))
        result = approved.request_asset_invalidation(self.actor,
            asset, owner, reason='AUTHORIZED_OWNER_REQUEST')
        self.assertEqual(result['status'], 'requested')
        self.assertEqual(len(owner.calls), 1)
        self.assertEqual(self.repo.read(lambda s: len(s.cleanup_audit)), 1)

    def test_running_cancel_is_observed_before_publication(self):
        assets = BlockingAssets()
        ref = assets.add(test_rules.A, test_rules.V, self.content)
        ops = Operations(self.repo, self.access, assets, clock=lambda: 1000)
        created = ops.create_scan(self.actor, ref.version_id, configuration=self.fixture.config,
            context=self.fixture.context(self.parsed), idempotency_key='running-cancel', scope=self.parsed.scope,
            semantic_required=False)
        output = []
        worker = Thread(target=lambda: output.append(ops.execute_one(self.actor, created['scan_id'])))
        worker.start()
        self.assertTrue(assets.entered.wait(2))
        self.assertEqual(ops.cancel_scan(self.actor, created['scan_id'])['status'], 'running')
        assets.release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(output[0]['status'], 'cancelled')
        self.assertIsNone(output[0]['profile_id'])

    def test_cleanup_tombstone_invalidates_profile_applicability(self):
        first = self.scan(key='clean-tombstone')
        self.repo.atomic(lambda state: state.resources['parsed:' + first['scan_id']].update(expires_at=1))
        cleanup = Operations(self.repo, self.access, self.asset_store, clock=lambda: 1000,
            cleanup_policy=CleanupPolicy(approved=True, retention_seconds=10))
        preview = cleanup.cleanup_preview(self.actor)
        with self.assertRaises(InputError) as stale:
            cleanup.cleanup_execute(self.actor, dry_run=False, reason='RETENTION_EXPIRED',
                                    preview_hash=preview['preview_hash'] + 'stale')
        self.assertEqual(stale.exception.code, 'CLEANUP_PREVIEW_STALE')
        cleanup.cleanup_execute(self.actor, dry_run=False, reason='RETENTION_EXPIRED',
                                preview_hash=preview['preview_hash'])
        app = cleanup.review.get_profile_applicability(self.actor, first['profile_id'])
        self.assertEqual(app['status'], 'unverifiable_deleted')
        self.assertEqual(app['state_version'], 2)
