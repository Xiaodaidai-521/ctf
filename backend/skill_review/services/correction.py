"""Versioned corrections for verification results.

The original result is never edited.  A correction creates a new result version
that supersedes it, records before/after snapshots and triggers module-1
recalculation plus module-7/8 notices.
"""

from django.db import transaction
from django.utils import timezone

from . import events, handoff, verification
from .. import constants
from ..models import (
    ManualReviewTask,
    ResultCorrection,
    SubmissionSnapshot,
    TeacherSamplingItem,
    VerificationResult,
)


class CorrectionError(ValueError):
    code = 'correction_invalid'


ALLOWED_CHANGES = {
    'program_status',
    'manual_status',
    'manual_result',
    'item_results',
    'verification_error',
    'independence',
    'assistance_snapshot',
    'overall_status',
}
FINAL_OVERALL = {
    constants.OVERALL_PASSED,
    constants.OVERALL_FAILED,
    constants.OVERALL_VERIFICATION_FAILED,
    constants.OVERALL_ENVIRONMENT_AFFECTED,
    constants.OVERALL_UNKNOWN,
    constants.OVERALL_PENDING_MANUAL,
}


@transaction.atomic
def create_correction(
    *,
    submission,
    actor,
    source,
    reason,
    changes,
    sampling_item=None,
):
    if source not in dict(constants.CORRECTION_SOURCE_CHOICES):
        raise CorrectionError('更正来源不合法。')
    if not reason.strip():
        raise CorrectionError('更正理由不能为空。')
    unknown = set(changes) - ALLOWED_CHANGES
    if unknown:
        raise CorrectionError(f'不允许更正字段：{", ".join(sorted(unknown))}')

    original = VerificationResult.objects.filter(
        submission=submission, is_current=True,
    ).first()
    if not original:
        raise CorrectionError('没有可更正的当前结果。')

    new_independence = changes.get('independence', original.independence)
    new_assistance = changes.get('assistance_snapshot', original.assistance_snapshot or {})
    if new_independence == constants.INDEPENDENCE_ASSISTED:
        if not new_assistance.get('shown') or int(new_assistance.get('level') or 0) < 1:
            raise CorrectionError('更正为受助时必须同时提供实际展示的帮助层级和来源。')
        if new_assistance.get('source') in (
            constants.ASSISTANCE_SOURCE_NONE, constants.ASSISTANCE_SOURCE_UNKNOWN,
        ):
            raise CorrectionError('更正为受助时必须注明帮助来源。')
    if new_independence == constants.INDEPENDENCE_INDEPENDENT and new_assistance.get('shown'):
        raise CorrectionError('实际展示过帮助时不能更正为平台内独立。')

    new_program = changes.get('program_status', original.program_status)
    new_manual = changes.get('manual_status', original.manual_status)
    new_error = changes.get('verification_error', original.verification_error)
    new_manual_result = changes.get('manual_result', original.manual_result or {})
    if new_manual == constants.MANUAL_REVIEWED and not new_manual_result.get('decision'):
        raise CorrectionError('人工评阅为已评阅时必须提供评阅结论。')

    if 'overall_status' in changes:
        overall = changes['overall_status']
        if overall not in FINAL_OVERALL:
            raise CorrectionError('综合结论取值不合法。')
    else:
        overall = verification.compute_overall(
            program_status=new_program,
            manual_status=new_manual,
            manual_required=original.manual_status != constants.MANUAL_NOT_APPLICABLE,
            manual_decision=new_manual_result.get('decision'),
            verification_error=new_error,
        )

    before = {
        'version': original.version,
        'program_status': original.program_status,
        'manual_status': original.manual_status,
        'overall_status': original.overall_status,
        'independence': original.independence,
        'item_results': original.item_results,
        'manual_result': original.manual_result,
    }

    original.is_current = False
    original.save(update_fields=['is_current', 'updated_at'])

    next_version = (
        VerificationResult.objects.filter(submission=submission)
        .order_by('-version').values_list('version', flat=True).first() or 0
    ) + 1
    corrected = VerificationResult.objects.create(
        submission=submission,
        attempt=submission.attempt,
        student=submission.student,
        task=submission.task,
        catalog=submission.catalog,
        version=next_version,
        revision=1,
        supersedes=original,
        is_current=True,
        program_status=new_program,
        manual_status=new_manual,
        overall_status=overall,
        independence=new_independence,
        assistance_snapshot=new_assistance,
        item_results=changes.get('item_results', original.item_results),
        program_result=original.program_result,
        manual_result=new_manual_result,
        verifier_version=original.verifier_version,
        rubric_version=original.rubric_version,
        verification_error=new_error,
    )

    ManualReviewTask.objects.filter(result=original).update(
        status=constants.MANUAL_TASK_CORRECTED,
    )
    correction = ResultCorrection.objects.create(
        submission=submission,
        original_result=original,
        corrected_result=corrected,
        corrected_by=actor,
        source=source,
        reason=reason.strip(),
        before=before,
        after={
            'version': corrected.version,
            'program_status': corrected.program_status,
            'manual_status': corrected.manual_status,
            'overall_status': corrected.overall_status,
            'independence': corrected.independence,
            'item_results': corrected.item_results,
            'manual_result': corrected.manual_result,
        },
    )
    if sampling_item is not None:
        sampling_item.correction = correction
        sampling_item.status = constants.SAMPLING_ITEM_NEEDS_CORRECTION
        sampling_item.save(update_fields=['correction', 'status', 'updated_at'])

    events.emit_event(
        user=submission.student,
        event_type='correction',
        event_id=f'm6-correction-{correction.correction_id}',
        catalog=submission.catalog,
        task=submission.task,
        attempt_id=submission.attempt.attempt_id,
        submission_id=submission.submission_id,
        result_id=corrected.result_id,
        capability_ids=[
            capability.stable_id for capability in submission.task.capabilities.all()
        ],
        evidence_ref=f'm6:{corrected.result_id}',
        extra={
            'correction_id': str(correction.correction_id),
            'source': source,
            'original_version': original.version,
            'corrected_version': corrected.version,
            'reason_summary': reason.strip()[:200],
        },
    )
    handoff.dispatch_result(corrected, correction=correction)
    return correction
