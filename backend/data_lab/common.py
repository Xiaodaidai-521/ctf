from django.db import transaction
from django.db.models import F
from rest_framework.exceptions import APIException, NotFound, ValidationError
from learning_map.models import DataBasisCard
from learning_map.services import events
from .catalog import BASIS_IDS, case_spec, digest
from .models import CasePackage, LabAttempt


class Conflict(APIException):
    status_code = 409
    default_detail = '状态已变化，请刷新后重试。'


class SavePending(APIException):
    status_code = 503
    default_detail = '保存待重试'


def short_id(*parts):
    return 'd4-' + digest([str(p) for p in parts])[:48]


def is_teacher(user):
    return bool(user.is_authenticated and (user.is_superuser or getattr(user, 'role', '') in ('teacher', 'admin')))


def teacher_allowed(user, case):
    return is_teacher(user) and (case.owner_id == user.id or case.teachers.filter(pk=user.id).exists())


def basis_cards(case, *, require_reviewed=True):
    cards = list(DataBasisCard.objects.filter(catalog=case.task.catalog, card_id__in=BASIS_IDS).order_by('card_id'))
    if len(cards) != len(BASIS_IDS) or (require_reviewed and any(c.status != 'reviewed' for c in cards)):
        raise Conflict('依据卡缺失或已撤回，停止新读取/引用。')
    fields = ('card_id', 'source_title', 'source_clause', 'source_version', 'source_url', 'applicable_facts',
              'classification_conclusion', 'uncertainties', 'protection_measures', 'scoring_evidence', 'status')
    return [{**{k: getattr(c, k) for k in fields}, 'verified_date': str(c.verified_date or ''),
             'record_digest': digest({k: getattr(c, k) for k in fields})} for c in cards]


def require_material(case, *, claiming=False):
    task = case.task
    spec = case_spec(task.task_key)
    if (case.withdrawn or task.materials_withdrawn or task.status != 'frozen'
            or task.catalog.status != 'published' or not task.environment_available
            or task.requires_milestone_i or task.execution_mode != 'readonly_decision'
            or task.version != spec['task_version'] or case.material_digest != digest(spec)
            or case.status != 'released'):
        raise Conflict('课程仍为草案、材料撤回或版本不可用；未开放。')
    reviews = (case.author_review, case.second_review)
    if (not all(r.get('actor_id') and r.get('at') and r.get('digest') == case.material_digest for r in reviews)
            or reviews[0]['actor_id'] == reviews[1]['actor_id']
            or not all(case.release_checks.get(k) is True for k in ('readonly', 'no_ai', 'events', 'permissions'))):
        raise Conflict('教师双人签收或发布门禁未完成。')
    if claiming and case.paused:
        raise Conflict('教师已暂停新领取。')
    basis_cards(case)
    return spec


def own_lab(user, attempt_id, *, material=True, lock=False):
    query = LabAttempt.objects.select_related('attempt__student', 'attempt__task__catalog', 'case__task__catalog')
    if lock:
        query = query.select_for_update()
    try:
        lab = query.get(attempt__attempt_id=attempt_id, attempt__student=user)
    except (LabAttempt.DoesNotExist, ValueError):
        raise NotFound() from None
    if material:
        require_material(lab.case)
    return lab


def cas_lab(lab):
    if not LabAttempt.objects.filter(pk=lab.pk, revision=lab.revision).update(revision=F('revision') + 1):
        raise Conflict()
    lab.revision += 1


def check_payload(data, allowed, required=()):
    if not isinstance(data, dict) or set(data) - set(allowed) or any(k not in data for k in required):
        raise ValidationError('请求字段不受支持；可信环境、授权、摘要与策略不可由客户端指定。')
    return data


def text(value, name, maximum=2048):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError(f'{name}不能为空且须在长度限制内。')
    return value.strip()


def key(data):
    return text(data.get('idempotency_key'), 'idempotency_key', 64)


def assert_same(existing, payload):
    if existing.request_digest != digest(payload):
        raise Conflict('同键异内容。')
    return existing


def emit(lab, action, object_id, content_digest='', *, event_type='task_start', level=0, source='none', shown=False):
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError('EVENT_REQUIRES_TRANSACTION')
    attempt = lab.attempt
    binding = digest([str(attempt.attempt_id), action, str(object_id), content_digest, level, source, shown])
    event, _ = events.emit_event(user=attempt.student, event_type=event_type,
        event_id=short_id(action, object_id), catalog=attempt.catalog, task=attempt.task,
        attempt_id=attempt.attempt_id, capability_ids=attempt.capability_ids,
        knowledge_point_ids=list(attempt.task.capabilities.values_list('knowledge_points__stable_id', flat=True).distinct()),
        evidence_ref=f'data-lab:{action}:{object_id}', verifier_version=case_spec(attempt.task.task_key)['validator_version'],
        assistance_level=level, assistance_source=source, assistance_shown=shown,
        extra={'source': 'data_lab', 'action': action, 'binding': binding})
    if event.user_id != attempt.student_id or event.event_type != event_type or event.metadata.get('binding') != binding:
        raise Conflict('学习事件ID内容冲突；保存待重试。')
    return event
