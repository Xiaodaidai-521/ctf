"""Frozen M6 -> M1 teaching facts; M7/M8 remain explicitly disconnected.

Only this adapter tightens the legacy M1 duplicate comparison. No export
execution/authorization service participates in this teaching-only handoff.
"""
from copy import deepcopy
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from learning_map.models import VerificationFact
from learning_map.services import handoff as map_handoff
from skill_review import constants
from skill_review.models import (
    DownstreamNotice, RetestAssignment, SubmissionErrorCause, VerificationResult,
)
from skill_review.services import events

from .catalog import digest
from .common import short_id


def _uuid(value):
    return UUID(str(value)) if value not in (None, '') else None


def _assert_fact_matches(fact, normalized):
    # Compare *all* persisted contract fields, including first_attempt and the
    # JSON payload which the legacy receiver's duplicate check omits.
    for field, expected in normalized.items():
        if hasattr(expected, 'pk'):
            actual = getattr(fact, f'{field}_id')
            expected = expected.pk
        else:
            actual = getattr(fact, field)
        same = digest(actual) == digest(expected) if field == 'payload' else actual == expected
        if not same:
            raise map_handoff.FactConflict(f'相同 fact_id 对应不同内容（{field}），拒绝覆盖。')


@transaction.atomic
def ingest_fact(payload, actor=None):
    """Strict local adapter; returns M1's (fact, state, changed, created).

    The durable notice is JSON, but M1 compares UUIDField values with Python
    UUIDs. Convert a copy, never the frozen notice, before calling its API.
    """
    wire = deepcopy(payload)
    for field in ('attempt_id', 'retest_of_attempt_id'):
        wire[field] = _uuid(wire.get(field))
    normalized = map_handoff.normalize_fact_payload(wire)
    existing = VerificationFact.objects.select_for_update().filter(fact_id=normalized['fact_id']).first()
    if existing:
        _assert_fact_matches(existing, normalized)
    response = map_handoff.ingest_verification_fact(wire, actor=actor)
    # Also cover a competing insert observed by the receiver after our lookup.
    _assert_fact_matches(response[0], normalized)
    return response


def _assistance(result):
    snapshot = result.assistance_snapshot or {}
    level = int(snapshot.get('level') or 0)
    source = snapshot.get('source') or constants.ASSISTANCE_SOURCE_NONE
    shown = bool(snapshot.get('shown'))
    # Legacy teacher-help snapshots can say shown/assisted with level zero.
    # Preserve assisted status and source, while satisfying M1's level >= 1.
    if (result.independence == constants.INDEPENDENCE_ASSISTED and shown
            and source == constants.ASSISTANCE_SOURCE_TEACHER):
        level = max(1, level)
    return {'level': level, 'source': source, 'shown': shown}


def _fact_payload(result, capability, *, retest_of=None, correction_of=None):
    assistance = _assistance(result)
    point = capability.knowledge_points.order_by('sort_order', 'stable_id').first()
    return {
        # 51 chars, leaving room for M1's 'lm-fact-' prefix in a 64-char event ID.
        # Identity, not content: changing content cannot silently create a new ID.
        'fact_id': short_id('fact', _uuid(result.result_id), result.revision, capability.stable_id),
        'student': result.student_id,
        'catalog_version': result.catalog.version,
        'capability_id': capability.stable_id,
        'knowledge_point_id': point.stable_id if point else None,
        'task_key': result.task.task_key,
        'task_version': result.submission.task_version,
        'attempt_id': str(_uuid(result.attempt.attempt_id)),
        'outcome': {
            constants.OVERALL_PENDING: 'pending_review',
            constants.OVERALL_PENDING_MANUAL: 'pending_review',
            constants.OVERALL_PASSED: 'passed',
            constants.OVERALL_FAILED: 'failed',
            constants.OVERALL_VERIFICATION_FAILED: 'verification_failed',
            constants.OVERALL_ENVIRONMENT_AFFECTED: 'environment_affected',
        }.get(result.overall_status, 'unknown'),
        'independence': result.independence,
        'assistance_level': assistance['level'],
        'assistance_source': assistance['source'],
        'assistance_shown': assistance['shown'],
        'retest_of_attempt_id': str(_uuid(retest_of)) if retest_of else None,
        'first_attempt': bool(result.submission.first_effective),
        'evidence_ref': f'm6:{_uuid(result.result_id)}',
        'verifier_version': result.verifier_version or 'data-lab-rules-v1',
        # updated_at changes when fact IDs are acknowledged; never use it or now().
        'occurred_at': result.created_at.isoformat(),
        'payload': {
            'source': 'data_lab',
            'submission_id': str(_uuid(result.submission.submission_id)),
            'submission_payload_hash': result.submission.payload_hash,
            'result_id': str(_uuid(result.result_id)),
            'result_version': result.version,
            'result_revision': result.revision,
            'overall_status': result.overall_status,
            'program_status': result.program_status,
            'manual_status': result.manual_status,
            # M1 has no correction column; keep the link in its persisted JSON.
            'correction_of_fact_id': correction_of,
        },
    }


