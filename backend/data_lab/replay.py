"""Read-only simulation. This module never imports export_risk.decisions."""
from dataclasses import fields, is_dataclass
from enum import Enum
from collections.abc import Mapping
from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError
from export_risk.contracts import (AuthorizationResult, AuthorizationSnapshot, ExportRequestSnapshot,
    FeatureSnapshot, QualityState, SensitivityProfileRef, SourceMode)
from export_risk.judgment.core import assess_risk
from export_risk.policies.catalog import resolve_policy, policy_hash
from .catalog import TASK_A, case_spec, digest
from .common import Conflict, assert_same, cas_lab, check_payload, emit, key, own_lab, text
from .models import Replay
from .services import validate_refs

EVALUATION_TIME = '2026-10-25T12:00:00+00:00'
POLICY_VERSION = 'B-v1'
REASONS = {
    'hard.recipient_forbidden': '接收者不在允许列表，低风险分不能抵消明确越权。',
    'degrade.authorization_unknown': '授权事实未知，须补查，不能默认允许；不同于已证明越权。',
    'fusion.base_protection_applied': '所有分支都有基础保护义务；mask只是建议，并未遮盖。',
    'fusion.cumulative_threshold_exceeded': '冻结窗口请求次数严格大于50才触发；不是交付记录数。',
    'baseline.within_authorized': '请求在此合成授权范围内；不构成可执行授权。',
}


def plain(value):
    if is_dataclass(value):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    return value


def validate_inputs(request, profile, authorization, features, scan, variant):
    if (request.environment != 'test' or authorization.environment != 'test'
            or any(s.source_mode != SourceMode.SYNTHETIC for s in (request, profile, authorization))
            or request.asset_version != str(scan.asset_version_id) or profile.asset_version != request.asset_version
            or request.subject_id != authorization.subject_id or request.scope != authorization.allowed_scope
            or authorization.policy_version != POLICY_VERSION or features.as_of_time != EVALUATION_TIME
            or not features.current_request_counted or request.record_count != 10
            or scan.asset_digest != case_spec(scan.lab.case.task.task_key)['sha256']
            or variant not in ('A1', 'A2', 'A3', 'A4')):
        raise ValueError('UNTRUSTED_REPLAY_INPUT')


def frozen_replay(scan, variant):
    spec = case_spec(scan.lab.case.task.task_key)
    recipient = 'DEMO-ANALYST-A' if spec['task_key'] == TASK_A else 'DEMO-OPS-B'
    forbidden = 'DEMO-OUTSIDER' if spec['task_key'] == TASK_A else 'DEMO-ANALYST-A'
    steps = []
    for count in ([50, 51] if variant == 'A4' else [1]):
        request = ExportRequestSnapshot(request_id=f'{spec["scenario_version"]}:{variant}:{count}', revision='1',
            subject_id='DEMO-REVIEWER', asset_version=str(scan.asset_version_id), scope=('statistics',),
            operation='export', recipient_id=forbidden if variant == 'A2' else recipient,
            purpose=spec['facts']['F-PURPOSE'], record_count=10, environment='test', source_mode=SourceMode.SYNTHETIC,
            request_fingerprint=digest([spec['scenario_version'], variant, count, scan.asset_digest]))
        authorization = AuthorizationSnapshot(authority_source='teacher_frozen_synthetic',
            snapshot_id=spec['scenario_version'] + ':' + variant, subject_id='DEMO-REVIEWER', data_domain='data-lab',
            result=AuthorizationResult.UNKNOWN if variant == 'A3' else AuthorizationResult.AUTHORIZED,
            allowed_scope=('statistics',), allowed_operations=('export',), allowed_recipients=(recipient,),
            policy_version=POLICY_VERSION, observed_at='2026-10-25T00:00:00+00:00',
            valid_until='2026-10-26T00:00:00+00:00', environment='test', source_mode=SourceMode.SYNTHETIC)
        profile = SensitivityProfileRef(profile_id=spec['scenario_version'] + ':teacher-profile',
            asset_version=str(scan.asset_version_id), protection_level='medium', categories=('DEMO_CONTACT',),
            coverage=QualityState.OK, status='complete', detector_version=spec['rule_version'],
            level_policy_version='demo-policy-v1-draft', source_mode=SourceMode.SYNTHETIC)
        features = FeatureSnapshot(feature_set_version='data-lab-frozen-window-v1', as_of_time=EVALUATION_TIME,
            values={'req_count_long': count, 'distinct_objects_long': 1},
            units={'req_count_long': 'requests', 'distinct_objects_long': 'objects'},
            current_request_counted=True, quality=QualityState.OK, data_watermark=EVALUATION_TIME)
        validate_inputs(request, profile, authorization, features, scan, variant)
        result = assess_risk(request, profile, authorization, features, 'not_used', POLICY_VERSION, EVALUATION_TIME)
        inputs = plain(dict(request=request, profile=profile, authorization=authorization, features=features))
        steps.append(dict(inputs=inputs, input_digest=digest(inputs), result=plain(result)))
    return dict(simulated=True, environment='test', source_mode='synthetic', scenario_version=spec['scenario_version'],
        evaluation_time=EVALUATION_TIME, policy_version=POLICY_VERSION, policy_digest=policy_hash(resolve_policy(POLICY_VERSION)),
        policy_status='draft', asset_digest=scan.asset_digest, material_version=spec['material_version'],
        student_profile_ref=str(scan.current_profile_id), profile_basis='teacher_frozen_reference_not_student_detection_coverage',
        execution_status='not_started', protection_status='not_assessed', steps=steps)


