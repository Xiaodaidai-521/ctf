from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .events import bounded_event_id, canonical_hash, record_teaching_event
from .models import PracticeAction
from .permissions import strip_sensitive_content, student_material_snapshot


ACTION_CONTRACTS = {
    'readonly_observation': (PracticeAction.STATUS_REGISTERED, ''),
    'data_export': (PracticeAction.STATUS_NOT_APPLICABLE, 'module5'),
    'sandbox_execute': (PracticeAction.STATUS_UNAVAILABLE, 'module4'),
}


class PracticeActionConflict(ValueError):
    pass


def task_snapshot(context):
    task = context.task
    return {
        'task_id': task.pk,
        'task_key': task.task_key,
        'task_version': context.attempt.task_version,
        'catalog_version': context.catalog.version,
        'title': task.title,
        'track': task.track,
        'purpose': task.purpose,
        'execution_mode': task.execution_mode,
        'capability_ids': list(context.attempt.capability_ids or []),
        'materials': student_material_snapshot(task),
        'acceptance': strip_sensitive_content(task.acceptance or {}),
        'practice_contracts': {
            action_type: {'status': status, 'dependency': dependency or None}
            for action_type, (status, dependency) in ACTION_CONTRACTS.items()
        },
        'submission': {
            'endpoint': f'/api/skill-review/attempts/{context.attempt.attempt_id}/submit/',
            'verification': 'deterministic_module6',
        },
    }


def register_practice_action(*, context, action_id, action_type, payload=None):
    if len(str(action_id)) > 64:
        raise ValidationError({'action_id': 'Must not exceed 64 characters.'})
    if action_type not in ACTION_CONTRACTS:
        raise ValidationError({'action_type': 'Unsupported practice action.'})
    status, dependency = ACTION_CONTRACTS[action_type]
    payload_hash = canonical_hash(payload or {})
    with transaction.atomic():
        existing = PracticeAction.objects.select_for_update().filter(action_id=action_id).first()
        if existing:
            if (
                existing.student_id != context.student_id
                or existing.run_id != context.run.id
                or existing.action_type != action_type
                or existing.payload_hash != payload_hash
            ):
                raise PracticeActionConflict('The action ID already exists with different content.')
            return existing, False
        action = PracticeAction.objects.create(
            action_id=action_id,
            student_id=context.student_id,
            run=context.run,
            attempt=context.attempt,
            action_type=action_type,
            payload_hash=payload_hash,
            status=status,
            dependency=dependency,
        )
        record_teaching_event(
            student=context.attempt.student,
            event_id=bounded_event_id('m2-action', action_id),
            event_type='tool_call_finished',
            attempt=context.attempt,
            run=context.run,
            payload={
                'action_id': action_id,
                'action_type': action_type,
                'status': status,
                'dependency': dependency or None,
                'evidence_ref': None,
            },
        )
        return action, True