def _notice_key(result, target):
    return short_id('notice', _uuid(result.result_id), result.revision, target)


def _emit_delivery(notice):
    payload = notice.payload
    result = notice.result
    metadata = {
        'source': 'data_lab', 'binding': digest(payload),
        'task_id': result.task_id, 'task_key': payload['task_key'],
        'task_version': payload['task_version'], 'catalog_version': payload['catalog_version'],
        'attempt_id': payload['attempt_id'], 'submission_id': payload['submission_id'],
        'result_id': payload['result_id'], 'result_revision': payload['result_revision'],
        'capability_ids': [fact['capability_id'] for fact in payload['facts']],
        'knowledge_point_ids': [], 'evidence_ref': f"m6:{payload['result_id']}",
        'verifier_version': payload['verifier_version'],
        'assistance_level': payload['assistance']['level'],
        'assistance_source': payload['assistance']['source'],
        'assistance_shown': payload['assistance']['shown'],
        'overall_status': payload['overall_status'], 'independence': payload['independence'],
        'module1_sent': len(payload['facts']),
        'module7_status': constants.NOTICE_NOT_CONNECTED,
        'module8_status': constants.NOTICE_NOT_CONNECTED,
    }
    event, _ = events.emit_event(
        user=result.student, event_type='verification_result', event_id=payload['event_id'],
        catalog=result.catalog, task=result.task, extra=metadata,
    )
    if (event.user_id != payload['student_id'] or event.event_type != 'verification_result'
            or digest(event.metadata) != digest(metadata)):
        raise map_handoff.FactConflict('学习事件ID内容冲突；保存待重试。')


def _failed(notice, error):
    notice.attempts += 1
    notice.status = constants.NOTICE_FAILED
    notice.last_error = str(error)[:255]
    notice.sent_at = None
    notice.save(update_fields=['attempts', 'status', 'last_error', 'sent_at', 'updated_at'])
    return notice


def _send_notice(notice):
    """Caller holds result/notice locks. Keep failures outside the savepoint."""
    if notice.status == constants.NOTICE_SENT:
        return notice
    try:
        with transaction.atomic():
            facts = notice.payload['facts']
            if not facts:
                raise map_handoff.FactError('任务未绑定能力，不能确认模块一交接。')
            for payload in facts:
                ingest_fact(payload, actor=notice.correction.corrected_by if notice.correction_id else None)
            _emit_delivery(notice)
            # Old revision retries must not replace a newer revision's ID map.
            result = notice.result
            if result.revision == notice.payload['result_revision']:
                result.module1_fact_ids = {fact['capability_id']: fact['fact_id'] for fact in facts}
                result.save(update_fields=['module1_fact_ids', 'updated_at'])
    except Exception as exc:
        # Includes downstream path/event failures. The facts, states, events and
        # acknowledgement map roll back together; the original M6 result survives.
        return _failed(notice, exc)
    notice.attempts += 1
    notice.status = constants.NOTICE_SENT
    notice.last_error = ''
    notice.sent_at = timezone.now()
    notice.save(update_fields=['attempts', 'status', 'last_error', 'sent_at', 'updated_at'])
    return notice


