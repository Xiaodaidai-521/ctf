"""Deterministic state transitions from module-6 verification facts.

No model is involved.  The rules are intentionally boring so the same fact
and the same rule version always produce the same path state.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .. import constants
from .events import emit_event
from ..models import CapabilityState, PathChangeLog, VerificationFact


def get_or_create_state(student, catalog, capability):
    state, _ = CapabilityState.objects.get_or_create(
        student=student,
        catalog=catalog,
        capability=capability,
        defaults={
            'state': constants.STATE_NEEDS_DIAGNOSIS,
            'rule_version': catalog.rule_version or constants.RULE_VERSION,
        },
    )
    return state


def record_state_change(*, state, from_state, to_state, reason, fact=None, actor=None, rule_version=None):
    state.state = to_state
    state.reason_code = reason
    state.last_fact = fact
    if fact and fact.evidence_ref:
        state.evidence_ref = fact.evidence_ref
    state.rule_version = rule_version or state.rule_version or constants.RULE_VERSION
    state.save()
    PathChangeLog.objects.create(
        student=state.student,
        catalog=state.catalog,
        capability=state.capability,
        from_state=from_state,
        to_state=to_state,
        trigger_fact=fact,
        reason=reason,
        actor=actor,
        rule_version=state.rule_version,
    )
    return state


def _retest_due_at(fact):
    days = int(getattr(settings, 'LEARNING_MAP_RETEST_INTERVAL_DAYS', 3))
    return fact.occurred_at + timedelta(days=days)


def derive_state(fact):
    """Return ``(state, reason, retest_due_at)`` for one verification fact."""

    is_retest = bool(fact.retest_of_attempt_id)
    if fact.outcome == constants.OUTCOME_PASSED:
        if fact.independence == constants.INDEPENDENCE_INDEPENDENT:
            return constants.STATE_INDEPENDENT, 'retest_independent_pass' if is_retest else 'independent_pass', None
        if fact.independence == constants.INDEPENDENCE_ASSISTED:
            return (
                constants.STATE_ASSISTED_PASS,
                'retest_assisted_pass' if is_retest else 'assisted_pass',
                _retest_due_at(fact),
            )
        return constants.STATE_UNKNOWN, 'help_record_unknown', None

    if fact.outcome == constants.OUTCOME_FAILED:
        return constants.STATE_NEEDS_PRACTICE, 'retest_failed' if is_retest else 'verification_not_passed', None
    if fact.outcome == constants.OUTCOME_PENDING_REVIEW:
        return constants.STATE_PENDING_REVIEW, 'pending_teacher_review', None
    if fact.outcome == constants.OUTCOME_VERIFICATION_FAILED:
        return constants.STATE_PENDING_VERIFICATION, 'verification_service_failed', None
    if fact.outcome == constants.OUTCOME_ENVIRONMENT_AFFECTED:
        return constants.STATE_ENVIRONMENT_AFFECTED, 'environment_affected', None
    return constants.STATE_UNKNOWN, 'unknown_evidence', None


def apply_fact(fact, actor=None):
    """Apply a persisted verification fact and log the exact transition.

    A completed attempt is frozen: later non-retest facts do not downgrade an
    ``independent`` state.  A retest always re-evaluates, which is how a failed
    delayed retest can return the student to practice.
    """

    state = get_or_create_state(fact.student, fact.catalog, fact.capability)
    previous = state.state

    if previous == constants.STATE_INDEPENDENT and not fact.retest_of_attempt_id:
        return state, False

    new_state, reason, retest_due = derive_state(fact)
    if new_state == previous and reason == state.reason_code:
        return state, False

    state.retest_due_at = retest_due
    state = record_state_change(
        state=state,
        from_state=previous,
        to_state=new_state,
        reason=reason,
        fact=fact,
        actor=actor,
        rule_version=fact.catalog.rule_version or constants.RULE_VERSION,
    )
    emit_event(
        user=fact.student,
        event_type='path_update',
        catalog=fact.catalog,
        task=fact.task,
        attempt_id=fact.attempt_id,
        capability_ids=[fact.capability.stable_id],
        evidence_ref=fact.evidence_ref,
        verifier_version=fact.verifier_version,
        extra={
            'from_state': previous,
            'to_state': new_state,
            'reason_code': reason,
            'retest_of_attempt_id': str(fact.retest_of_attempt_id or ''),
            'fact_id': fact.fact_id,
        },
    )
    return state, True


def refresh_due_retests(student, catalog, now=None):
    """Move assisted passes whose retest is due into ``retest_pending``."""

    now = now or timezone.now()
    updated = []
    states = CapabilityState.objects.filter(
        student=student,
        catalog=catalog,
        state=constants.STATE_ASSISTED_PASS,
        retest_due_at__lte=now,
    ).select_related('capability')
    for state in states:
        previous = state.state
        record_state_change(
            state=state,
            from_state=previous,
            to_state=constants.STATE_RETEST_PENDING,
            reason='retest_due',
            fact=state.last_fact,
            rule_version=catalog.rule_version or constants.RULE_VERSION,
        )
        emit_event(
            user=student,
            event_type='path_update',
            catalog=catalog,
            capability_ids=[state.capability.stable_id],
            extra={
                'from_state': previous,
                'to_state': constants.STATE_RETEST_PENDING,
                'reason_code': 'retest_due',
                'rule_version': catalog.rule_version or constants.RULE_VERSION,
            },
        )
        updated.append(state)
    return updated


def state_for_student(student, catalog):
    return {
        state.capability_id: state
        for state in CapabilityState.objects.filter(student=student, catalog=catalog).select_related('capability')
    }


def verification_fact_summary(fact):
    return {
        'fact_id': fact.fact_id,
        'outcome': fact.outcome,
        'independence': fact.independence,
        'assistance_level': fact.assistance_level,
        'assistance_source': fact.assistance_source,
        'assistance_shown': fact.assistance_shown,
        'retest_of_attempt_id': str(fact.retest_of_attempt_id) if fact.retest_of_attempt_id else None,
        'evidence_ref': fact.evidence_ref,
        'verifier_version': fact.verifier_version,
        'occurred_at': fact.occurred_at.isoformat() if fact.occurred_at else None,
        'capability_id': fact.capability.stable_id,
        'task_key': fact.task.task_key if fact.task else '',
        'task_version': fact.task_version,
    }
