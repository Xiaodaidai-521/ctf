import json
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from mainline1.parsing import InputError
from mainline1.review import ReviewConflict
from mainline1.rules import RuleResult
from .catalog import case_spec, digest
from .common import (Conflict, assert_same, basis_cards, cas_lab, check_payload, emit, key,
                     own_lab, text)
from .models import LabAttempt, ProfileIndex, ReviewLedger, Scan
from .repository import review_service
from .scanning import ScanFailure, restore_parsed, run_worker


@transaction.atomic
def save_basis(user, attempt_id, data):
    check_payload(data, ('entity_category', 'personal_information', 'data_classification', 'uncertainties',
                         'fact_ids', 'basis_ids', 'expected_revision'),
                  ('entity_category', 'personal_information', 'data_classification', 'uncertainties', 'fact_ids', 'basis_ids'))
    lab = own_lab(user, attempt_id, lock=True)
    spec = case_spec(lab.case.task.task_key)
    for field in ('entity_category', 'personal_information', 'data_classification', 'uncertainties'):
        text(data[field], field)
    validate_refs(lab, data)
    payload = {k: v for k, v in data.items() if k != 'expected_revision'}
    payload['cards'] = basis_cards(lab.case)
    if lab.basis_digest == digest(payload):
        return lab
    if data.get('expected_revision', lab.revision) != lab.revision:
        raise Conflict()
    cas_lab(lab)
    lab.basis, lab.basis_digest = payload, digest(payload)
    lab.save(update_fields=['basis', 'basis_digest'])
    emit(lab, 'basis', str(lab.attempt.attempt_id) + ':' + lab.basis_digest, lab.basis_digest)
    return lab


def validate_refs(lab, data):
    spec = case_spec(lab.case.task.task_key)
    for field, valid in [('fact_ids', set(spec['facts'])), ('basis_ids', {c['card_id'] for c in basis_cards(lab.case)})]:
        refs = data.get(field)
        if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x in valid for x in refs):
            raise ValidationError(f'{field}须引用本案例可见的事实/依据卡。')


def start_scan(user, attempt_id, data):
    check_payload(data, ('fixture_id', 'idempotency_key'), ('fixture_id', 'idempotency_key'))
    idempotency_key = key(data)
    with transaction.atomic():
        lab = own_lab(user, attempt_id, lock=True)
        spec = case_spec(lab.case.task.task_key)
        if data['fixture_id'] != spec['fixture_id']:
            raise ValidationError('仅接受本案例登记的合成资源引用。')
        # A lost worker/finalization transaction must not block this attempt forever.
        from datetime import timedelta
        expired = lab.scans.filter(status='running', created_at__lt=timezone.now() - timedelta(seconds=30))
        for interrupted in expired.select_for_update():
            interrupted.status, interrupted.failure_code = 'failed', 'SCAN_INTERRUPTED_RETRY_NEW_KEY'
            interrupted.save(update_fields=['status', 'failure_code'])
            emit(lab, 'scan_failed', interrupted.scan_id, interrupted.failure_code)
        existing = lab.scans.filter(idempotency_key=idempotency_key).first()
        if existing:
            return assert_same(existing, data)
        if not lab.basis:
            raise Conflict('先保存依据与适用事实。')
        if lab.scans.filter(status='running').exists():
            raise Conflict('已有识别运行中。')
        if lab.scans.count() >= 10:
            raise Conflict('本次尝试扫描次数达到上限。')
        cas_lab(lab)
        scan = Scan.objects.create(lab=lab, idempotency_key=idempotency_key,
                                   request_digest=digest(data), asset_digest=spec['sha256'])
        emit(lab, 'scan_requested', scan.scan_id, scan.request_digest)
    try:
        result = run_worker(scan)
    except ScanFailure as exc:
        with transaction.atomic():
            scan.status, scan.failure_code = 'failed', str(exc)
            scan.save(update_fields=['status', 'failure_code'])
            emit(lab, 'scan_failed', scan.scan_id, scan.failure_code)
        return scan
    with transaction.atomic():
        # Recheck ownership, material withdrawal and asset binding before publishing.
        lab = own_lab(user, attempt_id, lock=True)
        scan = Scan.objects.select_for_update().get(pk=scan.pk)
        if scan.status != 'running':
            return scan
        cas_lab(lab)
        if result['parsed']['input_content_hash'] != 'sha256:' + scan.asset_digest:
            raise Conflict('解析摘要不匹配。')
        scan.parsed, scan.original = result['parsed'], result['result']
        ReviewLedger.objects.create(scan=scan)
        service, principal = review_service(scan)
        pid = service.register(principal, RuleResult(json.dumps(scan.original)), restore_parsed(scan.parsed))
        ProfileIndex.objects.create(scan=scan, profile_id=pid)
        scan.current_profile_id, scan.status = pid, 'completed'
        scan.save(update_fields=['parsed', 'original', 'current_profile_id', 'status'])
        # A rescan creates a fresh teaching copy; no human judgment is inherited.
        lab.active_scan = scan
        lab.save(update_fields=['active_scan'])
        lab.attempt.status, lab.attempt.started_at = 'in_progress', lab.attempt.started_at or timezone.now()
        lab.attempt.save(update_fields=['status', 'started_at'])
        emit(lab, 'scan_completed', scan.scan_id, digest(scan.original))
    return scan


