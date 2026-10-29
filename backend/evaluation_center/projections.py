"""Read-only, versioned projections of module 1/6 evidence.

Result rows, not browser events or path estimates, determine conclusions.
Selection of the first effective attempt happens before time-window filtering.
No recommendation, dispatch or due-retest write service is called here.
"""

from collections import Counter, defaultdict

from django.db.models import Prefetch, Q
from django.utils import timezone

from learning_analytics.models import LearningEvent
from learning_map.models import TaskAttempt, VerificationFact
from skill_review.models import (
    AssistanceRecord, ResultCorrection, RetestAssignment, SubmissionSnapshot,
    VerificationResult,
)

from .metrics import SOURCE_STATUS, metric


FINAL_STATUSES = {'passed', 'failed'}


def _iso(value):
    return value.isoformat() if value else None


def _versions(attempt):
    return {
        'task_key': attempt.task.task_key,
        'task_version': attempt.task_version,
        'catalog_version': attempt.catalog.version,
        'event_dictionary': 'v1',
    }


def _key(attempt):
    return (attempt.student_id, attempt.task.task_key,
            attempt.task_version, attempt.catalog.version)


def _result_payload(result, submission):
    snapshot = result.assistance_snapshot or {}
    independence = result.independence
    # A correction can establish observed help despite incomplete old tracking;
    # absence of help still requires a complete, frozen observation snapshot.
    if not snapshot or independence not in {'independent', 'assisted', 'unknown'}:
        independence = 'unknown'
    if independence == 'assisted' and (
        snapshot.get('shown') is not True or snapshot.get('source') not in {'ai', 'card', 'teacher'}
    ):
        independence = 'unknown'
    if independence == 'independent' and (
        submission.assistance_tracking != 'complete'
        or snapshot.get('shown') is not False or snapshot.get('answer_exposure') is not False
        or snapshot.get('reason') != 'no_help_shown'
        or snapshot.get('help_records') != []
    ):
        independence = 'unknown'
    binding_valid = (
        result.student_id == submission.student_id
        and result.attempt_id == submission.attempt_id
        and result.task_id == submission.task_id
        and result.catalog_id == submission.catalog_id
    )
    if not binding_valid:
        independence = 'unknown'
    return {
        'result_id': str(result.result_id),
        'version': result.version,
        'revision': result.revision,
        'is_current': result.is_current,
        'supersedes': str(result.supersedes.result_id) if result.supersedes_id else None,
        'program_status': result.program_status,
        'manual_status': result.manual_status,
        'overall_status': result.overall_status if binding_valid else 'unknown',
        'independence': independence,
        'recorded_independence': result.independence,
        'binding_valid': binding_valid,
        'verifier_version': result.verifier_version,
        'rubric_version': result.rubric_version,
        'verification_error': result.verification_error,
        'help': {key: snapshot.get(key) for key in (
            'reason', 'level', 'source', 'shown', 'requested_not_shown', 'answer_exposure',
        )},
        'fact_ids': list((result.module1_fact_ids or {}).values()),
        'evidence_ref': f'm6:{result.result_id}',
        'created_at': _iso(result.created_at),
    }


def _submission_payload(submission):
    results = sorted(submission.results.all(), key=lambda row: (row.version, row.revision))
    current = next((row for row in results if row.is_current), None)
    return {
        'submission_id': str(submission.submission_id),
        'sequence': submission.sequence,
        'first_effective': submission.first_effective,
        'created_at': _iso(submission.created_at),
        'assistance_tracking': submission.assistance_tracking,
        'original_independence': submission.independence,
        'answer_exposure': submission.answer_exposure,
        'current_result': _result_payload(current, submission) if current else None,
        'result_history': [_result_payload(row, submission) for row in results],
    }


