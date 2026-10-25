"""Learning-effect summaries for module 8.

Every rate carries its numerator, denominator, missing count and version.
No single total score is produced.
"""

from django.utils import timezone

from .. import constants
from ..models import RetestAssignment, SubmissionSnapshot, VerificationResult


def _percent(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def build_stats(*, catalog, start=None, end=None, task=None):
    submissions = SubmissionSnapshot.objects.filter(
        catalog=catalog, first_effective=True,
    ).select_related('task', 'attempt', 'student')
    if start:
        submissions = submissions.filter(created_at__gte=start)
    if end:
        submissions = submissions.filter(created_at__lte=end)
    if task is not None:
        submissions = submissions.filter(task=task)
    submissions = list(submissions.order_by('id'))

    result_map = {
        result.submission_id: result
        for result in VerificationResult.objects.filter(
            submission__in=submissions, is_current=True,
        )
    }

    overall_counts = {}
    independence_counts = {}
    independent_pass = 0
    assisted_pass = 0
    denominator = 0
    missing_independence = 0
    pending_manual = 0
    verification_failed = 0
    environment_affected = 0
    task_versions = set()

    for submission in submissions:
        result = result_map.get(submission.id)
        independence = submission.independence
        independence_counts[independence] = independence_counts.get(independence, 0) + 1
        task_versions.add(f'{submission.task.task_key}@{submission.task_version}')
        if independence == constants.INDEPENDENCE_UNKNOWN:
            missing_independence += 1
        if result is None:
            overall_counts['result_missing'] = overall_counts.get('result_missing', 0) + 1
            continue
        overall_counts[result.overall_status] = overall_counts.get(result.overall_status, 0) + 1
        if result.overall_status == constants.OVERALL_PENDING_MANUAL:
            pending_manual += 1
        if result.overall_status == constants.OVERALL_VERIFICATION_FAILED:
            verification_failed += 1
        if result.overall_status == constants.OVERALL_ENVIRONMENT_AFFECTED:
            environment_affected += 1
        if (
            independence in (constants.INDEPENDENCE_INDEPENDENT, constants.INDEPENDENCE_ASSISTED)
            and result.overall_status in (constants.OVERALL_PASSED, constants.OVERALL_FAILED)
        ):
            denominator += 1
            if result.overall_status == constants.OVERALL_PASSED:
                if independence == constants.INDEPENDENCE_INDEPENDENT:
                    independent_pass += 1
                else:
                    assisted_pass += 1

    assignments = RetestAssignment.objects.filter(
        original_submission__in=submissions,
    ).select_related('selected_task', 'completed_submission')
    retest_status = {}
    retest_outcome = {}
    for assignment in assignments:
        retest_status[assignment.status] = retest_status.get(assignment.status, 0) + 1
        if assignment.outcome:
            retest_outcome[assignment.outcome] = retest_outcome.get(assignment.outcome, 0) + 1

    completed = sum(
        count for status, count in retest_status.items()
        if status == constants.RETEST_COMPLETED
    )
    retention_passed = retest_outcome.get(constants.RETEST_OUTCOME_PASSED, 0)
    retention_denominator = (
        retest_outcome.get(constants.RETEST_OUTCOME_PASSED, 0)
        + retest_outcome.get(constants.RETEST_OUTCOME_FAILED, 0)
    )

    return {
        'catalog_version': catalog.version,
        'task_versions': sorted(task_versions),
        'window': {
            'start': start.isoformat() if start else None,
            'end': (end or timezone.now()).isoformat() if end or start else None,
        },
        'first_effective_attempts': {
            'total': len(submissions),
            'result_missing': overall_counts.get('result_missing', 0),
            'independence': independence_counts,
            'overall': overall_counts,
            'pending_manual': pending_manual,
            'verification_failed': verification_failed,
            'environment_affected': environment_affected,
            'unknown_independence': missing_independence,
        },
        'platform_independent_pass': {
            'numerator': independent_pass,
            'denominator': denominator,
            'rate': _percent(independent_pass, denominator),
            'assisted_pass': assisted_pass,
            'missing_independence': missing_independence,
            'pending_manual_excluded': pending_manual,
            'note': '仅覆盖平台可观测帮助；未知、待评和环境异常分别单列。',
        },
        'retest': {
            'assignments': len(assignments),
            'status': retest_status,
            'outcome': retest_outcome,
            'completed': completed,
            'pending_item': retest_status.get(constants.RETEST_PENDING_ITEM, 0),
            'scheduled': retest_status.get(constants.RETEST_SCHEDULED, 0),
            'due': retest_status.get(constants.RETEST_DUE, 0),
            'missed': retest_status.get(constants.RETEST_MISSED, 0),
            'retention': {
                'numerator': retention_passed,
                'denominator': retention_denominator,
                'rate': _percent(retention_passed, retention_denominator),
                'assisted': retest_outcome.get(constants.RETEST_OUTCOME_ASSISTED, 0),
                'pending_manual': retest_outcome.get(constants.RETEST_OUTCOME_PENDING_MANUAL, 0),
                'verification_failed': retest_outcome.get(
                    constants.RETEST_OUTCOME_VERIFICATION_FAILED, 0
                ),
            },
            'note': '未参加不等于知识错误；受助复测不计入无提示保持分子。',
        },
        'versions': {
            'rule_version': constants.RULE_VERSION,
            'rubric_version': constants.RUBRIC_VERSION,
        },
    }