@transaction.atomic
def dispatch_result(result, *, correction=None):
    """Return (module1_sent, notices); freeze each result *revision* once."""
    original = result
    result = VerificationResult.objects.select_for_update().select_related(
        'student', 'submission', 'attempt', 'task', 'catalog',
    ).get(pk=result.pk)
    existing = DownstreamNotice.objects.filter(notice_key=_notice_key(result, constants.NOTICE_MODULE1)).first()
    if not result.submission.first_effective and correction is None and existing is None:
        return False, []

    retest_of = RetestAssignment.objects.filter(started_attempt=result.attempt).values_list(
        'original_attempt__attempt_id', flat=True,
    ).first()
    previous = correction.original_result.module1_fact_ids if correction else {}
    capabilities = list(result.task.capabilities.order_by('stable_id'))
    facts = [_fact_payload(result, capability, retest_of=retest_of,
                           correction_of=(previous or {}).get(capability.stable_id))
             for capability in capabilities]
    shared = {
        'source': 'data_lab', 'schema': 'data-lab-handoff-v1',
        'student_id': result.student_id,
        'result_id': str(_uuid(result.result_id)),
        'submission_id': str(_uuid(result.submission.submission_id)),
        'attempt_id': str(_uuid(result.attempt.attempt_id)),
        'catalog_version': result.catalog.version,
        'task_key': result.task.task_key, 'task_version': result.submission.task_version,
        'result_version': result.version, 'result_revision': result.revision,
        'program_status': result.program_status, 'manual_status': result.manual_status,
        'overall_status': result.overall_status, 'independence': result.independence,
        'assistance': _assistance(result), 'verifier_version': result.verifier_version,
        'correction_id': str(_uuid(correction.correction_id)) if correction else None,
    }
    payloads = {
        constants.NOTICE_MODULE1: {
            **shared, 'facts': facts,
            'event_id': short_id('dispatch', _uuid(result.result_id), result.revision),
        },
        constants.NOTICE_MODULE7: {
            **shared, 'confirmed_error_causes': list(SubmissionErrorCause.objects.filter(
                submission=result.submission, status=constants.CAUSE_CONFIRMED,
            ).order_by('cause').values_list('cause', flat=True)),
        },
        constants.NOTICE_MODULE8: {
            **shared, 'reason': 'not_connected',
            'retest_assignment_id': str(RetestAssignment.objects.filter(
                completed_submission=result.submission,
            ).values_list('assignment_id', flat=True).first() or ''),
        },
    }
    notices = []
    conflict = False
    for target, payload in payloads.items():
        connected = target == constants.NOTICE_MODULE1
        notice, created = DownstreamNotice.objects.get_or_create(
            notice_key=_notice_key(result, target), defaults={
                'result': result, 'correction': correction, 'target': target,
                'target_connected': connected,
                'status': constants.NOTICE_PENDING if connected else constants.NOTICE_NOT_CONNECTED,
                'payload': payload,
            },
        )
        if connected and not created and digest(notice.payload) != digest(payload):
            _failed(notice, '相同事实/通知ID对应不同内容，拒绝覆盖冻结payload。')
            conflict = True
        notices.append(notice)
    if not conflict:
        _send_notice(notices[0])
    original.refresh_from_db(fields=['module1_fact_ids'])
    return notices[0].status == constants.NOTICE_SENT, notices


@transaction.atomic
def retry_module1_notice(notice):
    """Retry only the stored payload, never reconstruct it from a newer result."""
    if notice.target != constants.NOTICE_MODULE1:
        return notice
    # Use the same lock order as dispatch, including when different revisions
    # of the same result are delivered concurrently.
    result = VerificationResult.objects.select_for_update().get(pk=notice.result_id)
    notice = DownstreamNotice.objects.select_for_update().get(pk=notice.pk)
    notice.result = result
    return _send_notice(notice)
