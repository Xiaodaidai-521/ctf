"""Evidence normalization, missing-slot calculation and dedup keys.

The module stores only references and short summaries.  It never stores answer
text, teacher answer keys, credentials or a second copy of a module 1/6 fact.
"""

import hashlib
import json
import re

from django.utils import timezone

from .. import constants
from ..models import FeedbackAttachment, FeedbackEvidence


class EvidenceError(ValueError):
    code = 'invalid_evidence'


KNOWN_SLOTS = set(constants.EVIDENCE_SLOT_LABELS)


def normalize_dispute(text):
    """Normalize whitespace and common punctuation for exact duplicate checks.

    This is intentionally conservative: only exact (normalized) same-attempt,
    same-category, same-dispute submissions are linked automatically.  Similar
    wording is left for the phase-3 manual issue-group review.
    """

    value = (text or '').strip().lower()
    value = re.sub(r'\s+', '', value)
    value = re.sub(r'[，。！？；：、“”‘’（）【】《》,.!?;:\'"()\[\]<>]', '', value)
    return value


def compute_dedup_key(*, student_id, attempt_key, category, dispute, task_key='', task_version=''):
    raw = json.dumps(
        {
            'student_id': student_id,
            'attempt': attempt_key or '',
            'task': f'{task_key or ""}@{task_version or ""}',
            'category': category,
            'dispute': normalize_dispute(dispute),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _json_default(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def compute_request_fingerprint(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=_json_default)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def normalize_evidence_inputs(items):
    """Return a stable, JSON-safe list for fingerprinting and storage."""

    normalized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        slot = str(item.get('slot') or '').strip()
        if not slot:
            continue
        normalized.append({
            'slot': slot,
            'ref': str(item.get('ref') or '').strip(),
            'version': str(item.get('version') or '').strip(),
            'summary': str(item.get('summary') or '').strip(),
            'attachment_id': str(item.get('attachment_id') or '').strip(),
            'status': str(item.get('status') or constants.EVIDENCE_STATUS_PROVIDED).strip(),
            'visibility': str(item.get('visibility') or constants.VISIBILITY_STUDENT).strip(),
        })
    return sorted(normalized, key=lambda item: (item['slot'], item['ref'], item['summary']))


def slot_label(slot):
    return constants.EVIDENCE_SLOT_LABELS.get(slot, slot)


def missing_slots(ticket):
    rows = ticket.evidence.filter(is_current=True)
    by_slot = {row.slot: row for row in rows}
    missing = []
    for slot in constants.required_slots(ticket.category, ticket.issue_type):
        row = by_slot.get(slot)
        if row is None or row.status in constants.INCOMPLETE_EVIDENCE_STATUSES:
            missing.append(slot)
    return missing


def sync_missing_evidence(ticket):
    ticket.missing_evidence = missing_slots(ticket)
    ticket.save(update_fields=['missing_evidence', 'updated_at'])
    return ticket.missing_evidence


def _auto_original_decision(ticket):
    if ticket.original_decision_ref:
        return {
            'ref': ticket.original_decision_ref,
            'version': ticket.original_decision_version,
            'summary': '提交人提供的原始判定引用；原始判定本身未被修改。',
            'status': constants.EVIDENCE_STATUS_PROVIDED,
        }
    return None


def _auto_attempt(ticket):
    if not ticket.attempt_id:
        return None
    return {
        'ref': str(ticket.attempt.attempt_id),
        'version': ticket.task_version,
        'summary': f'模块一任务尝试；状态 {ticket.attempt.get_status_display()}；任务版本 {ticket.task_version}。',
        'status': constants.EVIDENCE_STATUS_PROVIDED,
    }


def _auto_submission_verification(ticket, context):
    facts = context.get('verification_facts') or []
    if facts:
        fact_ids = ','.join(item['fact_id'] for item in facts[:5])
        outcomes = '、'.join(sorted({item['outcome'] for item in facts}))
        independence = '、'.join(sorted({item['independence'] for item in facts}))
        return {
            'ref': fact_ids,
            'version': ';'.join(sorted({item.get('verifier_version') or '' for item in facts if item.get('verifier_version')})),
            'summary': f'模块六核验事实 {len(facts)} 条；结论 {outcomes}；独立性 {independence}。',
            'status': constants.EVIDENCE_STATUS_PROVIDED,
        }
    if ticket.attempt_id and ticket.attempt.submitted_at:
        return {
            'ref': ticket.attempt.evidence_ref or f'attempt:{ticket.attempt.attempt_id}',
            'version': '',
            'summary': '尝试已提交，但尚未收到模块六核验事实；核验状态未知。',
            'status': constants.EVIDENCE_STATUS_UNKNOWN,
        }
    return None


def _auto_help_trace(ticket, context):
    events = (context.get('hint_events') or []) + (context.get('teacher_help_events') or [])
    assistance = context.get('assistance_records') or []
    if events or assistance:
        refs = [item.get('event_id') or item.get('record_id') for item in (events + assistance)]
        refs = [str(ref) for ref in refs if ref][:8]
        shown = context.get('help_shown')
        levels = sorted({
            int(item.get('level') or 0)
            for item in (events + assistance)
            if int(item.get('level') or 0) > 0
        })
        sources = sorted({
            item.get('source') or 'unknown'
            for item in (events + assistance)
        })
        return {
            'ref': ','.join(refs),
            'version': '',
            'summary': (
                f'发现帮助记录 {len(refs)} 条；实际展示={shown}；层级={levels or "无"}；'
                f'来源={sources or "未知"}。请求未展示不计受助。'
            ),
            'status': constants.EVIDENCE_STATUS_PROVIDED,
        }
    return {
        'ref': 'help_record_unknown',
        'version': '',
        'summary': '未发现提示或教师帮助记录；帮助状态未知，不能推定独立，也不据此改写原判定。',
        'status': constants.EVIDENCE_STATUS_UNKNOWN,
    }


def _auto_rubric(ticket):
    validator = ticket.task.validator if ticket.task else {}
    acceptance = ticket.task.acceptance if ticket.task else {}
    version = (
        (validator or {}).get('rubric_version')
        or (validator or {}).get('version')
        or (acceptance or {}).get('rubric_version')
    )
    if version:
        return {
            'ref': f'validator:{version}',
            'version': str(version),
            'summary': '任务包验证器/量表版本引用。',
            'status': constants.EVIDENCE_STATUS_PROVIDED,
        }
    return None


def _auto_material(ticket):
    if not ticket.task:
        return None
    materials = ticket.task.materials or {}
    refs = materials.get('student_material_refs') or []
    version = materials.get('version') or materials.get('material_version')
    if refs or version:
        return {
            'ref': ','.join(str(ref) for ref in refs[:5]),
            'version': str(version or ''),
            'summary': '任务包学生材料引用；只读版本快照。',
            'status': constants.EVIDENCE_STATUS_PROVIDED,
        }
    return None


def _auto_policy_version(ticket):
    if not ticket.task:
        return None
    validator = ticket.task.validator or {}
    version = validator.get('version') or validator.get('policy_version')
    if version:
        return {
            'ref': f'policy:{version}',
            'version': str(version),
            'summary': '任务包教学策略/验证器版本引用。',
            'status': constants.EVIDENCE_STATUS_PROVIDED,
        }
    return None


def _auto_request_scope(ticket):
    if not ticket.attempt_id:
        return None
    snapshot = ticket.attempt.submission_snapshot or {}
    for key in ('request_scope', 'record_count', 'scope'):
        if key in snapshot:
            value = snapshot.get(key)
            return {
                'ref': f'attempt-snapshot:{key}',
                'version': ticket.task_version,
                'summary': f'提交快照中的请求范围字段 {key}：{json.dumps(value, ensure_ascii=False)[:200]}',
                'status': constants.EVIDENCE_STATUS_PROVIDED,
            }
    return None


def _auto_business_purpose(ticket):
    if not ticket.attempt_id:
        return None
    snapshot = ticket.attempt.submission_snapshot or {}
    for key in ('business_purpose', 'purpose'):
        if key in snapshot:
            return {
                'ref': f'attempt-snapshot:{key}',
                'version': ticket.task_version,
                'summary': f'提交快照中的业务目的字段 {key}：{str(snapshot.get(key))[:200]}',
                'status': constants.EVIDENCE_STATUS_PROVIDED,
            }
    return None


def _auto_retest(ticket, context):
    if context.get('retest_present'):
        facts = context.get('verification_facts') or []
        assignments = context.get('retest_assignments') or []
        refs = [item.get('fact_id') for item in facts if item.get('retest_of_attempt_id')]
        refs += [item.get('assignment_id') for item in assignments]
        return {
            'ref': ','.join(str(ref) for ref in refs[:8]),
            'version': '',
            'summary': '已关联模块六复测事实/安排；复测效果仍需按真实结果判定。',
            'status': constants.EVIDENCE_STATUS_PROVIDED,
        }
    return {
        'ref': 'not_retested',
        'version': '',
        'summary': '未发现复测记录，明确标注“未复测”；教学效果待验证，不能宣称改善。',
        'status': constants.EVIDENCE_STATUS_PROVIDED,
    }


def build_auto_evidence(ticket, context):
    """Return server-linked references for slots the server can honestly fill."""

    auto = {}
    original = _auto_original_decision(ticket)
    if original:
        auto[constants.EVIDENCE_SLOT_ORIGINAL_DECISION] = original
    attempt = _auto_attempt(ticket)
    if attempt:
        auto[constants.EVIDENCE_SLOT_ATTEMPT_REF] = attempt
    submission = _auto_submission_verification(ticket, context)
    if submission:
        auto[constants.EVIDENCE_SLOT_SUBMISSION_VERIFICATION] = submission
    auto[constants.EVIDENCE_SLOT_HELP_TRACE] = _auto_help_trace(ticket, context)
    rubric = _auto_rubric(ticket)
    if rubric:
        auto[constants.EVIDENCE_SLOT_RUBRIC_VERSION] = rubric
    material = _auto_material(ticket)
    if material:
        auto[constants.EVIDENCE_SLOT_MATERIAL_VERSION] = material
    policy = _auto_policy_version(ticket)
    if policy:
        auto[constants.EVIDENCE_SLOT_POLICY_VERSION] = policy
    scope = _auto_request_scope(ticket)
    if scope:
        auto[constants.EVIDENCE_SLOT_REQUEST_SCOPE] = scope
    purpose = _auto_business_purpose(ticket)
    if purpose:
        auto[constants.EVIDENCE_SLOT_BUSINESS_PURPOSE] = purpose
    auto[constants.EVIDENCE_SLOT_REVIEW_RETEST] = _auto_retest(ticket, context)
    return auto


def _validate_slot(slot):
    if slot not in KNOWN_SLOTS:
        raise EvidenceError(f'未知证据槽：{slot}')
    return slot


def _row_from_input(ticket, item, *, actor, source, default_visibility, supersedes=None):
    slot = _validate_slot(str(item.get('slot') or '').strip())
    status = item.get('status') or constants.EVIDENCE_STATUS_PROVIDED
    if status not in dict(constants.EVIDENCE_STATUS_CHOICES):
        raise EvidenceError(f'未知证据状态：{status}')
    if status == constants.EVIDENCE_STATUS_MISSING:
        raise EvidenceError('不能手工提交“缺失”状态；请提供证据或标注未知。')
    ref = str(item.get('ref') or '').strip()
    summary = str(item.get('summary') or '').strip()
    attachment = item.get('attachment')
    if status == constants.EVIDENCE_STATUS_PROVIDED and not (ref or summary or attachment):
        raise EvidenceError(f'证据槽 {slot} 缺少引用、摘要或附件。')
    if status in (constants.EVIDENCE_STATUS_UNKNOWN, constants.EVIDENCE_STATUS_NOT_APPLICABLE) and not summary:
        raise EvidenceError(f'证据槽 {slot} 标记为未知/不适用时必须说明原因。')
    visibility = item.get('visibility') or default_visibility
    if visibility not in dict(constants.VISIBILITY_CHOICES):
        raise EvidenceError(f'未知可见范围：{visibility}')
    return FeedbackEvidence(
        ticket=ticket,
        slot=slot,
        ref=ref,
        version=str(item.get('version') or '').strip(),
        summary=summary,
        attachment=attachment,
        status=status,
        source=source,
        visibility=visibility,
        is_current=True,
        supersedes=supersedes,
        created_by=actor,
    )


def create_initial_evidence(ticket, inputs, *, actor, context):
    """Create one current row per required slot plus any extra supplied slots.

    Missing slots are stored explicitly, so the teacher sees what is missing
    instead of inferring it from an empty list.
    """

    supplied = {}
    for item in normalize_evidence_inputs(inputs):
        slot = item['slot']
        if slot not in KNOWN_SLOTS:
            raise EvidenceError(f'未知证据槽：{slot}')
        if item.get('ref') or item.get('summary') or item.get('attachment_id'):
            supplied[slot] = item

    auto = build_auto_evidence(ticket, context)
    required = constants.required_slots(ticket.category, ticket.issue_type)
    created = []

    for slot in required:
        if slot in supplied:
            row = _row_from_input(
                ticket, supplied[slot], actor=actor,
                source=constants.EVIDENCE_SOURCE_SUBMITTER,
                default_visibility=constants.VISIBILITY_STUDENT,
            )
        elif slot in auto:
            auto_item = dict(auto[slot], slot=slot)
            row = _row_from_input(
                ticket, auto_item, actor=actor,
                source=constants.EVIDENCE_SOURCE_SERVER_LINKED,
                default_visibility=constants.VISIBILITY_STUDENT,
            )
        else:
            row = FeedbackEvidence(
                ticket=ticket,
                slot=slot,
                status=constants.EVIDENCE_STATUS_MISSING,
                source=constants.EVIDENCE_SOURCE_SERVER_LINKED,
                visibility=constants.VISIBILITY_STUDENT,
                is_current=True,
                created_by=actor,
            )
        row.save()
        created.append(row)

    for slot, item in supplied.items():
        if slot in required:
            continue
        row = _row_from_input(
            ticket, item, actor=actor,
            source=constants.EVIDENCE_SOURCE_SUBMITTER,
            default_visibility=constants.VISIBILITY_STUDENT,
        )
        row.save()
        created.append(row)

    sync_missing_evidence(ticket)
    return created


def add_evidence(ticket, inputs, *, actor, source=constants.EVIDENCE_SOURCE_SUBMITTER,
                 default_visibility=constants.VISIBILITY_STUDENT):
    """Append new current evidence rows, preserving the previous versions."""

    changed = []
    for item in normalize_evidence_inputs(inputs):
        slot = _validate_slot(item['slot'])
        if not (item.get('ref') or item.get('summary') or item.get('attachment_id')):
            continue
        attachment = item.get('attachment')
        if attachment is None and item.get('attachment_id'):
            attachment = FeedbackAttachment.objects.filter(
                attachment_id=item['attachment_id'], ticket=ticket,
            ).first()
            if attachment is None:
                raise EvidenceError('附件不存在或不属于该反馈工单。')
        if attachment is not None and attachment.ticket_id != ticket.id:
            raise EvidenceError('附件不属于该反馈工单。')
        previous = ticket.evidence.filter(slot=slot, is_current=True).first()
        if previous is not None:
            previous.is_current = False
            previous.save(update_fields=['is_current'])
        row = _row_from_input(
            ticket, dict(item, attachment=attachment), actor=actor, source=source,
            default_visibility=default_visibility, supersedes=previous,
        )
        row.save()
        changed.append(slot)
    if changed:
        ticket.last_evidence_at = timezone.now()
        ticket.save(update_fields=['last_evidence_at', 'updated_at'])
        sync_missing_evidence(ticket)
    return changed


def mapping_missing_fields(ticket):
    missing = []
    if not ticket.catalog_id:
        missing.append('catalog_version')
    if not ticket.task_id:
        missing.append('task')
    if not ticket.attempt_id:
        missing.append('attempt')
    if not (ticket.capability_id or ticket.knowledge_point_id):
        missing.append('capability_or_knowledge_point')
    return missing


def evidence_gate(ticket):
    return {
        'evidence_complete': ticket.evidence_complete,
        'mapping_complete': ticket.mapping_complete,
        'missing_evidence': list(ticket.missing_evidence or []),
        'missing_mapping': mapping_missing_fields(ticket),
        'candidate_eligible': ticket.candidate_eligible,
        'duplicate_of': str(ticket.duplicate_of.feedback_id) if ticket.duplicate_of else None,
    }
