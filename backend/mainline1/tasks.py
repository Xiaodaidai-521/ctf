"""Internal parse-task state machine and atomic repository port.

The Django adapter is opt-in and uses PostgreSQL transactions. A parse success
is not a scan success. Production settings do not register this app yet.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from typing import Protocol
from uuid import uuid4

from .parsing import InputError, PARSING_ERROR_CODES, fingerprint


@dataclass(frozen=True)
class Attempt:
    attempt_id: str
    number: int
    token: str
    lease_expires: int
    status: str
    error_code: str | None = None
    stage: str = 'read'
    processed_count: int = 0
    total_count: int | None = None

    @property
    def progress_ratio(self):
        return self.processed_count / self.total_count if self.total_count else None


@dataclass(frozen=True)
class Run:
    run_id: str
    key: tuple[str, str, str, str, str]
    request_hash: str
    snapshot_json: str
    status: str = 'queued'
    revision: int = 1
    attempts: tuple[Attempt, ...] = ()
    cancel_requested: bool = False
    parsed_ref: str | None = None
    max_attempts: int = 2
    retry_keys: tuple[tuple[str, int], ...] = ()
    result_kind: str = 'parsed_asset'
    detection_status: str = 'not_run'
    scan_quality: str = 'unavailable'


class RunRepository(Protocol):
    """Production implementations must persist and atomically enforce these operations.

    create_unique is protected by a UNIQUE trusted key constraint, not get/insert.
    compare_and_swap MUST enforce revision and commit the entire run/attempt
    update in one transaction. Storage errors propagate: no memory fallback.
    """
    def create_unique(self, candidate: Run) -> Run: ...
    def get(self, run_id: str) -> Run: ...
    def compare_and_swap(self, expected_revision: int, replacement: Run) -> bool: ...


def dump_run(run: Run) -> str:
    return json.dumps(asdict(run), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def restore_run(payload: str) -> Run:
    """Restore trusted repository data only, never arbitrary client JSON."""
    data = json.loads(payload)
    data['key'] = tuple(data['key'])
    data['attempts'] = tuple(Attempt(**a) for a in data['attempts'])
    data['retry_keys'] = tuple(tuple(pair) for pair in data['retry_keys'])
    return Run(**data)


class ParseTasks:
    def __init__(self, repository: RunRepository):
        self.repository = repository

    def create(self, *, domain: str, environment: str, evaluation: str,
               principal: str, idempotency_key: str, snapshot: dict, max_attempts: int = 2) -> Run:
        if (any(type(v) is not str or len(v) > 128 for v in (domain, environment, evaluation, principal, idempotency_key))
                or not all((domain, environment, principal, idempotency_key))
                or environment not in ('development', 'test', 'production')):
            raise InputError('TASK_INPUT_INVALID')
        if type(max_attempts) is not int or max_attempts < 1:
            raise InputError('TASK_INPUT_INVALID')
        key = (domain, environment, evaluation, principal, idempotency_key)
        request_hash = fingerprint(dict(scope=list(key[:-1]), snapshot=snapshot, max_attempts=max_attempts))
        candidate = Run(str(uuid4()), key, request_hash,
                        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
                        max_attempts=max_attempts)
        actual = self.repository.create_unique(candidate)
        if actual.request_hash != request_hash:
            raise InputError('IDEMPOTENCY_CONFLICT')
        return actual

    def _commit(self, old: Run, **changes) -> Run:
        new = replace(old, revision=old.revision + 1, **changes)
        if not self.repository.compare_and_swap(old.revision, new):
            raise InputError('TASK_VERSION_CONFLICT')
        return new

    def claim(self, run_id: str, *, now: int, lease_seconds: int) -> Run:
        if type(now) is not int or type(lease_seconds) is not int or lease_seconds < 1:
            raise InputError('TASK_INPUT_INVALID')
        old = self.repository.get(run_id)
        if old.status != 'queued' or old.cancel_requested:
            raise InputError('TASK_NOT_QUEUED')
        if len(old.attempts) >= old.max_attempts:
            raise InputError('RETRY_LIMIT')
        attempt = Attempt(str(uuid4()), len(old.attempts) + 1, str(uuid4()), now + lease_seconds, 'running')
        return self._commit(old, status='running', attempts=old.attempts + (attempt,))

    def _owned(self, run_id, token, now):
        old = self.repository.get(run_id)
        if (old.status != 'running' or not old.attempts or old.attempts[-1].token != token
                or old.attempts[-1].status != 'running' or now >= old.attempts[-1].lease_expires):
            raise InputError('STALE_ATTEMPT')
        return old

    def heartbeat(self, run_id: str, *, token: str, now: int, lease_seconds: int) -> Run:
        if type(now) is not int or type(lease_seconds) is not int or lease_seconds < 1:
            raise InputError('TASK_INPUT_INVALID')
        old = self._owned(run_id, token, now)
        if old.cancel_requested:
            raise InputError('TASK_CANCELLED')
        attempt = replace(old.attempts[-1], lease_expires=max(old.attempts[-1].lease_expires, now + lease_seconds))
        return self._commit(old, attempts=old.attempts[:-1] + (attempt,))

    def cancel(self, run_id: str) -> Run:
        old = self.repository.get(run_id)
        if old.status == 'cancelled' or old.cancel_requested:
            return old
        if old.status not in ('queued', 'running'):
            raise InputError('TASK_TERMINAL')
        return self._commit(old, cancel_requested=True, status='cancelled' if old.status == 'queued' else 'running')

    def record_progress(self, run_id: str, *, token: str, now: int, stage: str,
                        processed_count: int, total_count: int | None) -> Run:
        old = self._owned(run_id, token, now)
        if old.cancel_requested:
            raise InputError('TASK_CANCELLED')
        stages = ('read', 'parse', 'finalize')
        previous = old.attempts[-1]
        if (stage not in stages or type(processed_count) is not int or processed_count < 0
                or (total_count is not None and (type(total_count) is not int or total_count < processed_count))):
            raise InputError('PROGRESS_INVALID')
        if stages.index(stage) < stages.index(previous.stage):
            raise InputError('PROGRESS_INVALID')
        if stage == previous.stage and (processed_count < previous.processed_count
                or previous.total_count is not None and total_count != previous.total_count):
            raise InputError('PROGRESS_INVALID')
        current = replace(previous, stage=stage, processed_count=processed_count, total_count=total_count)
        return self._commit(old, attempts=old.attempts[:-1] + (current,))

    def finish(self, run_id: str, *, token: str, now: int,
               parsed_ref: str | None = None, error_code: str | None = None) -> Run:
        old = self._owned(run_id, token, now)
        if error_code is not None and error_code not in PARSING_ERROR_CODES:
            raise InputError('TASK_INPUT_INVALID')
        if old.cancel_requested or error_code == 'TASK_CANCELLED':
            status, parsed_ref, error_code = 'cancelled', None, 'TASK_CANCELLED'
        elif error_code:
            status, parsed_ref = 'failed', None
        elif isinstance(parsed_ref, str) and parsed_ref.startswith('private:') and len(parsed_ref) > 8:
            status = 'succeeded'
        else:
            raise InputError('TASK_INPUT_INVALID')
        attempt = replace(old.attempts[-1], status=status, error_code=error_code)
        return self._commit(old, status=status, attempts=old.attempts[:-1] + (attempt,), parsed_ref=parsed_ref)

    def expire(self, run_id: str, *, now: int) -> Run:
        old = self.repository.get(run_id)
        if old.status != 'running' or now < old.attempts[-1].lease_expires:
            raise InputError('TASK_NOT_EXPIRED')
        cancelled = old.cancel_requested
        attempt = replace(old.attempts[-1], status='cancelled' if cancelled else 'expired',
                          error_code='TASK_CANCELLED' if cancelled else 'LEASE_EXPIRED')
        return self._commit(old, status='cancelled' if cancelled else 'failed', attempts=old.attempts[:-1] + (attempt,))

    def retry(self, run_id: str, *, expected_attempt: int, idempotency_key: str) -> Run:
        old = self.repository.get(run_id)
        if not idempotency_key or type(expected_attempt) is not int or expected_attempt < 1:
            raise InputError('TASK_INPUT_INVALID')
        prior = dict(old.retry_keys).get(idempotency_key)
        if prior is not None:
            if prior != expected_attempt:
                raise InputError('IDEMPOTENCY_CONFLICT')
            return old
        if old.status != 'failed' or old.parsed_ref is not None or old.cancel_requested:
            raise InputError('TASK_NOT_RETRYABLE')
        if len(old.attempts) != expected_attempt:
            raise InputError('TASK_VERSION_CONFLICT')
        if len(old.attempts) >= old.max_attempts:
            raise InputError('RETRY_LIMIT')
        return self._commit(old, status='queued', retry_keys=old.retry_keys + ((idempotency_key, expected_attempt),))
