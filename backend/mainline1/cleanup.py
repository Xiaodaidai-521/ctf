"""Preview-first cleanup for mainline-owned temporary resources.

The service only handles rows recorded by this module. It never deletes an
asset-owner object, shared evidence, or an object outside the authenticated
scope. Deletion is a tombstone plus payload removal; references remain visible
as an explicit invalid state to callers with permission.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Protocol
from uuid import uuid4

from .classification import require
from .parsing import InputError, fingerprint
from .review import ReviewPrincipal, ReviewService, partition


@dataclass(frozen=True)
class CleanupPolicy:
    version: str = 'cleanup-v1-draft'
    approved: bool = False
    retention_seconds: int = 24 * 60 * 60
    allowed_kinds: tuple[str, ...] = ('temporary_parse', 'detection_cache')

    def __post_init__(self):
        require(isinstance(self.version, str) and bool(self.version), 'POLICY_INVALID')
        require(type(self.approved) is bool and type(self.retention_seconds) is int
                and self.retention_seconds > 0, 'POLICY_INVALID')
        require(type(self.allowed_kinds) is tuple and bool(self.allowed_kinds)
                and all(k in ('temporary_parse', 'detection_cache') for k in self.allowed_kinds),
                'POLICY_INVALID')


class OwnerInvalidation(Protocol):
    def invalidate(self, principal, asset, *, reason, audit_ref): ...


def _now(clock):
    value = clock()
    if isinstance(value, datetime):
        return value
    return datetime.fromtimestamp(value, timezone.utc)


class CleanupService:
    def __init__(self, repository, access, *, policy=CleanupPolicy(), clock=lambda: datetime.now(timezone.utc)):
        self.repository, self.access, self.policy, self.clock = repository, access, policy, clock

    def _principal(self, principal):
        require(isinstance(principal, ReviewPrincipal) and type(principal.actor_id) is int
                and principal.actor_id > 0, 'OBJECT_NOT_FOUND')

    def _scope(self, principal, scope):
        self._principal(principal)
        require(type(scope) is dict and set(scope) <= {'asset_ids', 'run_ids', 'domain_id', 'environment'},
                'CLEANUP_SCOPE_INVALID')
        require(scope.get('domain_id', principal.domain_id) == principal.domain_id
                and scope.get('environment', principal.environment) == principal.environment,
                'OBJECT_NOT_FOUND')
        for key in ('asset_ids', 'run_ids'):
            if key in scope:
                require(type(scope[key]) is list and 0 < len(scope[key]) <= 1000
                        and all(isinstance(v, str) and v for v in scope[key]), 'CLEANUP_SCOPE_INVALID')
        return dict(scope, domain_id=principal.domain_id, environment=principal.environment)

    def _candidate_rows(self, state, principal, scope, now):
        scope = self._scope(principal, scope)
        rows, blocked = [], []
        asset_ids, run_ids = set(scope.get('asset_ids', [])), set(scope.get('run_ids', []))
        for resource_id, row in sorted(state.resources.items()):
            if row.get('deleted'):
                continue
            resource_scope = tuple(row.get('scope', ()))
            if resource_scope != (principal.domain_id, principal.environment, principal.evaluation_run_id):
                continue
            if asset_ids and row.get('asset', {}).get('asset_id') not in asset_ids:
                continue
            if run_ids and row.get('run_id') not in run_ids:
                continue
            if self.access.allowed(principal, deepcopy(row.get('asset', {})), 'cleanup') is not True:
                # Do not reveal a resource identifier or retention state across ACL.
                blocked.append(dict(reason_code='OBJECT_NOT_FOUND'))
                continue
            if row.get('kind') not in self.policy.allowed_kinds:
                blocked.append(dict(resource_id=resource_id, reason_code='KIND_NOT_ALLOWED'))
                continue
            if row.get('hold') or row.get('active_refs'):
                blocked.append(dict(resource_id=resource_id, reason_code='REFERENCE_ACTIVE'))
                continue
            active = False
            for workflow in state.workflows.values():
                run = json.loads(workflow['run'])
                if run['status'] not in ('queued', 'running'):
                    continue
                snapshot = json.loads(run['snapshot_json'])
                if (run['key'][:3] == [principal.domain_id, principal.environment, principal.evaluation_run_id or '']
                        and snapshot['asset_key']['asset_id'] == row['asset']['asset_id']):
                    active = True
                    break
            if active:
                blocked.append(dict(resource_id=resource_id, reason_code='TASK_ACTIVE'))
                continue
            expires_at = row.get('expires_at')
            if expires_at is None:
                created_at = row.get('created_at')
                if type(created_at) is not int:
                    blocked.append(dict(resource_id=resource_id, reason_code='RETENTION_UNKNOWN'))
                    continue
                expires_at = created_at + self.policy.retention_seconds
            if type(expires_at) is not int:
                blocked.append(dict(resource_id=resource_id, reason_code='RETENTION_UNKNOWN'))
                continue
            if expires_at > now:
                blocked.append(dict(resource_id=resource_id, reason_code='RETENTION_NOT_EXPIRED'))
                continue
            rows.append(dict(resource_id=resource_id, kind=row['kind'], run_id=row.get('run_id'),
                             asset_id=row.get('asset', {}).get('asset_id'), expires_at=expires_at))
        return rows, blocked

    def preview(self, principal, *, scope=None):
        scope = {} if scope is None else scope
        observed = int(_now(self.clock).timestamp())
        return self.repository.read(lambda state: self._preview_state(state, principal, scope, observed, 'preview'))

    def _preview_state(self, state, principal, scope, now, mode):
        rows, blocked = self._candidate_rows(state, principal, scope, now)
        digest = fingerprint(dict(scope=self._scope(principal, scope), policy=asdict(self.policy),
                                 actor=principal.actor_id, evaluation=principal.evaluation_run_id,
                                 candidates=rows, blocked=blocked))
        return dict(mode=mode, policy_version=self.policy.version, scope=self._scope(principal, scope),
                    generated_at=now, candidate_count=len(rows), candidates=rows, blocked=blocked,
                    preview_hash=digest, audit_ref='private:cleanup-preview:' + digest)

    def execute(self, principal, *, scope=None, dry_run=True, reason='', preview_hash=None):
        scope = {} if scope is None else scope
        observed = int(_now(self.clock).timestamp())
        require(type(dry_run) is bool and isinstance(reason, str)
                and (not reason if dry_run else reason in ('RETENTION_EXPIRED', 'FAILED_TEMPORARY', 'AUTHORIZED_OWNER_REQUEST')),
                'CLEANUP_INPUT_INVALID')
        if not dry_run:
            require(self.policy.approved, 'CLEANUP_NOT_APPROVED')
            require(bool(reason), 'CLEANUP_REASON_REQUIRED')
            require(type(preview_hash) is str and bool(preview_hash), 'CLEANUP_PREVIEW_REQUIRED')

        def commit(state):
            result = self._preview_state(state, principal, scope, observed, 'execute' if not dry_run else 'preview')
            deleted = []
            if not dry_run:
                require(preview_hash == result['preview_hash'], 'CLEANUP_PREVIEW_STALE')
                for candidate in result['candidates']:
                    row = state.resources[candidate['resource_id']]
                    row['deleted'] = True
                    row['deleted_at'] = observed
                    row['deletion_reason'] = reason
                    row.pop('payload', None)
                    review = ReviewService(self.repository, self.access,
                        clock=lambda: datetime.fromtimestamp(observed, timezone.utc).isoformat())
                    affected = set(row.get('profile_ids', []))
                    if row['kind'] == 'temporary_parse':
                        # Reviews and regrades reuse the original scan's parsed material.
                        affected.update(pid for pid, bundle in state.bundles.items()
                            if bundle['profile']['scan_id'] == row.get('run_id')
                            and partition(bundle['profile']) == tuple(row['scope'])
                            and bundle['profile']['asset'] == row['asset'])
                    for profile_id in sorted(affected):
                        app = state.applicability.get(profile_id)
                        if app and app['status'] != 'unverifiable_deleted':
                            updated = deepcopy(app)
                            updated.update(state_version=app['state_version'] + 1, status='unverifiable_deleted',
                                reason_codes=['PARSED_ARTIFACT_DELETED'], changed_at=datetime.fromtimestamp(
                                    observed, timezone.utc).isoformat(), usable_for_new_decision=False,
                                historical_audit_available=True)
                            state.applicability[profile_id] = updated
                            state.state_history.append(deepcopy(updated))
                            review._event(state, updated)
                    deleted.append(candidate['resource_id'])
                result['deleted'] = deleted
            else:
                result['deleted'] = []
            audit = dict(audit_id=str(uuid4()), actor_id=principal.actor_id, scope_hash=fingerprint(result['scope']),
                         policy_version=self.policy.version, mode=result['mode'], reason_code=reason or None,
                         candidate_ids=[row['resource_id'] for row in result['candidates']], deleted_ids=deleted,
                         blocked=result['blocked'], at=observed)
            state.cleanup_audit.append(audit)
            result['audit_ref'] = 'private:cleanup-audit:' + audit['audit_id']
            return result
        return self.repository.atomic(commit)

    def request_owner_invalidation(self, principal, asset, owner, *, reason):
        """Call the asset owner; never mutate/delete its object locally."""
        self._principal(principal)
        require(self.policy.approved, 'CLEANUP_NOT_APPROVED')
        require(reason == 'AUTHORIZED_OWNER_REQUEST', 'CLEANUP_REASON_REQUIRED')
        require(self.access.allowed(principal, deepcopy(asset), 'invalidate_asset') is True, 'OBJECT_NOT_FOUND')
        audit_ref = 'private:owner-invalidation:' + str(uuid4())
        audit = dict(audit_id=audit_ref.rsplit(':', 1)[-1], actor_id=principal.actor_id,
            scope_hash=fingerprint(dict(asset=asset, domain=principal.domain_id)),
            policy_version=self.policy.version, mode='owner_invalidation_requested',
            reason_code='AUTHORIZED_OWNER_REQUEST', candidate_ids=[], deleted_ids=[], blocked=[],
            status='pending', at=int(_now(self.clock).timestamp()))
        self.repository.atomic(lambda state: state.cleanup_audit.append(deepcopy(audit)))
        try:
            result = owner.invalidate(principal, deepcopy(asset), reason=reason.strip(), audit_ref=audit_ref)
        except Exception:
            def fail(state):
                next(row for row in state.cleanup_audit if row['audit_id'] == audit['audit_id'])['status'] = 'failed'
            self.repository.atomic(fail)
            raise InputError('OWNER_INVALIDATION_UNAVAILABLE') from None
        status = 'acknowledged' if result is True else 'not_acknowledged'
        def finish(state):
            next(row for row in state.cleanup_audit if row['audit_id'] == audit['audit_id'])['status'] = status
        self.repository.atomic(finish)
        require(result is True, 'OWNER_INVALIDATION_NOT_ACKNOWLEDGED')
        return dict(status='requested', audit_ref=audit_ref)
