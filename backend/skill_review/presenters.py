"""Display payloads for module 6.

Students see labels and feedback, not verifier internals, raw error codes or
evidence references.  Teachers get the full audit payload.
"""

from . import constants
from .models import (
    AssistanceRecord,
    ManualReviewTask,
    RetestAssignment,
    ReviewCard,
    SubmissionErrorCause,
    SubmissionSnapshot,
    VerificationResult,
)


PROGRAM_LABELS = dict(constants.PROGRAM_STATUS_CHOICES)
MANUAL_LABELS = dict(constants.MANUAL_STATUS_CHOICES)
OVERALL_LABELS = dict(constants.OVERALL_STATUS_CHOICES)
INDEPENDENCE_LABELS = dict(constants.INDEPENDENCE_CHOICES)
CAUSE_LABELS = dict(constants.ERROR_CAUSE_CHOICES)
CAUSE_STATUS_LABELS = dict(constants.CAUSE_STATUS_CHOICES)
RETEST_LABELS = dict(constants.RETEST_STATUS_CHOICES)
RETEST_OUTCOME_LABELS = dict(constants.RETEST_OUTCOME_CHOICES)
NOTICE_LABELS = dict(constants.NOTICE_STATUS_CHOICES)

VERIFICATION_ERROR_LABELS = {
    'server_evidence_not_connected': '服务端证据暂未接通，本次未判定通过',
    'unknown_verifier': '验证器未配置，本次未判定通过',
    'verifier_not_configured': '验证器未配置，本次未判定通过',
}


def _version_label(version):
    cleaned = (version or '').replace('-candidate', '').strip('-')
    return cleaned or version


def _item_payload(item, *, teacher):
    payload = {
        'label': item.get('label') or item.get('item_id'),
        'kind_label': '程序核验' if item.get('kind') == 'program' else '人工评阅',
        'status': item.get('status'),
        'status_label': {
            'passed': '通过',
            'failed': '未通过',
            'pending': '待评阅',
            'scored': '已评分',
        }.get(item.get('status'), item.get('status')),
        'score': item.get('score'),
        'max_points': item.get('max_points'),
    }
    if item.get('reason'):
        payload['reason'] = item['reason']
    if teacher:
        payload['item_id'] = item.get('item_id')
        payload['evidence_ref'] = item.get('evidence_ref', '')
    return payload


def _assistance_payload(submission, *, teacher):
    snapshot = submission.assistance_snapshot or {}
    payload = {
        'independence': submission.independence,
        'independence_label': INDEPENDENCE_LABELS.get(submission.independence, submission.independence),
        'level': int(snapshot.get('level') or 0),
        'level_label': constants.HINT_LEVEL_LABELS.get(int(snapshot.get('level') or 0), ''),
        'source_label': dict(constants.ASSISTANCE_SOURCE_CHOICES).get(
            snapshot.get('source') or constants.ASSISTANCE_SOURCE_NONE, '',
        ),
        'shown': bool(snapshot.get('shown')),
        'answer_exposure': bool(submission.answer_exposure),
        'tracking': submission.assistance_tracking,
        'tracking_label': dict(constants.ASSISTANCE_TRACKING_CHOICES).get(
            submission.assistance_tracking, submission.assistance_tracking,
        ),
    }
    if teacher:
        payload['reason'] = snapshot.get('reason')
        payload['help_records'] = snapshot.get('help_records', [])
        payload['requested_not_shown'] = snapshot.get('requested_not_shown', 0)
    return payload


def submission_payload(submission, result=None, *, teacher=False):
    result = result or submission.results.filter(is_current=True).first()
    payload = {
        'submission_id': str(submission.submission_id),
        'task': {
            'title': submission.task.title,
            'version_label': _version_label(submission.task_version),
            'track_label': '数据安全' if submission.task.track == 'data' else '网络安全',
        },
        'submitted_at': submission.created_at.isoformat(),
        'sequence': submission.sequence,
        'first_effective': submission.first_effective,
        'assistance': _assistance_payload(submission, teacher=teacher),
        'save_status': 'saved',
        'save_status_label': '保存成功',
        'execution_label': '未开展',
        'protection_label': '未评估',
    }
    if teacher:
        payload['student'] = {'id': submission.student_id, 'username': submission.student.username}
        payload['attempt_id'] = str(submission.attempt.attempt_id)
        payload['catalog_version'] = submission.catalog.version
        payload['payload_hash'] = submission.payload_hash
        payload['payload'] = submission.payload

    if result is None:
        payload.update({
            'program_status': constants.PROGRAM_NOT_RUN,
            'program_status_label': '待核验',
            'manual_status': constants.MANUAL_NOT_APPLICABLE,
            'manual_status_label': '不适用',
            'overall_status': constants.OVERALL_PENDING,
            'overall_status_label': '处理中',
            'items': [],
            'result_version': None,
        })
        return payload

    payload.update({
        'result_version': result.version,
        'program_status': result.program_status,
        'program_status_label': PROGRAM_LABELS.get(result.program_status, result.program_status),
        'manual_status': result.manual_status,
        'manual_status_label': MANUAL_LABELS.get(result.manual_status, result.manual_status),
        'overall_status': result.overall_status,
        'overall_status_label': OVERALL_LABELS.get(result.overall_status, result.overall_status),
        'items': [_item_payload(item, teacher=teacher) for item in (result.item_results or [])],
        'verification_note': VERIFICATION_ERROR_LABELS.get(result.verification_error, ''),
        'total_score': (result.manual_result or {}).get('total_score'),
        'max_total_score': len(constants.RUBRIC_ITEMS) * constants.RUBRIC_MAX_SCORE,
        'review_remarks': (result.manual_result or {}).get('remarks', ''),
        'corrected': result.version > 1,
    })
    if teacher:
        payload['result_id'] = str(result.result_id)
        payload['program_result'] = result.program_result
        payload['manual_result'] = result.manual_result
        payload['verifier_version'] = result.verifier_version
        payload['rubric_version'] = result.rubric_version
        payload['verification_error'] = result.verification_error
        payload['module1_fact_ids'] = result.module1_fact_ids
    return payload


