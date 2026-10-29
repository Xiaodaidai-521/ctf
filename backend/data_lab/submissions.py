"""Immutable, owner-bound evidence snapshots, separate from module-six grades."""
from uuid import UUID
from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError
from .catalog import case_spec, digest
from .common import Conflict, assert_same, cas_lab, check_payload, emit, key, own_lab, text
from .models import EvidenceSubmission
from .services import scan_dto


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('证据引用必须是UUID。') from None


def submit(user, attempt_id, data):
    check_payload(data, ('idempotency_key', 'explanation', 'scan_id', 'profile_id', 'replay_ids'),
                  ('idempotency_key', 'explanation', 'scan_id', 'profile_id', 'replay_ids'))
    with transaction.atomic():
        lab = own_lab(user, attempt_id, lock=True)
        operation_key = key(data)
        existing = lab.submissions.filter(idempotency_key=operation_key).first()
        if existing:
            evidence = assert_same(existing, data)
        else:
            if lab.submissions.filter(module6__isnull=True).exists():
                raise Conflict('先重试已有待核验证据，避免首次有效提交顺序变化。')
            explanation = text(data['explanation'], 'explanation', 4000)
            scan = lab.active_scan
            if (scan is None or scan.status != 'completed' or str(scan.scan_id) != identifier(data['scan_id'])
                    or str(scan.current_profile_id) != identifier(data['profile_id'])):
                raise Conflict('请引用本次尝试当前已完成的扫描与复核画像。')
            ids = data['replay_ids']
            if not isinstance(ids, list) or len(ids) != 4:
                raise ValidationError('须提交四轮回放引用。')
            ids = [identifier(value) for value in ids]
            replays = list(lab.replays.filter(replay_id__in=ids, scan=scan, profile_id=scan.current_profile_id).order_by('variant'))
            if len(replays) != 4 or {r.variant for r in replays} != {'A1', 'A2', 'A3', 'A4'} or any(not r.judgment for r in replays):
                raise Conflict('四轮必须属于当前扫描和画像，且均已保存学生判断。')
            if not lab.basis or digest(lab.basis) != lab.basis_digest:
                raise Conflict('依据快照缺失或摘要不一致。')
            scan_data = scan_dto(scan, limit=100)
            if not scan_data['review_history']:
                raise Conflict('请先完成教学复核。')
            spec = case_spec(lab.case.task.task_key)
            snapshot = {'schema': 'data-lab-evidence-v1', 'student_id': user.pk,
                'attempt_id': str(lab.attempt.attempt_id), 'catalog_version': lab.attempt.catalog.version,
                'task_key': lab.attempt.task.task_key, 'task_version': lab.attempt.task_version,
                'versions': {k: spec[k] for k in ('material_version', 'rule_version', 'validator_version', 'rubric_version', 'scenario_version')},
                'material_digest': lab.case.material_digest, 'basis': lab.basis, 'basis_digest': lab.basis_digest,
                'scan': scan_data, 'explanation': explanation,
                'replays': [{'replay_id': str(r.replay_id), 'variant': r.variant, 'judgment': r.judgment,
                             'frozen': r.frozen, 'content_digest': r.content_digest} for r in replays],
                'execution_mode': 'readonly_decision', 'execution_status': 'not_started', 'protection_status': 'not_assessed'}
            cas_lab(lab)
            evidence = EvidenceSubmission.objects.create(lab=lab, idempotency_key=operation_key,
                request_digest=digest(data), snapshot=snapshot, content_digest=digest(snapshot))
            emit(lab, 'evidence_saved', evidence.submission_id, evidence.content_digest, event_type='task_submit')
    return deliver(evidence)


def owned_submission(user, submission_id):
    evidence = EvidenceSubmission.objects.select_related('lab__attempt__student', 'module6').filter(
        submission_id=submission_id, lab__attempt__student=user).first()
    if evidence is None:
        raise NotFound()
    own_lab(user, evidence.lab.attempt.attempt_id)
    return evidence


def deliver(evidence):
    from django.db import DatabaseError
    from skill_review.services.submissions import create_submission, SubmissionError
    from skill_review.services.handoff import dispatch_result
    from .common import short_id
    try:
        with transaction.atomic():
            lab = own_lab(evidence.lab.attempt.student, evidence.lab.attempt.attempt_id, lock=True)
            saved = EvidenceSubmission.objects.select_for_update().get(pk=evidence.pk)
            if digest(saved.snapshot) != saved.content_digest:
                raise SubmissionError('EVIDENCE_DIGEST_MISMATCH')
            if saved.module6_id is None:
                submission, _ = create_submission(student=lab.attempt.student, attempt=lab.attempt,
                    client_submission_id=short_id('submission', lab.attempt.attempt_id, saved.submission_id),
                    payload={'evidence_id': str(saved.submission_id), 'content_digest': saved.content_digest},
                    assistance_tracking=lab.tracking, now=saved.created_at, data_lab_evidence=saved)
                saved.module6 = submission
                saved.save(update_fields=['module6'])
            result = saved.module6.results.get(is_current=True)
            sent, notices = dispatch_result(result)
            saved.status = 'delivered' if sent else 'pending_handoff'
            if not saved.module6.first_effective:
                saved.status = 'received_no_recount'
            saved.failure_code = '' if saved.status != 'pending_handoff' else 'MODULE1_PENDING'
            saved.save(update_fields=['status', 'failure_code'])
            emit(lab, 'module6_received', saved.submission_id, saved.content_digest, event_type='verification_result')
            return saved
    except (DatabaseError, SubmissionError, TimeoutError, ConnectionError, RuntimeError) as exc:
        # Evidence was committed before transport. A failed attempt never fabricates a grade.
        with transaction.atomic():
            saved = EvidenceSubmission.objects.get(pk=evidence.pk)
            saved.status = 'verification_failed' if isinstance(exc, SubmissionError) else 'pending'
            saved.failure_code = 'EVIDENCE_INVALID' if isinstance(exc, SubmissionError) else 'DELIVERY_RETRY_REQUIRED'
            saved.save(update_fields=['status', 'failure_code'])
        return saved


def submission_dto(evidence):
    result = evidence.module6.results.filter(is_current=True).first() if evidence.module6_id else None
    return {'submission_id': str(evidence.submission_id), 'save_status': 'saved',
        'content_digest': evidence.content_digest, 'handoff_status': evidence.status,
        'program_status': result.program_status if result else 'pending',
        'manual_status': result.manual_status if result else 'pending',
        'independence': result.independence if result else 'unknown',
        'overall_status': result.overall_status if result else 'pending',
        'module6_id': str(evidence.module6.submission_id) if evidence.module6_id else None,
        'execution_status': 'not_started', 'protection_status': 'not_assessed',
        'message': '证据已保存；核验/交接待重试。' if evidence.status != 'delivered' else '模块六已核验，模块一已确认接收；人工评阅另列。'}
