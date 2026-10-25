"""Deterministic basic diagnosis.

A diagnostic answer is evidence for arranging the learning order, not proof of
mastery.  Correct answers never create an independent-pass state; unanswered
questions are "insufficient", never "weak".
"""

from django.db import transaction
from django.utils import timezone

from .. import constants
from .events import emit_event
from .pathing import get_or_create_state, record_state_change
from ..models import DiagnosticQuestion, DiagnosticSession


class DiagnosisError(ValueError):
    pass


def question_statuses(catalog):
    if catalog.status == constants.CATALOG_STATUS_PUBLISHED:
        return ['frozen']
    return ['draft', 'reviewed', 'frozen']


def questions_for(catalog, tracks):
    if isinstance(tracks, str):
        tracks = [tracks]
    return list(
        DiagnosticQuestion.objects.filter(
            catalog=catalog,
            track__in=tracks,
            status__in=question_statuses(catalog),
        ).select_related('capability').order_by('track', 'sort_order', 'question_key', 'version')
    )


def serialize_questions(catalog, tracks):
    payload = []
    for question in DiagnosticQuestion.objects.filter(
        catalog=catalog,
        track__in=tracks,
        status__in=question_statuses(catalog),
    ).select_related('capability').order_by('track', 'sort_order', 'question_key'):
        payload.append({
            'question_key': question.question_key,
            'track': question.track,
            'dimension_label': constants.DIMENSION_LABELS.get(question.dimension, question.dimension),
            'capability_title': question.capability.title,
            'prompt': question.prompt,
            'options': [
                {'key': option.get('key'), 'label': option.get('label')}
                for option in (question.options or [])
            ],
        })
    return payload


def _normalize_answer(value):
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value}
    return {str(value)}


@transaction.atomic
def submit_diagnosis(*, student, catalog, goal_track, answers, session_id=None):
    if goal_track not in (constants.TRACK_DATA, constants.TRACK_NETWORK, constants.TRACK_BOTH):
        raise DiagnosisError('目标主线不合法。')
    if not isinstance(answers, dict):
        raise DiagnosisError('作答必须是题目键到选项的映射。')

    tracks = [constants.TRACK_DATA, constants.TRACK_NETWORK] if goal_track == constants.TRACK_BOTH else [goal_track]
    questions = questions_for(catalog, tracks)
    if not questions:
        raise DiagnosisError('该主线暂无已审核诊断题，请等待课程补充。')

    by_key = {question.question_key: question for question in questions}
    unknown = [key for key in answers if key not in by_key]
    if unknown:
        raise DiagnosisError(f'未知诊断题：{", ".join(sorted(unknown))}')

    session = None
    if session_id:
        session = DiagnosticSession.objects.filter(
            session_id=session_id, student=student, catalog=catalog, status='in_progress',
        ).first()
        if not session:
            raise DiagnosisError('诊断会话不存在或已结束。')
    if session is None:
        session = DiagnosticSession(student=student, catalog=catalog, goal_track=goal_track)

    per_capability = {}
    unanswered = []
    answered_count = 0
    for key, question in by_key.items():
        entry = per_capability.setdefault(question.capability.stable_id, {
            'capability_id': question.capability.stable_id,
            'track': question.track,
            'dimension': question.dimension,
            'answered': 0,
            'questions': 0,
            'correct_points': 0,
            'total_points': 0,
        })
        entry['questions'] += 1
        entry['total_points'] += question.points
        if key not in answers or answers.get(key) in (None, '', []):
            unanswered.append(key)
            continue
        answered_count += 1
        entry['answered'] += 1
        selected = _normalize_answer(answers.get(key))
        correct = _normalize_answer(question.correct_options)
        if selected == correct:
            entry['correct_points'] += question.points

    for entry in per_capability.values():
        if entry['answered'] == 0:
            entry['result'] = constants.DIAGNOSIS_INSUFFICIENT
        elif entry['correct_points'] == entry['total_points']:
            entry['result'] = constants.DIAGNOSIS_LIKELY_MASTERED
        else:
            entry['result'] = constants.DIAGNOSIS_NEEDS_LEARNING

    result = {
        'goal_track': goal_track,
        'question_count': len(by_key),
        'answered_count': answered_count,
        'unanswered_keys': sorted(unanswered),
        'capabilities': {
            stable_id: per_capability[stable_id]
            for stable_id in sorted(per_capability)
        },
    }

    session.goal_track = goal_track
    session.answers = answers
    session.result = result
    session.status = 'completed'
    session.completed_at = timezone.now()
    session.rule_version = catalog.rule_version or constants.RULE_VERSION
    session.save()

    for stable_id, entry in sorted(per_capability.items()):
        capability = catalog.capabilities.get(stable_id=stable_id)
        state = get_or_create_state(student, catalog, capability)
        if state.state in (constants.STATE_NEEDS_DIAGNOSIS, 'not_attempted', constants.STATE_DIAGNOSED):
            state.diagnosis_result = entry['result']
            if state.state != constants.STATE_DIAGNOSED:
                record_state_change(
                    state=state,
                    from_state=state.state,
                    to_state=constants.STATE_DIAGNOSED,
                    reason='basic_diagnosis_completed',
                    rule_version=catalog.rule_version or constants.RULE_VERSION,
                )
            else:
                state.save(update_fields=['diagnosis_result', 'updated_at'])

    emit_event(
        user=student,
        event_type='diagnosis_submit',
        event_id=f'lm-diagnosis-{session.session_id}',
        catalog=catalog,
        capability_ids=sorted(per_capability),
        extra={
            'session_id': str(session.session_id),
            'goal_track': goal_track,
            'answered_count': answered_count,
            'question_count': len(by_key),
            'ai_used': False,
        },
    )

    return session
