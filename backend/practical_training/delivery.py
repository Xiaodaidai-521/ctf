"""Module-six result/notice contracts with bounded module-five event IDs."""

from uuid import UUID

from django.db import transaction
from django.utils import timezone

from learning_map.services.handoff import ingest_verification_fact
from skill_review.models import DownstreamNotice, RetestAssignment
from skill_review.services.events import emit_event
from skill_review.services.submissions import payload_hash


def dispatch(result):
    assistance = result.assistance_snapshot
    retest = RetestAssignment.objects.filter(started_attempt=result.attempt).first()
    facts = []
    for capability in result.task.capabilities.all():
        point = capability.knowledge_points.order_by('sort_order', 'stable_id').first()
        facts.append({
            'fact_id': 'm5-' + payload_hash([str(result.result_id), capability.stable_id])[:40],
            'student': result.student_id, 'catalog_version': result.catalog.version,
            'capability_id': capability.stable_id, 'knowledge_point_id': point.stable_id if point else None,
            'task_key': result.task.task_key, 'task_version': result.submission.task_version,
            'attempt_id': str(result.attempt.attempt_id), 'outcome': result.overall_status,
            'independence': result.independence, 'assistance_level': assistance['level'],
            'assistance_source': assistance['source'], 'assistance_shown': assistance['shown'],
            'retest_of_attempt_id': str(retest.original_attempt.attempt_id) if retest else None,
            'first_attempt': result.submission.first_effective, 'evidence_ref': f'm6:{result.result_id}',
            'verifier_version': result.verifier_version, 'occurred_at': result.created_at.isoformat(),
            'payload': {'result_id': str(result.result_id), 'submission_id': str(result.submission.submission_id),
                        'source_evidence_ref': result.submission.payload['evidence_ref']},
        })
    notice, _ = DownstreamNotice.objects.get_or_create(
        notice_key=f'm5:{result.result_id}:module1',
        defaults={'result': result, 'target': 'module1', 'target_connected': True, 'payload': {'facts': facts}},
    )
    retry_notice(notice)
    return notice


@transaction.atomic
def retry_notice(notice):
    notice = DownstreamNotice.objects.select_for_update().get(pk=notice.pk)
    if notice.status == 'sent':
        return notice
    result = notice.result
    fact_ids = dict(result.module1_fact_ids)
    errors = []
    for raw in notice.payload['facts']:
        payload = dict(raw)
        # The shared in-process contract compares UUID values to DB UUID fields.
        for key in ('attempt_id', 'retest_of_attempt_id'):
            payload[key] = UUID(payload[key]) if payload.get(key) else None
        try:
            ingest_verification_fact(payload)
            fact_ids[payload['capability_id']] = payload['fact_id']
        except Exception as exc:
            errors.append(type(exc).__name__)
    result.module1_fact_ids = fact_ids
    result.save(update_fields=['module1_fact_ids'])
    notice.attempts += 1
    notice.status = 'failed' if errors else 'sent'
    notice.last_error = ','.join(errors)[:255]
    notice.sent_at = None if errors else timezone.now()
    notice.save(update_fields=['attempts', 'status', 'last_error', 'sent_at', 'updated_at'])
    return notice


def apply_retest(result):
    assignment = RetestAssignment.objects.filter(started_attempt=result.attempt).first()
    if not assignment:
        return
    assignment.completed_submission = result.submission
    assignment.completed_at = timezone.now()
    assignment.status = 'completed'
    outcome = result.overall_status
    if outcome == 'passed' and result.independence != 'independent':
        outcome = 'assisted' if result.independence == 'assisted' else 'unknown'
    assignment.outcome = outcome
    assignment.save()
    emit_event(user=result.student, event_type='retest_assign', event_id=f'm5-retest-{result.result_id}',
               catalog=result.catalog, task=result.task, attempt_id=result.attempt.attempt_id,
               submission_id=result.submission.submission_id, result_id=result.result_id,
               capability_ids=assignment.capability_ids, verifier_version=result.verifier_version,
               extra={'assignment_id': str(assignment.assignment_id), 'outcome': outcome,
                      'status': assignment.status, 'original_attempt_id': str(assignment.original_attempt.attempt_id)})
