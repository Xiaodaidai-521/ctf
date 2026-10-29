from __future__ import annotations

import hashlib
import json

from learning_analytics.events import record_learning_event


def bounded_event_id(prefix: str, *parts: object) -> str:
    raw = ':'.join([prefix, *[str(part) for part in parts]])
    if len(raw) <= 64:
        return raw
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]
    return f'{prefix[:40]}:{digest}'[:64]


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def record_teaching_event(*, student, event_id: str, event_type: str, attempt, run=None, payload=None):
    metadata = {
        'schema_version': 'module2.event/1',
        'attempt_id': str(attempt.attempt_id),
        'task_id': attempt.task_id,
        'task_key': attempt.task.task_key,
        'task_version': attempt.task_version,
        'catalog_version': attempt.catalog.version,
        'run_id': str(run.run_id) if run else None,
        'state': run.state if run else None,
        'state_version': run.state_version if run else 0,
        'payload': payload or {},
    }
    return record_learning_event(
        student,
        event_type,
        metadata,
        event_id=event_id,
        strict=True,
    )
