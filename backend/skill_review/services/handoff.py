"""Module 6 → module 1 / 7 / 8 hand-off.

Module 1 is connected locally and receives a verification fact for every result
revision.  Modules 7 and 8 are **not connected** in this build: their notices
are stored with ``status=not_connected`` so the gap is visible instead of
pretending a delivery succeeded.
"""

from django.conf import settings
from django.utils import timezone

from . import events
from .. import constants
from ..models import DownstreamNotice, RetestAssignment, SubmissionErrorCause


def _outcome(result):
    return {
        constants.OVERALL_PASSED: 'passed',
        constants.OVERALL_FAILED: 'failed',
        constants.OVERALL_PENDING_MANUAL: 'pending_review',
        constants.OVERALL_PENDING: 'pending_review',
        constants.OVERALL_VERIFICATION_FAILED: 'verification_failed',
        constants.OVERALL_ENVIRONMENT_AFFECTED: 'environment_affected',
        constants.OVERALL_UNKNOWN: 'unknown',
    }.get(result.overall_status, 'unknown')


def _assistance(result):
    snapshot = result.assistance_snapshot or {}
    return {
        'level': int(snapshot.get('level') or 0),
        'source': snapshot.get('source') or 'none',
        'shown': bool(snapshot.get('shown')),
    }


def _retest_original_attempt(result):
    assignment = RetestAssignment.objects.filter(
        started_attempt=result.attempt,
    ).first()
    return assignment.original_attempt.attempt_id if assignment else None


def _fact_payload(result, capability, correction_of_fact_id=None):
    assistance = _assistance(result)
    knowledge_point = capability.knowledge_points.order_by('sort_order', 'stable_id').first()
    retest_of = _retest_original_attempt(result)
    return {
        'fact_id': (
            f'm6-{result.submission.submission_id}-{result.result_id}-'
            f'{capability.stable_id}-r{result.revision}'
        ),
        'student': result.student_id,
        'catalog_version': result.catalog.version,
        'capability_id': capability.stable_id,
        'knowledge_point_id': knowledge_point.stable_id if knowledge_point else None,
        'task_key': result.task.task_key,
        'task_version': result.task.version,
        'attempt_id': str(result.attempt.attempt_id),
        'outcome': _outcome(result),
        'independence': result.independence,
        'assistance_level': assistance['level'],
        'assistance_source': assistance['source'],
        'assistance_shown': assistance['shown'],
        'retest_of_attempt_id': str(retest_of) if retest_of else None,
        'first_attempt': bool(result.submission.first_effective),
        'evidence_ref': f'm6:{result.result_id}',
        'verifier_version': result.verifier_version or 'm6-rules-v1',
        'occurred_at': timezone.now().isoformat(),
        'correction_of_fact_id': correction_of_fact_id,
        'payload': {
            'submission_id': str(result.submission.submission_id),
            'result_id': str(result.result_id),
            'result_version': result.version,
            'result_revision': result.revision,
            'overall_status': result.overall_status,
            'program_status': result.program_status,
            'manual_status': result.manual_status,
        },
    }


def _notice_key(result, target, correction=None):
    return f'{result.result_id}:{target}:{correction.correction_id if correction else "initial"}'