def _summary(attempt):
    submissions = sorted(attempt.submissions.all(), key=lambda row: (row.created_at, row.pk))
    first = next((row for row in submissions if row.first_effective), None)
    result = None
    if first:
        current = next((row for row in first.results.all() if row.is_current), None)
        result = _result_payload(current, first) if current else None
    capabilities = sorted(attempt.capability_ids or [])
    mapped = bool(capabilities) and set(capabilities).issubset({
        capability.stable_id for capability in attempt.task.capabilities.all()
        if capability.catalog_id == attempt.catalog_id
    }) and attempt.task.catalog_id == attempt.catalog_id
    return {
        'attempt_id': str(attempt.attempt_id),
        'student_id': attempt.student_id,
        'task_id': attempt.task_id,
        'task_title': attempt.task.title,
        'versions': _versions(attempt),
        'capability_ids': capabilities,
        'knowledge_point_ids': sorted({
            point.stable_id for capability in attempt.task.capabilities.all()
            if capability.stable_id in capabilities and capability.catalog_id == attempt.catalog_id
            for point in capability.knowledge_points.all()
            if point.catalog_id == attempt.catalog_id
        }),
        'mapping_status': 'mapped' if mapped else 'unmapped',
        'attempt_status': attempt.status,
        'claimed_at': _iso(attempt.claimed_at),
        'effective_at': _iso(first.created_at if first else attempt.claimed_at),
        'first_submission_id': str(first.submission_id) if first else None,
        'submission_count': len(submissions),
        'current_result': result,
        'overall_status': result['overall_status'] if result else ('unknown' if first else 'not_submitted'),
        'independence': result['independence'] if result else 'unknown',
        'source': 'formal',
    }


def _attempts():
    return TaskAttempt.objects.select_related('task', 'catalog').prefetch_related(
        'task__capabilities__knowledge_points',
        Prefetch('submissions', queryset=SubmissionSnapshot.objects.order_by('created_at', 'pk').prefetch_related(
            Prefetch('results', queryset=VerificationResult.objects.select_related('supersedes')),
        )),
    )


def retest_payload(assignment):
    """Read current evidence even when the assignment's cached outcome is stale."""
    submission = assignment.completed_submission
    current = submission.results.filter(is_current=True).select_related('supersedes').first() if submission else None
    result = _result_payload(current, submission) if current else None
    original = assignment.original_attempt
    started = assignment.started_attempt
    bound = bool(
        submission and started and assignment.selected_task_id
        and submission.attempt_id == started.pk
        and submission.student_id == assignment.student_id == original.student_id
        and submission.task_id == assignment.selected_task_id == started.task_id
        and submission.catalog_id == assignment.catalog_id == original.catalog_id
        and assignment.original_submission.attempt_id == original.pk
        and assignment.original_submission.student_id == assignment.student_id
        and started.task.task_key != original.task.task_key
        and submission.task_version == started.task_version
        and set(started.capability_ids or []) & set(original.capability_ids or [])
    )
    if not bound:
        outcome = 'unknown' if submission else 'not_tested'
    elif result is None:
        outcome = 'unknown'
    elif result['overall_status'] not in FINAL_STATUSES:
        outcome = result['overall_status']
    elif result['independence'] == 'unknown':
        outcome = 'unknown'
    elif result['independence'] == 'assisted':
        outcome = 'assisted'
    else:
        outcome = result['overall_status']
    return {
        'assignment_id': str(assignment.assignment_id),
        'original_attempt_id': str(original.attempt_id),
        'original_submission_id': str(assignment.original_submission.submission_id),
        'started_attempt_id': str(started.attempt_id) if started else None,
        'completed_submission_id': str(submission.submission_id) if submission else None,
        'selected_task_key': assignment.selected_task.task_key if assignment.selected_task_id else None,
        'selected_task_version': assignment.selected_task.version if assignment.selected_task_id else None,
        'due_at': _iso(assignment.due_at),
        'status': assignment.status,
        'recorded_outcome': assignment.outcome,
        'outcome': outcome,
        'binding_valid': bound,
        'current_result': result,
        'rule_version': assignment.rule_version,
    }


def _retests():
    return RetestAssignment.objects.select_related(
        'original_attempt__task', 'original_attempt__catalog', 'original_submission', 'selected_task',
        'started_attempt__task', 'completed_submission',
    )


