"""Deterministic checks over server-saved evidence, never client assertions."""
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from skill_review.services.submissions import SubmissionError
from .catalog import case_spec, digest
from .models import EvidenceSubmission
from .teacher_material import TARGETS


def validate_context(evidence, student, attempt, payload):
    if not isinstance(evidence, EvidenceSubmission) or not transaction.get_connection().in_atomic_block:
        raise SubmissionError('模块四只接受服务端保存的证据上下文。')
    saved = EvidenceSubmission.objects.select_for_update().filter(pk=evidence.pk).first()
    if (saved is None or saved.lab.attempt_id != attempt.pk or attempt.student_id != student.pk
            or payload != {'evidence_id': str(saved.submission_id), 'content_digest': saved.content_digest}
            or digest(saved.snapshot) != saved.content_digest
            or saved.snapshot.get('student_id') != student.pk
            or saved.snapshot.get('attempt_id') != str(attempt.attempt_id)):
        raise SubmissionError('证据上下文归属或摘要不一致。')
    return saved


def target_locations(snapshot):
    cells = {(c['row'], c['column']): c['source_text'] for c in snapshot['scan']['cells']}
    expected = set()
    for row, column, value, category in TARGETS[snapshot['task_key']]:
        start = cells[row, column].index(value)
        expected.add((row, column, start, start + len(value), category))
    return expected


def finding_locations(findings):
    return {(loc['row'], loc['column'], loc['span']['start'], loc['span']['end'], f['category_id'])
            for f in findings for loc in f['locations']}


def metrics(expected, actual):
    tp, fp, fn = len(expected & actual), len(actual - expected), len(expected - actual)
    return {'targets': len(expected), 'candidates': len(actual), 'true_positive': tp,
            'false_positive': fp, 'false_negative': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'matching': 'exact_logical_row_column_codepoint_span_and_category',
            'scope': 'six_synthetic_rows_not_real_world_performance'}


def verify_submission(submission, evidence):
    version = case_spec(submission.task.task_key)['validator_version']
    result = {'status': 'error', 'error': 'evidence_missing_or_invalid', 'version': version,
              'manual_required': True, 'public_items': [], 'internal': {'type': 'data_lab'}, 'suggested_causes': [],
              'rubric_version': case_spec(submission.task.task_key)['rubric_version']}
    try:
        saved = validate_context(evidence, submission.student, submission.attempt, submission.payload)
        snapshot = saved.snapshot
        if submission.task.validator.get('version') != version:
            return result
        expected = target_locations(snapshot)
        findings = snapshot['scan']['findings']['items']
        actual = finding_locations(findings)
        scan = saved.lab.scans.get(scan_id=snapshot['scan']['scan_id'])
        original = finding_locations(scan.original['findings'])
        checks = {
            'reviewed_locations': expected == actual and all(f['judgment'] == 'determined' for f in findings),
            'replay_judgments': all(r['judgment']['actions'] == [s['result']['recommended_action'] for s in r['frozen']['steps']]
                                    for r in snapshot['replays']),
            'readonly_evidence': snapshot['execution_mode'] == 'readonly_decision'
                                 and snapshot['execution_status'] == 'not_started'
                                 and snapshot['protection_status'] == 'not_assessed',
        }
        result.update(status='passed' if all(checks.values()) else 'failed', error='',
            public_items=[{'item_id': name, 'kind': 'program', 'label': name,
                'status': 'passed' if passed else 'failed', 'score': int(passed), 'max_points': 1,
                'evidence_ref': f'data-lab:{saved.submission_id}'} for name, passed in checks.items()],
            internal={'type': 'data_lab', 'checks': checks, 'content_digest': saved.content_digest,
                'original_detection': metrics(expected, original), 'reviewed_detection': metrics(expected, actual),
                'coverage': snapshot['scan']['coverage'], 'execution': 'not_started', 'protection': 'not_assessed'})
    except (SubmissionError, ObjectDoesNotExist, KeyError, TypeError, ValueError, AttributeError):
        pass
    return result
