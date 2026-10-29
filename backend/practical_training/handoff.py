"""Trusted adapter to module six's existing persistence and downstream contracts.

The public student submit endpoint intentionally cannot evaluate server evidence.
This adapter accepts only persisted, source-bound evidence produced in this app;
it does not change that endpoint or install a global verifier monkeypatch.
"""

from django.db import transaction
from django.utils import timezone

from skill_review import constants
from skill_review.models import SubmissionSnapshot, VerificationResult
from . import delivery
from skill_review.services.events import emit_event
from skill_review.services.submissions import assistance_snapshot, payload_hash
from skill_review.services.verification import compute_overall


@transaction.atomic
def deliver(evidence):
    if evidence.result_id:
        return evidence.result
    attempt = evidence.attempt
    now = timezone.now()
    assistance = assistance_snapshot(attempt=attempt, before=now)
    # Module one's assisted contract requires a 1–4 hint level. Preserve unknown
    # rather than inventing a level for the legacy level-zero teacher-help record.
    if assistance['shown'] and assistance['level'] == 0:
        assistance = {**assistance, 'independence': 'unknown', 'reason': 'legacy_teacher_level_unknown'}
    payload = {'evidence_ref': f'm5:{evidence.evidence_id}', 'content_hash': evidence.content_hash,
               'source': evidence.source, 'verifier_version': evidence.verifier_version}
    submission = SubmissionSnapshot.objects.create(
        client_submission_id=f'm5:{evidence.evidence_id}', attempt=attempt, student=attempt.student,
        task=attempt.task, catalog=attempt.catalog, task_version=attempt.task_version,
        sequence=SubmissionSnapshot.objects.filter(attempt=attempt).count() + 1,
        payload=payload, payload_hash=payload_hash(payload), assistance_snapshot=assistance,
        independence=assistance['independence'], answer_exposure=assistance['answer_exposure'],
        first_effective=not SubmissionSnapshot.objects.filter(attempt=attempt, first_effective=True).exists(),
        created_at=now,
    )
    status = {'passed': constants.PROGRAM_PASSED, 'failed': constants.PROGRAM_FAILED, 'error': constants.PROGRAM_ERROR}[evidence.status]
    overall = compute_overall(program_status=status, manual_status=constants.MANUAL_NOT_APPLICABLE,
                              manual_required=False, verification_error=evidence.error)
    result = VerificationResult.objects.create(
        submission=submission, attempt=attempt, student=attempt.student, task=attempt.task,
        catalog=attempt.catalog, program_status=status, manual_status=constants.MANUAL_NOT_APPLICABLE,
        overall_status=overall, independence=submission.independence, assistance_snapshot=assistance,
        verifier_version=evidence.verifier_version, verification_error=evidence.error,
        program_result={'evidence_ref': payload['evidence_ref'], 'content_hash': evidence.content_hash,
                        'observation': evidence.observation, 'source': evidence.source},
        item_results=[{'item_id': 'server_evidence', 'kind': 'program', 'status': evidence.status,
                       'evidence_ref': payload['evidence_ref']}],
    )
    attempt.status = 'verified'
    attempt.submitted_at = now
    attempt.submission_snapshot = {'submission_id': str(submission.submission_id), 'payload_hash': submission.payload_hash}
    attempt.save(update_fields=['status', 'submitted_at', 'submission_snapshot'])
    for event_type, suffix in (('task_submit', 'submit'), ('verification_result', 'result')):
        emit_event(user=attempt.student, event_type=event_type, event_id=f'm5-{suffix}-{evidence.evidence_id}',
                   catalog=attempt.catalog, task=attempt.task, attempt_id=attempt.attempt_id,
                   submission_id=submission.submission_id, result_id=result.result_id,
                   capability_ids=attempt.capability_ids, evidence_ref=payload['evidence_ref'],
                   verifier_version=evidence.verifier_version,
                   extra={'source': 'practical_training', 'program_status': status,
                          'overall_status': overall, 'save_status': 'saved'})
    evidence.result = result
    evidence.save(update_fields=['result'])
    delivery.dispatch(result)
    result.refresh_from_db(fields=['module1_fact_ids'])
    delivery.apply_retest(result)
    return result
