from django.db import transaction
from rest_framework.exceptions import ValidationError

from learning_map.models import TaskAttempt
from skill_review.models import RetestAssignment
from skill_review.services.retest import claim_retest
from skill_review.services.submissions import payload_hash

from . import verifiers
from .evidence import existing_evidence, persist_evidence, request_digest, source_binding, valid_key
from .models import LabAssignment, RepairClaim
from .services import REPAIR_VERIFIER, active_assignment, audit, task_snapshot


def validate_payload(explanation, policy):
    if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 2000:
        raise ValidationError('须填写原理解释（1–2000 字符）；解释不自动评分。')
    if (not isinstance(policy, dict) or set(policy) != {'default', 'rules'}
            or policy['default'] not in ('allow', 'deny') or not isinstance(policy['rules'], dict)
            or set(policy['rules']) != {'public', 'internal', 'private'}
            or any(value not in ('public', 'tenant', 'owner', 'deny') for value in policy['rules'].values())):
        raise ValidationError('修复方案仅接受声明式资料访问策略，不能提交代码、URL 或执行命令。')


def repair_ready(assignment):
    active_assignment(assignment)
    if payload_hash(task_snapshot(assignment.mapping.repair_task)) != assignment.scope['repair_task_hash']:
        raise ValidationError('修复任务版本或场景已变化。')
    original = assignment.evidence.filter(
        attempt=assignment.attempt, status='passed', result__overall_status='passed', result__is_current=True,
    ).first()
    if not original:
        raise ValidationError('原问题尚无服务端通过证据。')
    retest = RetestAssignment.objects.filter(original_submission=original.result.submission).first()
    if not retest or retest.selected_task_id != assignment.mapping.repair_task_id:
        raise ValidationError('无可用新场景修复任务，须教师补题。')
    return retest


@transaction.atomic
def submit_claim(*, assignment, key, explanation, policy):
    valid_key(key)
    validate_payload(explanation, policy)
    assignment = LabAssignment.objects.select_for_update().get(pk=assignment.pk)
    payload = {'explanation': explanation, 'policy': policy}
    digest = payload_hash(payload)
    existing = RepairClaim.objects.filter(key=key).first()
    if existing:
        if existing.assignment_id != assignment.pk or existing.payload_hash != digest:
            raise ValidationError('同键异内容修复主张被拒绝。')
        return existing, False
    retest = repair_ready(assignment)
    if RepairClaim.objects.filter(retest=retest).exists():
        raise ValidationError('该复测已有冻结主张，请核验原主张；重新练习需新场景。')
    if retest.started_attempt_id and retest.started_attempt.submissions.exists():
        raise ValidationError('复测已通过其他入口提交，请安排新场景。')
    try:
        attempt, _ = claim_retest(retest, assignment.attempt.student)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    claim = RepairClaim.objects.create(assignment=assignment, retest=retest, attempt=attempt,
                                       key=key, payload=payload, payload_hash=digest)
    audit(attempt.student, 'repair_claimed', assignment, claim_id=str(claim.claim_id),
          payload_hash=digest, verified=False)
    return claim, True


@transaction.atomic
def verify_claim(*, assignment, claim_id, key):
    valid_key(key)
    assignment = LabAssignment.objects.select_for_update().get(pk=assignment.pk)
    claim = RepairClaim.objects.filter(claim_id=claim_id, assignment=assignment).first()
    if not claim:
        from rest_framework.exceptions import NotFound
        raise NotFound()
    digest = request_digest(assignment, claim.attempt, 'repair', {'claim_hash': claim.payload_hash})
    existing = existing_evidence(key, digest)
    if existing:
        return existing, False
    repair_ready(assignment)
    attempt = TaskAttempt.objects.select_for_update().get(pk=claim.attempt_id)
    if claim.evidence_id or attempt.status == 'verified' or attempt.submissions.exists():
        raise ValidationError('主张已复核，不能覆盖；请安排新场景。')
    if (attempt.task_id != assignment.mapping.repair_task_id or attempt.task_version != attempt.task.version
            or attempt.student_id != assignment.attempt.student_id
            or attempt.catalog_id != assignment.attempt.catalog_id):
        raise ValidationError('修复尝试绑定不一致。')
    error = ''
    try:
        observation = verifiers.verify_policy(claim.payload['policy'])
        status = 'passed' if observation['passed'] else 'failed'
    except (ValueError, KeyError, TypeError):
        observation, status, error = {}, 'error', 'repair_verifier_error'
    source = source_binding(assignment, attempt, 'synthetic_policy_reexecution')
    source.update({'claim_id': str(claim.claim_id), 'claim_hash': claim.payload_hash,
                   'original_attempt_id': str(assignment.attempt.attempt_id),
                   'scope': 'proposal_only_not_live_juice_patch'})
    row = persist_evidence(assignment=assignment, attempt=attempt, key=key, request_hash=digest,
                           source=source, observation=observation, version=REPAIR_VERIFIER, status=status, error=error)
    claim.evidence = row
    claim.save(update_fields=['evidence'])
    return row, True
