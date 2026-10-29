from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from django.db import transaction
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from learning_map.models import TaskAttempt
from .models import TeachingRun
from .permissions import allowed_tools, student_material_snapshot


class TaskBoundLegacyEndpoint(APIException):
    status_code = 409
    default_code = 'task_tutoring_endpoint_required'
    default_detail = 'Task-bound tutoring must use the teaching run tutoring endpoint.'


ATTEMPT_LOCATOR_KEYS = ('attempt_id', 'task_attempt_id')
RUN_LOCATOR_KEYS = ('run_id', 'teaching_run_id')
CLIENT_AUTHORITY_KEYS = frozenset({
    'catalog_version',
    'context_version',
    'hint_level',
    'permission_version',
    'run_state',
    'state_version',
    'task_id',
    'task_version',
    'tools_allowed',
    'unlocked_materials',
})


@dataclass(frozen=True)
class TrustedTaskContext:
    student_id: int
    attempt: TaskAttempt
    run: TeachingRun | None
    hint_level: int
    state: str
    state_version: int
    context_version: int
    permission_version: int
    analysis_unlocked: bool = False

    @property
    def task(self):
        return self.attempt.task

    @property
    def catalog(self):
        return self.attempt.catalog

    def model_context(self) -> dict[str, Any]:
        """Minimal prompt input; intentionally excludes identity and answer keys."""
        task = self.task
        return {
            'schema_version': 'teaching-context/1',
            'task': {
                'task_key': task.task_key,
                'task_version': self.attempt.task_version,
                'catalog_version': self.catalog.version,
                'title': task.title,
                'track': task.track,
                'purpose': task.purpose,
                'execution_mode': task.execution_mode,
            },
            'attempt': {
                'attempt_id': str(self.attempt.attempt_id),
                'status': self.attempt.status,
                'evidence_ref': self.attempt.evidence_ref or None,
            },
            'runtime': {
                'run_id': str(self.run.run_id) if self.run else None,
                'state': self.state,
                'state_version': self.state_version,
                'hint_level': self.hint_level,
                'context_version': self.context_version,
                'permission_version': self.permission_version,
            },
            'materials': student_material_snapshot(task),
            'allowed_tools': sorted(allowed_tools(self)),
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _locator(data: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for source in (data, _mapping(data.get('context')), _mapping(data.get('agentContext')), _mapping(data.get('agent_context'))):
        for key in keys:
            value = source.get(key)
            if value not in (None, ''):
                return value
    return None


def has_task_locator(data: Mapping[str, Any] | None) -> bool:
    data = _mapping(data)
    return bool(_locator(data, ATTEMPT_LOCATOR_KEYS) or _locator(data, RUN_LOCATOR_KEYS))


def client_authority_fields(data: Mapping[str, Any] | None) -> set[str]:
    found = set()
    for source in (_mapping(data), _mapping(_mapping(data).get('context')), _mapping(_mapping(data).get('agentContext')), _mapping(_mapping(data).get('agent_context'))):
        found.update(CLIENT_AUTHORITY_KEYS.intersection(source.keys()))
    return found


def resolve_task_context(*, user, request_data: Mapping[str, Any], require_attempt: bool = False, challenge_id: Any = None) -> TrustedTaskContext | None:
    """Resolve every authorization-bearing field from server-side rows."""
    data = _mapping(request_data)
    attempt_id = _locator(data, ATTEMPT_LOCATOR_KEYS)
    run_id = _locator(data, RUN_LOCATOR_KEYS)

    if not attempt_id and not run_id:
        if require_attempt:
            raise ValidationError({'attempt_id': 'A claimed task attempt is required.'})
        return None

    run = None
    if run_id:
        try:
            run = TeachingRun.objects.select_related('attempt__task', 'attempt__catalog').get(run_id=run_id)
        except (TeachingRun.DoesNotExist, ValueError, TypeError):
            raise NotFound('Teaching run not found.')
        if run.student_id != getattr(user, 'id', None):
            raise PermissionDenied('This teaching run belongs to another student.')
        if attempt_id and str(run.attempt.attempt_id) != str(attempt_id):
            raise ValidationError({'attempt_id': 'Attempt does not match the teaching run.'})
        attempt = run.attempt
    else:
        try:
            attempt = TaskAttempt.objects.select_related('task', 'catalog').get(attempt_id=attempt_id)
        except (TaskAttempt.DoesNotExist, ValueError, TypeError):
            raise NotFound('Task attempt not found.')

    if attempt.student_id != getattr(user, 'id', None):
        raise PermissionDenied('This task attempt belongs to another student.')
    if challenge_id not in (None, '') and attempt.task.challenge_id != _as_int(challenge_id):
        raise PermissionDenied('Challenge is not authorized by this task attempt.')

    return TrustedTaskContext(
        student_id=attempt.student_id,
        attempt=attempt,
        run=run,
        hint_level=run.hint_level if run else 0,
        state=run.state if run else TeachingRun.STATE_READY,
        state_version=run.state_version if run else 0,
        context_version=run.context_version if run else 1,
        permission_version=run.permission_version if run else 1,
    )


def resolve_or_create_run(*, user, attempt_id: Any) -> tuple[TeachingRun, bool]:
    context = resolve_task_context(user=user, request_data={'attempt_id': attempt_id}, require_attempt=True)
    mode = {
        'data': TeachingRun.MODE_DATA_SECURITY,
        'network': TeachingRun.MODE_NETWORK_SECURITY,
    }.get(context.task.track, TeachingRun.MODE_REVIEW)
    with transaction.atomic():
        existing = (
            TeachingRun.objects.select_for_update()
            .filter(student=user, attempt=context.attempt)
            .exclude(state=TeachingRun.STATE_ENDED)
            .order_by('-created_at')
            .first()
        )
        if existing:
            return existing, False
        run = TeachingRun.objects.create(
            student=user,
            attempt=context.attempt,
            mode=mode,
            task_version=context.attempt.task_version,
            catalog_version=context.catalog.version,
            context_snapshot=context.model_context(),
        )
        run.context_snapshot = resolve_task_context(
            user=user,
            request_data={'run_id': run.run_id},
            require_attempt=True,
        ).model_context()
        run.save(update_fields=['context_snapshot', 'updated_at'])
        return run, True


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
