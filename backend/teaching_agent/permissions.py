from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rest_framework.exceptions import PermissionDenied


MATERIAL_STUDENT = 'student_material'
MATERIAL_HINT = 'hint'
MATERIAL_ANALYSIS = 'student_analysis'
MATERIAL_TEACHER_ANSWER = 'teacher_answer'
MATERIAL_SCORING_KEY = 'scoring_key'
MATERIAL_HIDDEN_VERIFIER = 'hidden_verifier'

NEVER_MODEL_MATERIALS = frozenset({
    MATERIAL_TEACHER_ANSWER,
    MATERIAL_SCORING_KEY,
    MATERIAL_HIDDEN_VERIFIER,
})

STUDENT_TOOL_MATRIX = {
    'data': frozenset({
        'read_student_profile',
        'read_user_knowledge_state',
        'read_learning_path_modules',
    }),
    'network': frozenset({
        'read_student_profile',
        'read_user_knowledge_state',
        'read_learning_path_modules',
    }),
}

SENSITIVE_KEYS = frozenset({
    'answer',
    'answers',
    'correct_answer',
    'correct_answers',
    'correct_options',
    'flag',
    'hidden',
    'hidden_checks',
    'hidden_verifier',
    'marking_key',
    'rubric',
    'scoring_key',
    'solution',
    'standard_answer',
    'teacher_answer',
    'validator',
})


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str


def _normalized_key(value: Any) -> str:
    return str(value or '').strip().lower().replace('-', '_').replace(' ', '_')


def strip_sensitive_content(value: Any) -> Any:
    """Return a prompt-safe copy, dropping server-only answer and verifier data."""
    if isinstance(value, dict):
        return {
            str(key): strip_sensitive_content(item)
            for key, item in value.items()
            if _normalized_key(key) not in SENSITIVE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [strip_sensitive_content(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def student_material_snapshot(task) -> dict[str, Any]:
    materials = task.materials if isinstance(task.materials, dict) else {}
    if materials.get('withdrawn'):
        return {'withdrawn': True, 'student_material_refs': []}
    return {
        'withdrawn': False,
        'student_material_refs': strip_sensitive_content(materials.get('student_material_refs') or []),
    }


def material_permission(*, material_type: str, context, requested_level: int | None = None) -> PermissionDecision:
    if material_type in NEVER_MODEL_MATERIALS:
        return PermissionDecision(False, 'server_only_material')
    if material_type == MATERIAL_STUDENT:
        return PermissionDecision(not context.task.materials_withdrawn, 'available' if not context.task.materials_withdrawn else 'withdrawn')
    if material_type == MATERIAL_HINT:
        level = int(requested_level or 0)
        allowed = 1 <= level <= 4 and level <= context.hint_level
        return PermissionDecision(allowed, 'unlocked' if allowed else 'hint_locked')
    if material_type == MATERIAL_ANALYSIS:
        return PermissionDecision(bool(context.analysis_unlocked), 'unlocked' if context.analysis_unlocked else 'analysis_locked')
    return PermissionDecision(False, 'unknown_material_type')


def allowed_tools(context) -> frozenset[str]:
    return STUDENT_TOOL_MATRIX.get(context.task.track, frozenset())


def require_tool_permission(context, tool_name: str) -> None:
    if tool_name not in allowed_tools(context):
        raise PermissionDenied(f'Tool is not permitted for this task: {tool_name}')