def causes_payload(submission, *, teacher=False):
    items = []
    for cause in SubmissionErrorCause.objects.filter(submission=submission).order_by('cause'):
        item = {
            'label': CAUSE_LABELS.get(cause.cause, cause.cause),
            'status_label': CAUSE_STATUS_LABELS.get(cause.status, cause.status),
        }
        if teacher:
            item.update({
                'cause': cause.cause,
                'status': cause.status,
                'source': cause.source,
                'note': cause.note,
            })
        items.append(item)
    return items


def review_card_payload(card, *, teacher=False):
    if card is None:
        return None
    payload = {
        'status': card.status,
        'status_label': dict(constants.REVIEW_CARD_STATUS_CHOICES).get(card.status, card.status),
        'original_task_summary': card.original_task_summary,
        'error_evidence': card.error_evidence,
        'judgment_at_time': card.judgment_at_time,
        'correct_basis': card.correct_basis,
        'next_verification': card.next_verification,
        'student_reflection': card.student_reflection,
        'teacher_confirmation': card.teacher_confirmation,
        'assistance_level': card.assistance_level,
        'assistance_level_label': constants.HINT_LEVEL_LABELS.get(card.assistance_level, ''),
        'completed_at': card.completed_at.isoformat() if card.completed_at else None,
    }
    if teacher:
        payload['card_id'] = str(card.card_id)
        payload['confirmed_by'] = card.confirmed_by_id
    return payload


def retest_payload(assignment, *, teacher=False):
    payload = {
        'assignment_id': str(assignment.assignment_id),
        'status': assignment.status,
        'status_label': RETEST_LABELS.get(assignment.status, assignment.status),
        'task': (
            {
                'id': assignment.selected_task.id,
                'title': assignment.selected_task.title,
                'version_label': _version_label(assignment.selected_task.version),
            }
            if assignment.selected_task else None
        ),
        'scheduled_at': assignment.scheduled_at.isoformat() if assignment.scheduled_at else None,
        'due_at': assignment.due_at.isoformat() if assignment.due_at else None,
        'grace_until': assignment.grace_until.isoformat() if assignment.grace_until else None,
        'outcome': assignment.outcome,
        'outcome_label': RETEST_OUTCOME_LABELS.get(assignment.outcome, ''),
        'completed_at': assignment.completed_at.isoformat() if assignment.completed_at else None,
        'original_task_title': assignment.original_submission.task.title,
        'note': assignment.adjustment_note,
    }
    if teacher:
        payload['student'] = {'id': assignment.student_id, 'username': assignment.student.username}
        payload['original_attempt_id'] = str(assignment.original_attempt.attempt_id)
        payload['pool_snapshot'] = assignment.pool_snapshot
        payload['selection_reason'] = assignment.selection_reason
        payload['rule_version'] = assignment.rule_version
        payload['capability_ids'] = assignment.capability_ids
        payload['started_attempt_id'] = (
            str(assignment.started_attempt.attempt_id) if assignment.started_attempt else None
        )
    return payload


def manual_task_payload(task, *, teacher=True):
    submission = task.submission
    payload = {
        'task_id': str(task.review_id),
        'status': task.status,
        'status_label': dict(constants.MANUAL_TASK_STATUS_CHOICES).get(task.status, task.status),
        'student': {'id': task.student_id, 'username': task.student.username},
        'submission': submission_payload(submission, task.result, teacher=True),
        'rubric': task.rubric,
        'rubric_version': task.rubric_version,
        'claimed_by': task.claimed_by_id,
        'reviewed_at': task.reviewed_at.isoformat() if task.reviewed_at else None,
        'scores': task.scores,
        'total_score': task.total_score,
        'decision': task.decision,
        'remarks': task.remarks,
        'causes': causes_payload(submission, teacher=True),
        'created_at': task.created_at.isoformat(),
    }
    return payload


def timeline_payload(submission, *, teacher=False):
    result = submission.results.filter(is_current=True).first()
    records = AssistanceRecord.objects.filter(attempt=submission.attempt).order_by('created_at')
    timeline = []
    for record in records:
        item = {
            'kind': record.kind,
            'kind_label': dict(constants.ASSISTANCE_KIND_CHOICES).get(record.kind, record.kind),
            'level': record.level,
            'level_label': constants.HINT_LEVEL_LABELS.get(record.level, ''),
            'source_label': dict(constants.ASSISTANCE_SOURCE_CHOICES).get(record.source, record.source),
            'shown': record.shown,
            'requested_at': record.requested_at.isoformat() if record.requested_at else None,
            'shown_at': record.shown_at.isoformat() if record.shown_at else None,
        }
        if teacher:
            item['note'] = record.note
        timeline.append(item)
    return {
        'submission_id': str(submission.submission_id),
        'result': submission_payload(submission, result, teacher=teacher),
        'causes': causes_payload(submission, teacher=teacher),
        'review_card': review_card_payload(
            ReviewCard.objects.filter(submission=submission).first(), teacher=teacher,
        ),
        'timeline': timeline,
        'corrections': [
            {
                'correction_id': str(correction.correction_id),
                'source': correction.source,
                'reason': correction.reason,
                'before': correction.before,
                'after': correction.after,
                'created_at': correction.created_at.isoformat(),
            }
            for correction in submission.corrections.order_by('-created_at')
        ] if teacher else None,
    }