def attempt_detail(attempt):
    """Teaching-safe detail. The caller must authorize the student/attempt."""
    attempt = _attempts().get(pk=attempt.pk)
    detail = _summary(attempt)
    submissions = [_submission_payload(row) for row in attempt.submissions.all()]
    facts = list(VerificationFact.objects.filter(
        student_id=attempt.student_id, attempt_id=attempt.attempt_id,
    ).select_related('catalog', 'capability').order_by('occurred_at', 'pk'))
    events = list(LearningEvent.objects.filter(
        user_id=attempt.student_id, metadata__attempt_id=str(attempt.attempt_id),
    ).order_by('server_time', 'pk'))
    event_submissions = {
        event.metadata.get('submission_id') for event in events
        if event.event_type == 'task_submit' and event.metadata.get('source') == 'skill_review'
    }
    event_results = {
        event.metadata.get('result_id') for event in events
        if event.event_type in {'verification_result', 'correction'} and event.metadata.get('source') == 'skill_review'
    }
    fact_ids = {fact.fact_id for fact in facts}
    expected_facts = {fact_id for submission in submissions for result in submission['result_history']
                      for fact_id in result['fact_ids']}
    result_ids = {result['result_id'] for submission in submissions for result in submission['result_history']}
    submission_ids = {submission['submission_id'] for submission in submissions}
    detail.update({
        'submissions': submissions,
        'facts': [{
            'fact_id': fact.fact_id, 'source': fact.source,
            'catalog_version': fact.catalog.version, 'task_version': fact.task_version,
            'capability_id': fact.capability.stable_id, 'dimension': fact.dimension,
            'outcome': fact.outcome, 'independence': fact.independence,
            'verifier_version': fact.verifier_version,
            'occurred_at': _iso(fact.occurred_at), 'received_at': _iso(fact.received_at),
            'retest_of_attempt_id': str(fact.retest_of_attempt_id) if fact.retest_of_attempt_id else None,
            'binding_valid': fact.task_id == attempt.task_id and fact.task_version == attempt.task_version
                             and fact.catalog_id == attempt.catalog_id,
        } for fact in facts],
        'assistance': [{
            'record_id': str(row.record_id), 'kind': row.kind, 'level': row.level,
            'source': row.source, 'shown': row.shown,
            'requested_at': _iso(row.requested_at), 'shown_at': _iso(row.shown_at),
        } for row in AssistanceRecord.objects.filter(attempt=attempt).order_by('created_at', 'pk')],
        'events': [{
            'event_id': row.event_id, 'event_type': row.event_type,
            'event_time': _iso(row.event_time), 'server_time': _iso(row.server_time),
            'source': row.metadata.get('source'),
            'task_version': row.metadata.get('task_version'),
            'catalog_version': row.metadata.get('catalog_version'),
            'submission_id': row.metadata.get('submission_id'),
            'result_id': row.metadata.get('result_id'),
        } for row in events],
        'reconciliation': {
            'missing_submission_events': sorted(submission_ids - event_submissions),
            'missing_result_events': sorted(result_ids - event_results),
            'missing_fact_ids': sorted(expected_facts - fact_ids),
            'unbacked_submission_events': sorted(event_submissions - submission_ids - {None, ''}),
            'unbacked_result_events': sorted(event_results - result_ids - {None, ''}),
            'event_counts_are_not_grades': True,
        },
        'corrections': [{
            'correction_id': str(row.correction_id),
            'submission_id': str(row.submission.submission_id),
            'original_result_id': str(row.original_result.result_id),
            'corrected_result_id': str(row.corrected_result.result_id),
            'original_version': row.original_result.version,
            'corrected_version': row.corrected_result.version,
            'source': row.source, 'created_at': _iso(row.created_at),
        } for row in ResultCorrection.objects.filter(submission__attempt=attempt).select_related(
            'submission', 'original_result', 'corrected_result',
        ).order_by('created_at', 'pk')],
        'retests': [retest_payload(row) for row in _retests().filter(
            Q(original_attempt=attempt) | Q(started_attempt=attempt),
        )],
        'source_status': dict(SOURCE_STATUS),
    })
    return detail