def owned_scan(user, scan_id, *, material=True):
    try:
        scan = Scan.objects.select_related('lab__attempt__student', 'lab__case__task__catalog').get(
            scan_id=scan_id, lab__attempt__student=user)
    except (Scan.DoesNotExist, ValueError):
        raise NotFound() from None
    own_lab(user, scan.lab.attempt.attempt_id, material=material)
    return scan


def scan_dto(scan, *, offset=0, limit=50):
    if not 0 <= offset or not 1 <= limit <= 100:
        raise ValidationError('分页范围不合法。')
    dto = dict(scan_id=str(scan.scan_id), status=scan.status, failure_code=scan.failure_code,
               asset_digest=scan.asset_digest, profile_id=str(scan.current_profile_id or ''),
               execution_status='not_started', protection_status='not_assessed')
    if scan.status != 'completed':
        dto['message'] = '解析失败/受环境影响；不计知识错误' if scan.status == 'failed' else '正在识别'
        return dto
    service, principal = review_service(scan)
    profile = service.get_profile(principal, str(scan.current_profile_id))
    app = service.get_profile_applicability(principal, str(scan.current_profile_id))
    findings = service.list_findings(principal, str(scan.current_profile_id), pending_only=False,
                                     offset=offset, limit=limit)
    originals = {f['finding_id']: f for f in scan.original['findings']}
    for item in findings['items']:
        original = originals.get(item['finding_id'], {})
        item.update(detector_id=original.get('detector_id'), detector_version=original.get('detector_version'),
                    raw_score=original.get('raw_score'), score_meaning=original.get('score_meaning'))
    dto.update(profile=profile, state_version=app['state_version'], findings=findings,
               cells=[{k: c[k] for k in ('sheet_id', 'row', 'column', 'source_text', 'channel')} for c in scan.parsed['cells']],
               coverage=scan.original['profile']['coverage'], cell_outcomes=scan.original['cell_outcomes'],
               counts={'original_findings': len(scan.original['findings']),
                       'manual_additions': service.repository.read(lambda s: sum(r['action'] == 'add_manual' for r in s.reviews.values())),
                       'reviewed_findings': len(profile['finding_ids'])},
               review_history=service.repository.read(lambda s: list(s.reviews.values())))
    return dto


@transaction.atomic
def submit_review(user, profile_id, data):
    check_payload(data, ('expected_state_version', 'idempotency_key', 'action', 'reason', 'finding_id', 'category_id',
                         'locations', 'fact_ids', 'basis_ids'),
                  ('expected_state_version', 'idempotency_key', 'action', 'reason', 'fact_ids', 'basis_ids'))
    try:
        index = ProfileIndex.objects.select_related('scan__lab__attempt', 'scan__lab__case__task__catalog').get(
            profile_id=profile_id, scan__lab__attempt__student=user)
    except (ProfileIndex.DoesNotExist, ValueError):
        raise NotFound() from None
    scan = index.scan
    lab = own_lab(user, scan.lab.attempt.attempt_id, lock=True)
    if lab.active_scan_id != scan.pk:
        raise Conflict('已重扫；旧复核不能继承到新教学副本。')
    validate_refs(lab, data)
    reason = text(data['reason'], 'reason', 1500)
    # Bind references into the original review fingerprint and immutable history.
    reason += '\n引用:' + json.dumps({'fact_ids': data['fact_ids'], 'basis_ids': data['basis_ids']}, ensure_ascii=False, sort_keys=True)
    service, principal = review_service(scan)
    cas_lab(lab)
    try:
        record = service.submit_review(principal, base_profile_id=str(profile_id),
            expected_state_version=data['expected_state_version'], idempotency_key=key(data),
            action=data['action'], reason=reason, finding_id=data.get('finding_id'),
            category_id=data.get('category_id'), locations=data.get('locations'))
    except ReviewConflict as exc:
        raise Conflict({'code': 'REVIEW_VERSION_CONFLICT', 'latest_profile_id': exc.latest_profile_id}) from None
    except InputError as exc:
        if exc.code in ('IDEMPOTENCY_CONFLICT', 'PROFILE_REEVALUATION_REQUIRED'):
            raise Conflict(exc.code) from None
        raise ValidationError(exc.code) from None
    ProfileIndex.objects.get_or_create(profile_id=record['successor_profile_id'], defaults={'scan': scan})
    # A retry of an earlier review must not move the head backwards.
    from mainline1.review import head_key
    head = service.repository.read(lambda s: s.heads[head_key(s.bundles[str(profile_id)]['profile'])])
    scan.current_profile_id = head
    scan.save(update_fields=['current_profile_id'])
    emit(lab, 'review', record['review_id'], record['request_fingerprint'])
    return record
