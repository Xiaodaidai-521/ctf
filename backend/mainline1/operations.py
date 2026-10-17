"""Internal backend-only workflow over the existing task state machine/ledger.

Asset owner and ACL are injected trusted ports. No HTTP publication, unmanaged
threads or production policy activation. The worker is invoked explicitly.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import time
from uuid import UUID, uuid4, uuid5

from .classification import BusinessContext, RuleConfiguration, identifier, require
from .comparison import compare_bundles, exact_review_reuse, regrade_configuration
from .cleanup import CleanupPolicy, CleanupService
from .parsing import AssetRef, InputError, Limits, ParserConfig, Scope, Selection, parse_table, read_private, fingerprint
from .review import ReviewPrincipal, ReviewService, ReviewState, head_key, partition
from .rules import scan_rules
from .tasks import ParseTasks, dump_run, restore_run
from .worker import parse_snapshot


class StateRunRepository:
    """Task repository on a private transaction view; never use outside its lock."""
    def __init__(self, state):
        self.state = state

    def create_unique(self, candidate):
        key = fingerprint(list(candidate.key))
        if key not in self.state.workflow_keys:
            candidate = replace(candidate, result_kind='scan_result')
            self.state.workflow_keys[key] = candidate.run_id
            self.state.workflows[candidate.run_id] = dict(run=dump_run(candidate), profile_id=None, error_code=None)
        return self.get(self.state.workflow_keys[key])

    def get(self, run_id):
        require(run_id in self.state.workflows, 'OBJECT_NOT_FOUND')
        return restore_run(self.state.workflows[run_id]['run'])

    def compare_and_swap(self, expected_revision, replacement):
        old = self.get(replacement.run_id)
        if old.revision != expected_revision:
            return False
        require(replacement.revision == old.revision + 1 and all(getattr(old, k) == getattr(replacement, k)
            for k in ('run_id', 'key', 'request_hash', 'snapshot_json', 'max_attempts', 'result_kind')), 'TASK_INPUT_INVALID')
        self.state.workflows[old.run_id]['run'] = dump_run(replacement)
        return True


class Operations:
    def __init__(self, repository, access, assets, *, clock=lambda: int(time.time()), cleanup_policy=CleanupPolicy()):
        self.repository, self.access, self.assets, self.clock = repository, access, assets, clock
        self.review = ReviewService(repository, access, clock=lambda: datetime.fromtimestamp(clock(), timezone.utc).isoformat())
        self.cleanup = CleanupService(repository, access, policy=cleanup_policy,
            clock=lambda: datetime.fromtimestamp(clock(), timezone.utc))

    def _actor(self, actor):
        require(isinstance(actor, ReviewPrincipal) and type(actor.actor_id) is int and actor.actor_id > 0, 'OBJECT_NOT_FOUND')

    def _asset(self, actor, version_id, operation):
        self._actor(actor)
        asset_id, ref = self.assets.resolve(actor, version_id, operation)
        require(isinstance(ref, AssetRef) and ref.domain_id == actor.domain_id, 'OBJECT_NOT_FOUND')
        require(ref.version_id == version_id, 'ASSET_VERSION_MISMATCH')
        key = dict(asset_id=asset_id, asset_version_id=ref.version_id, content_hash=ref.content_hash)
        require(self.access.allowed(actor, key, operation) is True, 'OBJECT_NOT_FOUND')
        return key, ref

    def _run(self, state, actor, run_id, operation='read_scan'):
        self._actor(actor)
        run = StateRunRepository(state).get(run_id)
        require(run.key[:4] == (actor.domain_id, actor.environment, actor.evaluation_run_id or '', str(actor.actor_id)),
                'OBJECT_NOT_FOUND')
        snap = json.loads(run.snapshot_json)
        self._asset(actor, snap['asset']['version_id'], operation)
        return run

    def create_version(self, actor, asset_id, content, format):
        """Delegate storage/version allocation to the owner; never edit its bytes."""
        self._actor(actor)
        identifier(asset_id)
        require(type(content) is bytes and len(content) <= Limits().max_bytes and format in ('csv', 'xlsx'), 'RESOURCE_LIMIT')
        require(self.access.allowed(actor, dict(asset_id=asset_id), 'create_version') is True, 'OBJECT_NOT_FOUND')
        return self.assets.create_version(actor, asset_id, content, format)

    def create_scan(self, actor, version_id, *, configuration, context, idempotency_key,
                    config=ParserConfig(), limits=Limits(), scope=None, base_profile_id=None,
                    semantic_required=True, max_attempts=2):
        asset, ref = self._asset(actor, version_id, 'scan')
        require(ref.state == 'ready', 'ASSET_UNAVAILABLE')
        require(type(semantic_required) is bool and type(max_attempts) is int and 1 <= max_attempts <= 2, 'TASK_INPUT_INVALID')
        cfg = RuleConfiguration.load(configuration.data()).data()
        require(actor.environment in cfg['allowed_environments'], 'POLICY_NOT_ACTIVE')
        ctx = context.data()
        require(scope is not None and scope.asset_version_id == version_id and fingerprint(asdict(scope)) == ctx['scope_hash'],
                'CONTEXT_SCOPE_MISMATCH')
        require(ctx['asset_version_id'] == version_id and all(ctx['meta'][k] == v for k,v in (
            ('domain_id',actor.domain_id),('environment',actor.environment),('evaluation_run_id',actor.evaluation_run_id))), 'CONTEXT_SCOPE_MISMATCH')
        snap = parse_snapshot(ref, config=config, limits=limits, scope=scope)
        snap.update(asset_key=asset, configuration=cfg, context=ctx, semantic_required=semantic_required,
                    base_profile_id=base_profile_id, expected_applicability_version=None)
        def create(state):
            # A fixed content version cannot silently acquire different bytes or identity.
            for row in state.workflows.values():
                previous = json.loads(restore_run(row['run']).snapshot_json)
                if previous['asset']['version_id'] == version_id and previous['asset']['domain_id'] == actor.domain_id:
                    require(previous['asset'] == snap['asset'] and previous['asset_key'] == asset, 'ASSET_VERSION_MISMATCH')
            if base_profile_id:
                old = self.review._get(state, actor, base_profile_id, 'scan')
                require(old['profile']['asset']['asset_id'] == asset['asset_id'], 'ASSET_VERSION_MISMATCH')
                snap['expected_applicability_version'] = state.applicability[base_profile_id]['state_version']
            # Replay compares the frozen expected state, not a later mutable head.
            key = (actor.domain_id, actor.environment, actor.evaluation_run_id or '', str(actor.actor_id), idempotency_key)
            existing = state.workflow_keys.get(fingerprint(list(key)))
            if existing:
                prior = json.loads(StateRunRepository(state).get(existing).snapshot_json)
                snap['expected_applicability_version'] = prior['expected_applicability_version']
            run = ParseTasks(StateRunRepository(state)).create(domain=actor.domain_id, environment=actor.environment,
                evaluation=actor.evaluation_run_id or '', principal=str(actor.actor_id), idempotency_key=idempotency_key,
                snapshot=snap, max_attempts=max_attempts)
            return self._view(state, run)
        return self.repository.atomic(create)

    def _view(self, state, run):
        row = state.workflows[run.run_id]
        attempt = run.attempts[-1] if run.attempts else None
        profile = state.bundles[row['profile_id']]['profile'] if row['profile_id'] else None
        return dict(scan_id=run.run_id, status=run.status, profile_id=row['profile_id'],
            quality=profile['quality'] if profile else 'unavailable', cancel_requested=run.cancel_requested,
            stage=('completed' if profile else attempt.stage if attempt else 'queued'),
            processed_count=attempt.processed_count if attempt else 0, total_count=attempt.total_count if attempt else None,
            progress_ratio=attempt.progress_ratio if attempt else None, attempts=len(run.attempts),
            error_code=row['error_code'] or (attempt.error_code if attempt else None),
            result_kind='scan_result', detection_status='completed' if profile else 'not_completed')

    def get_scan(self, actor, run_id):
        return self.repository.read(lambda s: self._view(s, self._run(s, actor, run_id)))

    def cancel_scan(self, actor, run_id):
        def cancel(state):
            self._run(state, actor, run_id, 'cancel_scan')
            return self._view(state, ParseTasks(StateRunRepository(state)).cancel(run_id))
        return self.repository.atomic(cancel)

    def retry_scan(self, actor, run_id, *, expected_attempt, idempotency_key):
        require(type(idempotency_key) is str and 0 < len(idempotency_key) <= 128, 'TASK_INPUT_INVALID')
        def retry(state):
            self._run(state, actor, run_id, 'retry_scan')
            run = ParseTasks(StateRunRepository(state)).retry(run_id, expected_attempt=expected_attempt, idempotency_key=idempotency_key)
            state.workflows[run_id]['error_code'] = None
            return self._view(state, run)
        return self.repository.atomic(retry)

    def recover_expired(self, actor, run_id):
        def expire(state):
            self._run(state, actor, run_id, 'retry_scan')
            return self._view(state, ParseTasks(StateRunRepository(state)).expire(run_id, now=self.clock()))
        return self.repository.atomic(expire)

    def _publish(self, state, actor, bundle, base_id, expected):
        profile = bundle['profile']
        self.review._get(ReviewState(bundles={profile['profile_id']: bundle}), actor, profile['profile_id'], 'register')
        old = None
        if base_id:
            old = self.review._get(state, actor, base_id, 'scan')
            app = state.applicability[base_id]
            require(app['state_version'] == expected and app['status'] == 'current'
                    and state.heads[head_key(old['profile'])] == base_id, 'REVIEW_VERSION_CONFLICT')
            require(old['profile']['asset']['asset_id'] == profile['asset']['asset_id'], 'ASSET_VERSION_MISMATCH')
            profile['supersedes_profile_id'] = base_id
        head = state.heads.get(head_key(profile))
        require(head is None or head == base_id, 'PROFILE_HEAD_CONFLICT')
        # Do not bypass manual review by omitting a base reference or using a different range.
        current = [b for pid,b in state.bundles.items() if partition(b['profile']) == partition(profile)
            and b['profile']['asset']['asset_id'] == profile['asset']['asset_id'] and state.applicability[pid]['status'] == 'current']
        related = [b for b in state.bundles.values() if partition(b['profile']) == partition(profile)
                   and b['profile']['asset']['asset_id'] == profile['asset']['asset_id']]
        require(not related or old is not None, 'BASE_PROFILE_REQUIRED')
        has_review = old is not None and (any(r['successor_profile_id'] == base_id for r in state.reviews.values())
            or any(f.get('review_id') for f in old['findings']) or bool(old['snapshot'].get('inherited_profile_id')))
        if has_review:
            if exact_review_reuse(old, bundle):
                inherited = deepcopy(old['findings'])
                for finding in inherited:
                    prior = finding['finding_id']
                    finding.update(finding_id=str(uuid5(UUID(profile['scan_id']), prior)), scan_id=profile['scan_id'],
                                   source_finding_ids=sorted(set(finding['source_finding_ids'] + [prior])))
                bundle['findings'] = inherited
                profile.update(finding_ids=[f['finding_id'] for f in inherited],
                    category_counts=deepcopy(old['profile']['category_counts']), protection_level=old['profile']['protection_level'],
                    review_status=old['profile']['review_status'])
                bundle['snapshot']['inherited_profile_id'] = base_id
            else:
                profile['review_status'] = 'pending'
                profile['quality'] = 'partial'
                profile['limitations'] = sorted(set(profile['limitations'] + ['PRIOR_REVIEW_RECHECK_REQUIRED']))
        pid = profile['profile_id']
        require(pid not in state.bundles, 'PROFILE_IMMUTABLE')
        state.bundles[pid], state.heads[head_key(profile)] = bundle, pid
        if old:
            self.review._event(state, self.review._state(state, old['profile'], status='superseded', successor=pid, reason='RESCAN_REPLACED'))
        for other in current:
            if other is not old:
                self.review._event(state, self.review._state(state, other['profile'], status='reevaluation_required', reason='ASSET_SCAN_CHANGED'))
        self.review._state(state, profile, reason='SCAN_PUBLISHED')

    def execute_one(self, actor, run_id):
        """Managed synchronous worker unit; source access and inference run outside locks."""
        def claim(state):
            run = self._run(state, actor, run_id, 'scan')
            require(not any(restore_run(row['run']).status == 'running' and restore_run(row['run']).key[:3] == run.key[:3]
                for rid,row in state.workflows.items() if rid != run_id), 'CONCURRENCY_LIMIT')
            limit = json.loads(run.snapshot_json)['limits']['max_seconds']
            return ParseTasks(StateRunRepository(state)).claim(run_id, now=self.clock(), lease_seconds=2 * limit + 30)
        run = self.repository.atomic(claim)
        snap, token = json.loads(run.snapshot_json), run.attempts[-1].token
        def cancelled():
            current = self.repository.read(lambda s: StateRunRepository(s).get(run_id))
            return current.cancel_requested or current.status != 'running' or current.attempts[-1].token != token or self.clock() >= current.attempts[-1].lease_expires
        def stage(name, count=0, total=None):
            self.repository.atomic(lambda s: ParseTasks(StateRunRepository(s)).record_progress(run_id, token=token,
                now=self.clock(), stage=name, processed_count=count, total_count=total))
        try:
            _, ref = self._asset(actor, snap['asset']['version_id'], 'scan')
            require(asdict(ref) == snap['asset'], 'ASSET_VERSION_MISMATCH')
            raw = read_private(self.assets, ref, principal=str(actor.actor_id), domain_id=actor.domain_id,
                               limits=Limits(**snap['limits']), cancelled=cancelled)
            stage('parse')
            scope = snap['scope']
            scope = None if scope is None else Scope(scope['asset_version_id'], tuple(Selection(s['sheet_id'],
                tuple(map(tuple,s['rows'])), tuple(map(tuple,s['columns']))) for s in scope['selections']), scope['include_header'])
            parsed = parse_table(raw, ref, config=ParserConfig(**snap['config']), limits=Limits(**snap['limits']), scope=scope, cancelled=cancelled)
            ctx = BusinessContext(json.dumps(snap['context']))
            result = scan_rules(parsed, RuleConfiguration.load(snap['configuration']), ctx,
                meta=snap['context']['meta'], asset=snap['asset_key'], principal=str(actor.actor_id), scan_id=run_id,
                applicability_ref=str(uuid4()), parsed_ref='private:workflow-parsed:' + run_id,
                semantic_required=snap['semantic_required'], cancelled=cancelled)
            stage('finalize', len(parsed.cells), len(parsed.cells))
            bundle = self.review._prepare_bundle(result, parsed)
            # Recheck asset owner immediately before the atomic local publish.
            _, latest = self._asset(actor, ref.version_id, 'scan')
            require(latest == ref, 'ASSET_VERSION_MISMATCH')
            def publish(state):
                tasks = ParseTasks(StateRunRepository(state))
                owned = tasks._owned(run_id, token, self.clock())
                if owned.cancel_requested:
                    return self._view(state, tasks.finish(run_id, token=token, now=self.clock(), error_code='TASK_CANCELLED'))
                self._publish(state, actor, bundle, snap['base_profile_id'], snap['expected_applicability_version'])
                pid = bundle['profile']['profile_id']
                state.workflows[run_id]['profile_id'] = pid
                resource_id = 'parsed:' + run_id
                state.resources[resource_id] = dict(resource_id=resource_id, kind='temporary_parse', scope=list(partition(bundle['profile'])),
                    asset=deepcopy(snap['asset_key']), run_id=run_id, profile_ids=[pid], created_at=self.clock(), expires_at=None,
                    hold=False, active_refs=[], deleted=False, payload=asdict(parsed))
                final = tasks.finish(run_id, token=token, now=self.clock(), parsed_ref='private:profile:' + pid)
                return self._view(state, final)
            return self.repository.atomic(publish)
        except Exception as exc:
            if isinstance(exc, InputError) and exc.code in ('STALE_ATTEMPT', 'TASK_VERSION_CONFLICT'):
                raise
            safe_codes = {'ASSET_UNAVAILABLE','ASSET_VERSION_MISMATCH','OBJECT_NOT_FOUND','CONTEXT_SCOPE_MISMATCH',
                'REVIEW_VERSION_CONFLICT','PROFILE_HEAD_CONFLICT','BASE_PROFILE_REQUIRED','TASK_CANCELLED',
                'RESOURCE_LIMIT','PARSE_FAILED','ENCODING_INVALID','CONFIG_INVALID'}
            code = exc.code if isinstance(exc, InputError) and exc.code in safe_codes else 'SCAN_FAILED'
            def failed(state):
                state.workflows[run_id]['error_code'] = code
                return self._view(state, ParseTasks(StateRunRepository(state)).finish(run_id, token=token,
                    now=self.clock(), error_code='TASK_CANCELLED' if code == 'TASK_CANCELLED' else 'PARSE_FAILED'))
            return self.repository.atomic(failed)

    def get_profile(self, actor, profile_id):
        return self.review.get_profile(actor, profile_id)

    def read_private_parsed(self, actor, run_id):
        def read(state):
            self._run(state, actor, run_id, 'view_source')
            row = state.resources.get('parsed:' + run_id)
            require(row is not None, 'OBJECT_NOT_FOUND')
            require(not row['deleted'], 'ARTIFACT_DELETED')
            return row['payload']
        return self.repository.read(read)

    def list_findings(self, actor, profile_id, **paging):
        return self.review.list_findings(actor, profile_id, **paging)

    def submit_review(self, actor, **request):
        return self.review.submit_review(actor, **request)

    def cleanup_preview(self, actor, *, scope=None):
        return self.cleanup.preview(actor, scope=scope)

    def cleanup_execute(self, actor, *, scope=None, dry_run=True, reason='', preview_hash=None):
        return self.cleanup.execute(actor, scope=scope, dry_run=dry_run, reason=reason,
                                    preview_hash=preview_hash)

    def request_asset_invalidation(self, actor, asset, owner, *, reason):
        authoritative_key, ref = self._asset(actor, asset['asset_version_id'], 'invalidate_asset')
        authoritative = dict(asset_id=authoritative_key['asset_id'], asset_version_id=ref.version_id,
                             **asdict(ref))
        require(authoritative == asset, 'ASSET_VERSION_MISMATCH')
        return self.cleanup.request_owner_invalidation(actor, authoritative, owner, reason=reason)

    def compare_scans(self, actor, before_profile_id, after_profile_id):
        def compare(state):
            a = self.review._get(state, actor, before_profile_id, 'compare')
            b = self.review._get(state, actor, after_profile_id, 'compare')
            return compare_bundles(a, b)
        return self.repository.read(compare)

    def regrade(self, actor, profile_id, configuration, *, expected_state_version, idempotency_key):
        require(type(idempotency_key) is str and 0 < len(idempotency_key) <= 128, 'TASK_INPUT_INVALID')
        require(type(expected_state_version) is int and expected_state_version > 0, 'REVIEW_INPUT_INVALID')
        def update(state):
            old = self.review._get(state, actor, profile_id, 'regrade')
            cfg = regrade_configuration(old, configuration.data())
            require(actor.environment in cfg['allowed_environments'], 'POLICY_NOT_ACTIVE')
            key = fingerprint([partition(old['profile']), actor.actor_id, 'regrade', idempotency_key])
            request = fingerprint([profile_id, expected_state_version, cfg])
            if key in state.regrade_keys:
                prior = state.regrade_keys[key]
                require(prior['request'] == request, 'IDEMPOTENCY_CONFLICT')
                return state.bundles[prior['profile_id']]['profile']
            require(state.applicability[profile_id]['status'] == 'current' and
                    state.applicability[profile_id]['state_version'] == expected_state_version, 'REVIEW_VERSION_CONFLICT')
            new = deepcopy(old)
            p = new['profile']
            pid = str(uuid4())
            levels = {c['category_id']:c['protection_level'] for c in cfg['policy']['categories']}
            values = [levels[f['category_id']] for f in new['findings']]
            p.update(profile_id=pid, applicability_ref=str(uuid4()), policy_version=cfg['policy']['version'],
                supersedes_profile_id=profile_id, protection_level=max(values,key=cfg['policy']['levels'].index) if values else None)
            # Keep the scan's original immutable configuration and evidence intact.
            new['regrade'] = dict(configuration=cfg, source_profile_id=profile_id)
            for row in state.resources.values():
                if profile_id in row['profile_ids']:
                    row['profile_ids'].append(pid)
            state.bundles[pid], state.heads[head_key(p)] = new, pid
            state.regrade_keys[key] = dict(request=request, profile_id=pid)
            self.review._event(state, self.review._state(state, old['profile'], status='superseded', successor=pid, reason='POLICY_REGRADED'))
            self.review._state(state, p, reason='POLICY_REGRADED')
            return p
        return self.repository.atomic(update)