def _group_metrics(rows, *, window, versions, retests):
    first = [row for row in rows if row['first_effective_attempt']]
    mapped = [row for row in first if row['mapping_status'] == 'mapped']
    graded = [row for row in mapped if row['overall_status'] in FINAL_STATUSES]
    determinate = [row for row in graded if row['independence'] in {'independent', 'assisted'}]
    counts = Counter(row['overall_status'] for row in first)
    measured = [row for row in retests if row['outcome'] in {'passed', 'failed'}]

    def count(numerator, denominator=len(first), missing=0, status=None):
        return metric(numerator, denominator, missing, window=window, versions=versions, status=status)

    return {
        'first_effective_attempts': count(len(first)),
        'independent_completion': count(sum(row['overall_status'] == 'passed' and row['independence'] == 'independent'
                                          for row in determinate), len(determinate), len(first) - len(determinate)),
        'determinate_coverage': count(len(determinate), len(first), len(first) - len(determinate)),
        'core_pass': count(sum(row['overall_status'] == 'passed' for row in graded), len(graded), len(first) - len(graded)),
        'pending_manual': count(counts['pending_manual']),
        'environment_affected': count(counts['environment_affected']),
        'verification_failed': count(counts['verification_failed']),
        'unknown': count(sum(row['independence'] == 'unknown' or row['overall_status'] == 'unknown' for row in first)),
        'unmapped': count(len(first) - len(mapped)),
        'independent_retest_pass': count(sum(row['outcome'] == 'passed' for row in measured), len(measured), len(retests) - len(measured)),
        'retests_due': count(len(retests), len(retests)),
        'retests_not_tested': count(sum(row['outcome'] == 'not_tested' for row in retests), len(retests)),
        'retests_assisted': count(sum(row['outcome'] == 'assisted' for row in retests), len(retests)),
        'retests_pending_manual': count(sum(row['outcome'] == 'pending_manual' for row in retests), len(retests)),
        'retests_verification_failed': count(sum(row['outcome'] == 'verification_failed' for row in retests), len(retests)),
    }


def query_learning(*, student_id=None, task_key=None, knowledge_point_id=None,
                   catalog_version=None, start=None, end=None, excluded_student_ids=()):
    """Return exact-version groups. Never stitch a cross-version improvement score."""
    attempts = _attempts().filter(student__role='student').exclude(student_id__in=excluded_student_ids)
    if student_id is not None:
        attempts = attempts.filter(student_id=student_id)
    if task_key:
        attempts = attempts.filter(task__task_key=task_key)
    if catalog_version:
        attempts = attempts.filter(catalog__version=catalog_version)
    if knowledge_point_id:
        # Stable IDs are versioned by the enclosing catalog, not global names.
        attempts = attempts.filter(task__capabilities__knowledge_points__stable_id=knowledge_point_id).distinct()
    loaded = list(attempts.order_by('claimed_at', 'pk'))
    first_by_key = {}
    for attempt in loaded:
        for submission in attempt.submissions.all():
            if submission.first_effective:
                key = _key(attempt)
                order = (submission.created_at, submission.pk)
                if key not in first_by_key or order < first_by_key[key][0]:
                    first_by_key[key] = (order, attempt.pk)
    rows, groups = [], defaultdict(list)
    for attempt in loaded:
        row = _summary(attempt)
        if knowledge_point_id and knowledge_point_id not in row['knowledge_point_ids']:
            continue
        effective = next((submission.created_at for submission in attempt.submissions.all() if submission.first_effective), attempt.claimed_at)
        if (start and effective < start) or (end and effective >= end):
            continue
        row['first_effective_attempt'] = first_by_key.get(_key(attempt), (None, None))[1] == attempt.pk
        rows.append(row)
        groups[tuple(row['versions'].values())].append(row)
    window = {'start': _iso(start), 'end': _iso(end)}
    assignments = _retests().filter(original_attempt_id__in=[attempt.pk for attempt in loaded])
    retests_by_group = defaultdict(list)
    as_of = end or timezone.now()
    for assignment in assignments:
        if assignment.due_at:
            if assignment.due_at >= as_of or (start and assignment.due_at < start):
                continue
        elif assignment.status != 'pending_item' or (start and assignment.created_at < start) or assignment.created_at >= as_of:
            continue
        original = assignment.original_attempt
        versions = (original.task.task_key, original.task_version, original.catalog.version, 'v1')
        retests_by_group[versions].append(retest_payload(assignment))
    version_groups = []
    for key in sorted(set(groups) | set(retests_by_group)):
        version_rows = groups[key]
        versions = dict(zip(('task_key', 'task_version', 'catalog_version', 'event_dictionary'), key))
        version_groups.append({
            'versions': versions,
            'metrics': _group_metrics(version_rows, window=window, versions=versions, retests=retests_by_group[key]),
            'attempt_ids': [row['attempt_id'] for row in version_rows],
            'retests': retests_by_group[key],
        })
    return {
        'rows': rows, 'version_groups': version_groups,
        'source_status': dict(SOURCE_STATUS), 'window': window,
        'status': 'available' if rows or version_groups else 'no_data',
        'source': 'formal', 'updated_at': timezone.now().isoformat(),
        'independence_scope': 'platform_observable_help_only',
    }
