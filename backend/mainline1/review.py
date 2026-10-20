"""Internal review service; no HTTP publication or production authorization.

The repository transaction must atomically commit history, head, applicability and
outbox, with serializable isolation across ALL scopes of an asset. The supplied
memory adapter is explicitly development-only, not durable delivery evidence.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from uuid import uuid4

from .classification import RuleConfiguration, require
from .parsing import InputError, fingerprint


def uid():
    return str(uuid4())


@dataclass(frozen=True)
class ReviewPrincipal:
    """Constructed by authenticated server code, never deserialized from a DTO."""
    actor_id: int
    domain_id: str
    environment: str
    evaluation_run_id: str | None = None


class ObjectAccess(Protocol):
    def allowed(self, principal, asset, operation): ...


@dataclass
class ReviewState:
    bundles: dict = field(default_factory=dict)
    heads: dict = field(default_factory=dict)
    applicability: dict = field(default_factory=dict)
    state_history: list = field(default_factory=list)
    reviews: dict = field(default_factory=dict)
    keys: dict = field(default_factory=dict)
    bindings: dict = field(default_factory=dict)
    outbox: dict = field(default_factory=dict)
    workflows: dict = field(default_factory=dict)
    workflow_keys: dict = field(default_factory=dict)
    regrade_keys: dict = field(default_factory=dict)
    resources: dict = field(default_factory=dict)
    cleanup_audit: list = field(default_factory=list)


class ReviewRepository(Protocol):
    """No fallback on storage failure. operation receives a private transaction view.

    Implementations must durably enforce unique heads, keys and IDs (constraints
    or a single locked aggregate with atomic checks);
    rollback all changes on exception; serialize asset-wide overlapping-scope
    invalidation and publication. Do not expose this port to untrusted callers.
    """
    def atomic(self, operation): ...
    def read(self, operation): ...


class MemoryReviewRepository:
    """Synthetic/local adapter only. Thread-safe, process-local, loses state on exit."""
    def __init__(self):
        self._state, self._lock = ReviewState(), RLock()

    def atomic(self, operation):
        with self._lock:
            candidate = deepcopy(self._state)
            result = deepcopy(operation(candidate))
            self._state = candidate
            return result

    def read(self, operation):
        with self._lock:
            return deepcopy(operation(deepcopy(self._state)))


class ReviewConflict(InputError):
    def __init__(self, latest_profile_id):
        super().__init__('REVIEW_VERSION_CONFLICT')
        self.latest_profile_id = latest_profile_id


def partition(profile):
    meta = profile['meta']
    return (meta['domain_id'], meta['environment'], meta['evaluation_run_id'])


def head_key(profile):
    return partition(profile) + (profile['asset']['asset_version_id'], profile['scope_hash'])


def binding(bundle):
    """Strict same-input eligibility; no coordinate-only transfer or public hash."""
    snapshot = bundle['snapshot']
    return {k: deepcopy(snapshot.get(k)) for k in (
        'asset', 'scope_hash', 'parser_version', 'parser_config_hash', 'parsed_cells_hash',
        'parse_metadata_hash', 'context', 'configuration', 'semantic', 'fusion_version',
        'combination_config', 'model', 'scan_policy_version')}


class ReviewService:
    def __init__(self, repository: ReviewRepository, access: ObjectAccess, *, clock=None):
        self.repository, self.access = repository, access
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def _get(self, state, principal, profile_id, operation='read'):
        bundle = state.bundles.get(profile_id)
        require(isinstance(principal, ReviewPrincipal) and type(principal.actor_id) is int
                and principal.actor_id > 0, 'OBJECT_NOT_FOUND')
        require(bundle is not None, 'OBJECT_NOT_FOUND')
        profile = bundle['profile']
        require(partition(profile) == (principal.domain_id, principal.environment, principal.evaluation_run_id),
                'OBJECT_NOT_FOUND')
        require(self.access.allowed(principal, deepcopy(profile['asset']), operation) is True, 'OBJECT_NOT_FOUND')
        return bundle

    def _state(self, state, profile, *, status='current', successor=None, reason='PROFILE_REGISTERED'):
        pid = profile['profile_id']
        previous = state.applicability.get(pid)
        value = dict(meta=deepcopy(profile['meta']), applicability_id=profile['applicability_ref'],
            profile_id=pid, asset_version_id=profile['asset']['asset_version_id'],
            state_version=previous['state_version'] + 1 if previous else 1, status=status,
            successor_profile_id=successor, reason_codes=[reason], changed_at=self.clock(),
            affected_scope_hash=profile['scope_hash'], usable_for_new_decision=False,
            historical_audit_available=True)
        # Development policy and owner integration are not authorization evidence.
        state.applicability[pid] = value
        state.state_history.append(deepcopy(value))
        return value

    def _event(self, state, app):
        event = dict(meta=deepcopy(app['meta']), event_id=uid(),
            event_type='profile_superseded' if app['status'] == 'superseded' else 'profile_reevaluation_required',
            aggregate_version=app['state_version'], old_profile_id=app['profile_id'],
            new_profile_id=app['successor_profile_id'], asset_version_id=app['asset_version_id'],
            scope_hash=app['affected_scope_hash'], reason_codes=app['reason_codes'], occurred_at=app['changed_at'])
        state.outbox[event['event_id']] = dict(event=event, status='pending', attempts=0, last_error=None)

    def _prepare_bundle(self, result, parsed):
        bundle = result.data()
        profile, snapshot = bundle['profile'], bundle['snapshot']
        cfg = RuleConfiguration.load(snapshot['configuration']).data()
        require(profile['meta']['environment'] in cfg['allowed_environments'], 'POLICY_NOT_ACTIVE')
        require(profile['asset'] == snapshot['asset'] and profile['scope_hash'] == parsed.scope_hash
                and profile['asset']['asset_version_id'] == parsed.asset_version_id
                and profile['asset']['content_hash'] == parsed.input_content_hash
                and snapshot['parsed_cells_hash'] == fingerprint([asdict(c) for c in parsed.cells])
                and snapshot['parser_config_hash'] == parsed.config_hash, 'ASSET_VERSION_MISMATCH')
        require(profile['policy_version'] == cfg['policy']['version'], 'CONFIG_INVALID')
        require(profile['finding_ids'] == [f['finding_id'] for f in bundle['findings']], 'CONFIG_INVALID')
        require(len(set(profile['finding_ids'])) == len(profile['finding_ids']), 'CONFIG_INVALID')
        bundle['_cells'] = {(c.sheet_id, c.row, c.column, c.channel): len(c.source_text) for c in parsed.cells}
        return bundle

    def register(self, principal, result, parsed):
        """Trusted scan-ingestion adapter only, not a user-controlled profile API."""
        bundle = self._prepare_bundle(result, parsed)
        profile = bundle['profile']

        def commit(state):
            pid, key = profile['profile_id'], head_key(profile)
            # Check authorization before revealing registration/head conflicts.
            temporary = ReviewState(bundles={pid: bundle})
            self._get(temporary, principal, pid, 'register')
            if pid in state.bundles:
                require(state.bundles[pid] == bundle, 'PROFILE_IMMUTABLE')
                return pid
            require(key not in state.heads, 'PROFILE_HEAD_CONFLICT')
            require(not any(partition(b['profile']) == partition(profile)
                and b['profile']['asset']['asset_version_id'] == profile['asset']['asset_version_id']
                and b['profile']['asset'] != profile['asset'] for b in state.bundles.values()), 'ASSET_VERSION_MISMATCH')
            # New parallel scopes must not bypass earlier human corrections.
            require(not any(partition(state.bundles[r['base_profile_id']]['profile']) == partition(profile)
                and state.bundles[r['base_profile_id']]['profile']['asset']['asset_version_id'] == profile['asset']['asset_version_id']
                for r in state.reviews.values()), 'REVIEW_REVALIDATION_REQUIRED')
            state.bundles[pid], state.heads[key] = deepcopy(bundle), pid
            self._state(state, profile)
            return pid
        return self.repository.atomic(commit)

    def get_profile(self, principal, profile_id):
        return self.repository.atomic(lambda s: self._get(s, principal, profile_id)['profile'])

    def read_plan_basis(self, principal, profile_id):
        """Internal authorized, consistent read; never creates a ledger or writes it."""
        def read(state):
            bundle = self._get(state, principal, profile_id, 'plan')
            return dict(bundle=bundle, applicability=state.applicability[profile_id])
        return self.repository.read(read)

    def get_profile_applicability(self, principal, profile_id):
        def read(state):
            self._get(state, principal, profile_id)
            return state.applicability[profile_id]
        return self.repository.atomic(read)

    def list_findings(self, principal, profile_id, *, pending_only=True, offset=0, limit=50):
        require(type(offset) is int and offset >= 0 and type(limit) is int and 1 <= limit <= 100,
                'REVIEW_INPUT_INVALID')
        require(type(pending_only) is bool, 'REVIEW_INPUT_INVALID')
        def read(state):
            bundle = self._get(state, principal, profile_id)
            findings = [f for f in bundle['findings'] if not pending_only or f['judgment'] != 'determined']
            # Full redaction is intentional; no arbitrary reasons, evidence text or context.
            items = [dict(finding_id=f['finding_id'], category_id=f['category_id'], judgment=f['judgment'],
                source_type=f['source_type'], locations=f['locations'], sample='[REDACTED]',
                source_finding_ids=f['source_finding_ids'],
                evidence_kinds=sorted({e['kind'] for e in f['evidence']}),
                evidence_reason_codes=sorted({e['reason_code'] if e['reason_code'] in {
                    'ASCII_EMAIL_SYNTAX', 'IPV4_OCTETS_VALID', 'LUHN_VALID_NOT_ACCOUNT_PROOF',
                    'FIXED_PARSED_CELL', 'HUMAN_REVIEW'} else 'CONTROLLED_EVIDENCE'
                    for e in f['evidence']})) for f in findings[offset:offset + limit]]
            return dict(profile_id=profile_id, items=items,
                        next_offset=offset + limit if offset + limit < len(findings) else None)
        return self.repository.atomic(read)

    def get_review(self, principal, review_id):
        def read(state):
            record = state.reviews.get(review_id)
            require(record is not None, 'OBJECT_NOT_FOUND')
            self._get(state, principal, record['base_profile_id'], 'read_review')
            return record
        return self.repository.atomic(read)

    def _locations(self, bundle, locations):
        require(isinstance(locations, list) and len(locations) == 1, 'LOCATION_MISMATCH')
        loc = locations[0]
        require(isinstance(loc, dict) and set(loc) == {'kind', 'sheet_id', 'row', 'column', 'channel', 'span'},
                'LOCATION_MISMATCH')
        require(type(loc['row']) is int and type(loc['column']) is int
                and isinstance(loc['sheet_id'], str) and isinstance(loc['channel'], str), 'LOCATION_MISMATCH')
        length = bundle['_cells'].get((loc['sheet_id'], loc['row'], loc['column'], loc['channel']))
        require(length is not None, 'LOCATION_MISMATCH')
        if loc['kind'] == 'cell':
            require(loc['span'] is None, 'LOCATION_MISMATCH')
        else:
            span = loc['span']
            require(loc['kind'] == 'span' and isinstance(span, dict)
                    and set(span) == {'start', 'end'}, 'LOCATION_MISMATCH')
            require(type(span['start']) is int
                    and type(span['end']) is int and 0 <= span['start'] < span['end'] <= length,
                    'LOCATION_MISMATCH')

    def submit_review(self, principal, *, base_profile_id, expected_state_version,
                      idempotency_key, action, reason, finding_id=None, category_id=None, locations=None):
        require(action in ('confirm', 'correct', 'false_positive', 'add_manual'), 'REVIEW_INPUT_INVALID')
        require(type(expected_state_version) is int and expected_state_version > 0
                and isinstance(idempotency_key, str) and 0 < len(idempotency_key) <= 128
                and isinstance(reason, str) and 0 < len(reason.strip()) <= 2048, 'REVIEW_INPUT_INVALID')
        request = dict(base_profile_id=base_profile_id, expected_state_version=expected_state_version,
            action=action, reason=reason, finding_id=finding_id, category_id=category_id, locations=locations)
        request_hash = fingerprint(request)

        def commit(state):
            bundle = self._get(state, principal, base_profile_id, 'review')
            old = bundle['profile']
            key = partition(old) + (principal.actor_id, 'review', idempotency_key)
            if key in state.keys:
                record = state.reviews[state.keys[key]]
                require(record['request_fingerprint'] == request_hash, 'IDEMPOTENCY_CONFLICT')
                return record
            app = state.applicability[base_profile_id]
            latest = state.heads[head_key(old)]
            if latest != base_profile_id or app['state_version'] != expected_state_version:
                # Recheck latest ACL before exposing its reference.
                self._get(state, principal, latest)
                raise ReviewConflict(latest)
            require(app['status'] == 'current', 'PROFILE_REEVALUATION_REQUIRED')
            cfg = RuleConfiguration.load(bundle.get('regrade', {}).get('configuration', bundle['snapshot']['configuration'])).data()
            policy = cfg['policy']
            categories = {c['category_id']: c for c in policy['categories']}
            require(not old['combination_finding_ids'], 'COMBINATION_REVIEW_UNSUPPORTED')
            target = next((f for f in bundle['findings'] if f['finding_id'] == finding_id), None)
            if action == 'add_manual':
                require(finding_id is None and category_id in categories, 'REVIEW_INPUT_INVALID')
                self._locations(bundle, locations)
            else:
                require(target is not None and locations is None, 'REVIEW_INPUT_INVALID')
                require(target['kind'] == 'entity', 'REVIEW_INPUT_INVALID')
                if action == 'correct':
                    require(category_id in categories, 'CATEGORY_INVALID')
                else:
                    require(category_id is None, 'REVIEW_INPUT_INVALID')
            after = (target['category_id'] if action == 'confirm' else None if action == 'false_positive' else category_id)
            require(after is None or after in categories, 'CATEGORY_INVALID')
            rid, pid, now = uid(), uid(), self.clock()
            meta = dict(old['meta'], created_at=now)
            active = [deepcopy(f) for f in bundle['findings'] if f['finding_id'] != finding_id]
            new_finding = None
            if action != 'false_positive':
                new_finding = dict(meta=meta, finding_id=uid(), scan_id=old['scan_id'], kind='entity',
                    locations=deepcopy(locations if target is None else target['locations']), category_id=after,
                    judgment='determined', source_type='manual', detector_id=None, detector_version=None,
                    source_finding_ids=[] if target is None else [target['finding_id']], relation_type=None,
                    evidence=[dict(evidence_ref='private:review:' + rid, kind='review', reason_code='HUMAN_REVIEW')],
                    uncertainty_reasons=[], raw_score=None, score_meaning=None, calibrated_probability=None,
                    calibration_version=None, created_by=principal.actor_id, review_id=rid)
                active.append(new_finding)
            successor = deepcopy(old)
            counts = Counter(f['category_id'] for f in active if f['category_id'] is not None)
            levels = [categories[c]['protection_level'] for c in counts]
            successor.update(meta=meta, profile_id=pid, applicability_ref=uid(), supersedes_profile_id=base_profile_id,
                finding_ids=[f['finding_id'] for f in active],
                category_counts=[dict(category_id=c, count=counts[c]) for c in sorted(counts)],
                protection_level=max(levels, key=policy['levels'].index) if levels else None,
                review_status='pending' if any(f['judgment'] != 'determined' for f in active) else 'completed')
            # Review never upgrades detection quality/coverage or removes prior limitations.
            new_bundle = deepcopy(bundle)
            new_bundle.update(profile=successor, findings=active)
            record = dict(meta=meta, review_id=rid, base_profile_id=base_profile_id,
                expected_state_version=expected_state_version, idempotency_key=idempotency_key,
                request_fingerprint=request_hash, actor_id=principal.actor_id, action=action,
                finding_ids=[target['finding_id']] if target else [new_finding['finding_id']], reason=reason,
                before_category=target['category_id'] if target else None, after_category=after,
                workflow_status='completed', request_status='accepted',
                conclusion={'confirm': 'confirmed', 'correct': 'corrected', 'false_positive': 'false_positive',
                            'add_manual': 'manual_added'}[action], successor_profile_id=pid, completed_at=now)
            state.bundles[pid], state.heads[head_key(old)] = new_bundle, pid
            state.reviews[rid], state.keys[key], state.bindings[rid] = record, rid, binding(bundle)
            self._event(state, self._state(state, old, status='superseded', successor=pid, reason='REVIEW_' + action.upper()))
            self._state(state, successor, reason='REVIEW_' + action.upper())
            # Conservative asset-wide invalidation: unknown intersections cannot remain current.
            for other_id, other in list(state.bundles.items()):
                p = other['profile']
                if (other_id != pid and partition(p) == partition(old) and p['asset']['asset_version_id'] == old['asset']['asset_version_id']
                        and state.applicability[other_id]['status'] == 'current'):
                    self._event(state, self._state(state, p, status='reevaluation_required', reason='ASSET_REVIEW_CHANGED'))
            return record
        return self.repository.atomic(commit)

    def add_manual_finding(self, principal, **request):
        return self.submit_review(principal, action='add_manual', **request)

    def review_reuse_eligibility(self, principal, review_id, candidate_profile_id):
        """Explicit eligibility only. Does not apply a conclusion or publish a rescan."""
        def read(state):
            record = state.reviews.get(review_id)
            require(record is not None, 'OBJECT_NOT_FOUND')
            self._get(state, principal, record['base_profile_id'], 'read_review')
            candidate = self._get(state, principal, candidate_profile_id)
            base = state.bundles[record['base_profile_id']]['profile']
            same = (state.bindings[review_id] == binding(candidate)
                    and state.heads[head_key(base)] == record['successor_profile_id']
                    and state.applicability[record['successor_profile_id']]['status'] == 'current')
            return dict(review_id=review_id, eligible=same,
                        reason_codes=['EXACT_INPUT_BINDING'] if same else ['INPUT_CHANGED_REVIEW_REQUIRED'],
                        automatic_inheritance=False)
        return self.repository.atomic(read)


class EventAdapter(Protocol):
    """Trusted adapter maps Proposed payload to a separately approved envelope.

    True means durable acknowledgement. Consumers deduplicate event_id and reject
    aggregate_version regressions per old_profile_id. No source/reason prose sent.
    """
    def publish(self, event) -> bool: ...


class ReviewOutbox:
    def __init__(self, repository, adapter=None, *, max_attempts=3):
        require(type(max_attempts) is int and max_attempts > 0, 'CONFIG_INVALID')
        self.repository, self.adapter, self.max_attempts = repository, adapter, max_attempts

    def dispatch(self, *, limit=50):
        require(type(limit) is int and 1 <= limit <= 100, 'CONFIG_INVALID')
        if self.adapter is None:
            return dict(status='not_connected', acknowledged=0, failed=0)
        rows = self.repository.atomic(lambda s: [r for r in s.outbox.values() if r['status'] == 'pending'][:limit])
        acknowledged = failed = 0
        for row in rows:
            try:
                ok = self.adapter.publish(deepcopy(row['event'])) is True
            except Exception:
                ok = False  # Never retain transport exception text, credentials or raw source.
            def mark(state):
                current = state.outbox[row['event']['event_id']]
                if current['status'] == 'acknowledged':
                    return
                current['attempts'] += 1
                current['status'] = 'acknowledged' if ok else 'dead_letter' if current['attempts'] >= self.max_attempts else 'pending'
                current['last_error'] = None if ok else 'DELIVERY_NOT_ACKNOWLEDGED'
            self.repository.atomic(mark)
            acknowledged += int(ok)
            failed += int(not ok)
        return dict(status='adapter_attempted', acknowledged=acknowledged, failed=failed)
