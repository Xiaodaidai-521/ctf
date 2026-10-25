"""Read-only adapter for module 6 facts.

Module 6 is being written in parallel in this workspace.  Module 7 therefore
never imports its models at module import time and never writes to them.  The
stable hand-off is:

* ``learning_map.VerificationFact`` — the fact module 6 already sends to module
  1 (verification conclusion, independence, assistance, retest link).
* ``learning_analytics.LearningEvent`` — the canonical hint request/show and
  teacher-help events.

If the module 6 extension tables are available, their assistance records,
current verification results and retest assignments are added as read-only
references.  If they are not migrated yet, the adapter reports
``skill_review_connected=false`` and continues with the stable facts.  It never
creates a fact, grade, hint or retest.
"""

from django.db import transaction

from learning_analytics.models import LearningEvent
from learning_map.models import VerificationFact

HINT_EVENT_TYPES = ('hint_request', 'hint_show', 'teacher_help', 'analysis_view')


def _iso(value):
    return value.isoformat() if value else None


def _fact_summary(fact):
    return {
        'fact_id': fact.fact_id,
        'outcome': fact.outcome,
        'independence': fact.independence,
        'assistance_level': fact.assistance_level,
        'assistance_source': fact.assistance_source,
        'assistance_shown': fact.assistance_shown,
        'retest_of_attempt_id': str(fact.retest_of_attempt_id or ''),
        'first_attempt': fact.first_attempt,
        'evidence_ref': fact.evidence_ref,
        'verifier_version': fact.verifier_version,
        'occurred_at': _iso(fact.occurred_at),
    }


def _event_summary(event):
    metadata = event.metadata or {}
    return {
        'event_id': event.event_id,
        'event_type': event.event_type,
        'level': int(metadata.get('assistance_level') or 0),
        'source': metadata.get('assistance_source') or 'none',
        'shown': bool(metadata.get('assistance_shown')),
        'event_time': _iso(event.event_time),
    }


def _empty_context():
    return {
        'module6_connected': True,
        'skill_review_connected': False,
        'verification_facts': [],
        'hint_events': [],
        'teacher_help_events': [],
        'assistance_records': [],
        'verification_results': [],
        'retest_assignments': [],
        'hint_record_status': 'unknown',
        'help_shown': False,
        'retest_present': False,
        'notes': [],
    }


def collect_attempt_context(attempt):
    """Return a compact, read-only module 6 context for one attempt.

    No answer text, student identity or credential is returned.  The caller
    stores this as a reference snapshot, not as a new learning fact.
    """

    context = _empty_context()
    if attempt is None:
        context['module6_connected'] = False
        context['notes'].append('未关联任务尝试，无法读取模块六事实。')
        return context

    facts = list(
        VerificationFact.objects.filter(
            student=attempt.student,
            attempt_id=attempt.attempt_id,
        ).select_related('capability').order_by('-occurred_at')[:20]
    )
    context['verification_facts'] = [_fact_summary(fact) for fact in facts]
    context['retest_present'] = bool(facts) and any(
        fact.retest_of_attempt_id or fact.task_version != attempt.task_version
        for fact in facts
    )

    try:
        events = list(
            LearningEvent.objects.filter(
                user=attempt.student,
                event_type__in=HINT_EVENT_TYPES,
                metadata__attempt_id=str(attempt.attempt_id),
            ).order_by('-event_time')[:50]
        )
    except Exception:
        # JSON key lookup is supported by the configured databases, but a
        # defensive fallback keeps the feedback submission readable.
        events = [
            event for event in LearningEvent.objects.filter(
                user=attempt.student, event_type__in=HINT_EVENT_TYPES,
            ).order_by('-event_time')[:200]
            if str((event.metadata or {}).get('attempt_id') or '') == str(attempt.attempt_id)
        ]

    hint_events = [event for event in events if event.event_type in ('hint_request', 'hint_show')]
    teacher_events = [event for event in events if event.event_type == 'teacher_help']
    context['hint_events'] = [_event_summary(event) for event in hint_events]
    context['teacher_help_events'] = [_event_summary(event) for event in teacher_events]
    context['help_shown'] = any(item['shown'] for item in context['hint_events'] + context['teacher_help_events'])
    context['hint_record_status'] = 'present' if (hint_events or teacher_events) else 'unknown'
    if not (hint_events or teacher_events):
        context['notes'].append('未发现提示或教师帮助事件；帮助状态未知，不能推定独立。')

    # Optional read-only module 6 extension tables.  A nested atomic block makes
    # a missing table safe even on PostgreSQL, where a failed statement would
    # otherwise abort the surrounding transaction.
    try:
        with transaction.atomic():
            from skill_review.models import (  # noqa: WPS433 (optional integration)
                AssistanceRecord,
                RetestAssignment,
                VerificationResult,
            )

            assistance = list(
                AssistanceRecord.objects.filter(attempt=attempt).order_by('-created_at')[:50]
            )
            context['assistance_records'] = [
                {
                    'record_id': str(record.record_id),
                    'kind': record.kind,
                    'level': record.level,
                    'source': record.source,
                    'shown': record.shown,
                    'shown_at': _iso(record.shown_at),
                    'content_ref': record.content_ref,
                }
                for record in assistance
            ]
            if assistance:
                context['hint_record_status'] = 'present'
                context['help_shown'] = context['help_shown'] or any(record.shown for record in assistance)

            results = list(
                VerificationResult.objects.filter(
                    attempt=attempt, is_current=True,
                ).order_by('-created_at')[:5]
            )
            context['verification_results'] = [
                {
                    'result_id': str(result.result_id),
                    'version': result.version,
                    'revision': result.revision,
                    'program_status': result.program_status,
                    'manual_status': result.manual_status,
                    'overall_status': result.overall_status,
                    'independence': result.independence,
                    'verifier_version': result.verifier_version,
                    'rubric_version': result.rubric_version,
                }
                for result in results
            ]

            retests = list(
                RetestAssignment.objects.filter(original_attempt=attempt).order_by('-created_at')[:5]
            )
            context['retest_assignments'] = [
                {
                    'assignment_id': str(assignment.assignment_id),
                    'status': assignment.status,
                    'due_at': _iso(assignment.due_at),
                    'outcome': assignment.outcome,
                    'selected_task_id': assignment.selected_task_id,
                    'started_attempt_id': str(assignment.started_attempt.attempt_id) if assignment.started_attempt else '',
                }
                for assignment in retests
            ]
            context['retest_present'] = context['retest_present'] or bool(retests)
            context['skill_review_connected'] = True
    except Exception:
        context['skill_review_connected'] = False
        context['notes'].append(
            '模块六扩展表当前不可用或尚未迁移；已使用模块一核验事实与统一学习事件作为只读引用。'
        )

    return context