@transaction.atomic
def start_replay(user, attempt_id, data):
    check_payload(data, ('scenario_variant', 'idempotency_key'), ('scenario_variant', 'idempotency_key'))
    lab = own_lab(user, attempt_id, lock=True)
    existing = lab.replays.filter(idempotency_key=key(data)).first()
    if existing:
        return assert_same(existing, data)
    variant = data['scenario_variant']
    if variant not in ('A1', 'A2', 'A3', 'A4'):
        raise ValidationError('只能选择四轮预置变体。')
    scan = lab.active_scan
    if not scan or scan.status != 'completed':
        raise Conflict('先完成识别与复核。')
    from .repository import review_service
    service, _ = review_service(scan)
    if not service.repository.read(lambda s: bool(s.reviews)):
        raise Conflict('先保存至少一次人工复核。')
    if lab.replays.count() >= 40:
        raise Conflict('回放次数达到上限。')
    cas_lab(lab)
    frozen = frozen_replay(scan, variant)
    replay = Replay.objects.create(lab=lab, scan=scan, idempotency_key=key(data), request_digest=digest(data),
        variant=variant, profile_id=scan.current_profile_id, frozen=frozen, content_digest=digest(frozen))
    emit(lab, 'replay', replay.replay_id, replay.content_digest)
    return replay


def owned_replay(user, replay_id):
    try:
        replay = Replay.objects.select_related('lab__attempt', 'lab__case__task__catalog').get(
            replay_id=replay_id, lab__attempt__student=user)
    except (Replay.DoesNotExist, ValueError):
        raise NotFound() from None
    own_lab(user, replay.lab.attempt.attempt_id)
    return replay


@transaction.atomic
def save_judgment(user, replay_id, data):
    check_payload(data, ('actions', 'reason', 'fact_ids', 'basis_ids', 'idempotency_key'),
                  ('actions', 'reason', 'fact_ids', 'basis_ids', 'idempotency_key'))
    replay = owned_replay(user, replay_id)
    replay = Replay.objects.select_for_update().get(pk=replay.pk)
    key(data)
    text(data['reason'], 'reason')
    validate_refs(replay.lab, data)
    if (not isinstance(data['actions'], list) or len(data['actions']) != (2 if replay.variant == 'A4' else 1)
            or any(a not in ('allow', 'mask', 'deny', 'defer', 'require_approval') for a in data['actions'])):
        raise ValidationError('请为每个边界步骤填写建议。')
    if replay.judgment:
        if replay.judgment != data:
            raise Conflict('程序结果已揭示，不能覆盖原判断。')
        return replay
    cas_lab(replay.lab)
    replay.judgment = data
    replay.save(update_fields=['judgment'])
    emit(replay.lab, 'judgment', replay.replay_id, digest(data))
    return replay


def replay_dto(replay):
    result = dict(replay_id=str(replay.replay_id), scenario_variant=replay.variant,
        scan_id=str(replay.scan.scan_id), profile_id=str(replay.profile_id), created_at=replay.created_at.isoformat(),
        judgment=replay.judgment, revealed=bool(replay.judgment), simulated=True,
        policy_version=POLICY_VERSION, policy_status='draft', evaluation_time=EVALUATION_TIME,
        execution_status='not_started', protection_status='not_assessed')
    if replay.judgment:
        result.update(frozen=replay.frozen, content_digest=replay.content_digest,
            reason_explanations={code: REASONS.get(code, '固定教学理由码；结合输入事实解释，不代表执行。')
                for step in replay.frozen['steps'] for code in step['result']['reason_codes']})
    return result