def dispatch_result(result, *, correction=None):
    """Deliver module-1 facts and record notices for all targets.

    Returns ``(module1_sent, notices)``.  A module-1 failure never rewrites the
    result; it is stored as a failed notice for retry.
    """

    from learning_map.services.handoff import FactConflict, ingest_verification_fact

    if not result.submission.first_effective and correction is None:
        return False, []

    previous_fact_ids = {}
    if correction is not None and correction.original_result_id:
        previous_fact_ids = correction.original_result.module1_fact_ids or {}

    capabilities = list(result.task.capabilities.all())
    fact_ids = {}
    payloads = []
    errors = []
    sent_count = 0
    for capability in capabilities:
        correction_of = previous_fact_ids.get(capability.stable_id)
        payload = _fact_payload(result, capability, correction_of_fact_id=correction_of)
        payloads.append(payload)
        try:
            ingest_verification_fact(payload, actor=correction.corrected_by if correction else None)
            fact_ids[capability.stable_id] = payload['fact_id']
            sent_count += 1
        except (FactConflict, Exception) as exc:  # keep the result even if downstream rejects
            errors.append(f'{capability.stable_id}: {exc}')

    if fact_ids:
        merged = dict(result.module1_fact_ids or {})
        merged.update(fact_ids)
        result.module1_fact_ids = merged
        result.save(update_fields=['module1_fact_ids', 'updated_at'])

    notice_payload = {
        'result_id': str(result.result_id),
        'submission_id': str(result.submission.submission_id),
        'attempt_id': str(result.attempt.attempt_id),
        'catalog_version': result.catalog.version,
        'task_key': result.task.task_key,
        'task_version': result.task.version,
        'overall_status': result.overall_status,
        'independence': result.independence,
        'facts': payloads,
        'errors': errors,
    }
    notice, _ = DownstreamNotice.objects.update_or_create(
        notice_key=_notice_key(result, constants.NOTICE_MODULE1, correction),
        defaults={
            'result': result,
            'correction': correction,
            'target': constants.NOTICE_MODULE1,
            'target_connected': True,
            'status': (
                constants.NOTICE_SENT if sent_count and not errors
                else constants.NOTICE_FAILED
            ),
            'payload': notice_payload,
            'attempts': 1,
            'last_error': '; '.join(errors)[:255],
            'sent_at': timezone.now() if sent_count and not errors else None,
        },
    )

    causes = list(
        SubmissionErrorCause.objects.filter(
            submission=result.submission, status=constants.CAUSE_CONFIRMED,
        ).values_list('cause', flat=True)
    )
    module7_payload = {
        'result_id': str(result.result_id),
        'task_key': result.task.task_key,
        'task_version': result.task.version,
        'catalog_version': result.catalog.version,
        'confirmed_error_causes': causes,
        'correction_id': str(correction.correction_id) if correction else None,
    }
    module7_notice, _ = DownstreamNotice.objects.update_or_create(
        notice_key=_notice_key(result, constants.NOTICE_MODULE7, correction),
        defaults={
            'result': result,
            'correction': correction,
            'target': constants.NOTICE_MODULE7,
            'target_connected': False,
            'status': constants.NOTICE_NOT_CONNECTED,
            'payload': module7_payload,
            'attempts': 0,
        },
    )

    module8_payload = {
        'result_id': str(result.result_id),
        'task_key': result.task.task_key,
        'task_version': result.task.version,
        'catalog_version': result.catalog.version,
        'program_status': result.program_status,
        'manual_status': result.manual_status,
        'overall_status': result.overall_status,
        'independence': result.independence,
        'retest_assignment_id': str(
            RetestAssignment.objects.filter(completed_submission=result.submission)
            .values_list('assignment_id', flat=True).first() or ''
        ),
        'correction_id': str(correction.correction_id) if correction else None,
    }
    module8_notice, _ = DownstreamNotice.objects.update_or_create(
        notice_key=_notice_key(result, constants.NOTICE_MODULE8, correction),
        defaults={
            'result': result,
            'correction': correction,
            'target': constants.NOTICE_MODULE8,
            'target_connected': False,
            'status': constants.NOTICE_NOT_CONNECTED,
            'payload': module8_payload,
            'attempts': 0,
        },
    )

    events.emit_event(
        user=result.student,
        event_type='verification_result',
        event_id=f'm6-dispatch-{result.result_id}-{result.revision}-{correction.correction_id if correction else "initial"}',
        catalog=result.catalog,
        task=result.task,
        attempt_id=result.attempt.attempt_id,
        submission_id=result.submission.submission_id,
        result_id=result.result_id,
        capability_ids=[capability.stable_id for capability in capabilities],
        evidence_ref=f'm6:{result.result_id}',
        verifier_version=result.verifier_version,
        extra={
            'overall_status': result.overall_status,
            'module1_sent': sent_count,
            'module1_errors': errors[:3],
            'module7_status': module7_notice.status,
            'module8_status': module8_notice.status,
        },
    )
    return sent_count == len(capabilities) and not errors, [notice, module7_notice, module8_notice]


def retry_module1_notice(notice):
    """Retry one failed module-1 notice; no other target is retried."""

    from learning_map.services.handoff import ingest_verification_fact

    if notice.target != constants.NOTICE_MODULE1:
        return notice
    notice.attempts += 1
    errors = []
    for payload in notice.payload.get('facts', []):
        try:
            ingest_verification_fact(payload, actor=None)
        except Exception as exc:
            errors.append(str(exc))
    notice.last_error = '; '.join(errors)[:255]
    notice.status = constants.NOTICE_FAILED if errors else constants.NOTICE_SENT
    notice.sent_at = None if errors else timezone.now()
    notice.save(update_fields=['attempts', 'last_error', 'status', 'sent_at', 'updated_at'])
    return notice
