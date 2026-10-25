"""Module 6 → module 1 verification hand-off.

Shared contract (also documented in ``learning_map/README.md``):

    fact_id, student (internal id), catalog_version, capability_id,
    knowledge_point_id, task_key + task_version, attempt_id,
    outcome, independence, assistance_level/source/shown,
    retest_of_attempt_id, evidence_ref, verifier_version, occurred_at

The HTTP endpoint accepts this payload from a teacher/admin or from the
module-6 service (``X-Learning-Map-Service-Token``).  Local development and
tests use ``InMemoryVerificationFactSource``; the real module 6 is **not yet
connected**.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .. import constants
from .events import emit_event
from .pathing import apply_fact
from ..models import (
    Capability,
    CapabilityState,
    CatalogVersion,
    KnowledgePoint,
    TaskAttempt,
    TaskPackage,
    VerificationFact,
)


class FactError(ValueError):
    code = 'invalid_fact'


class FactConflict(FactError):
    code = 'fact_id_conflict'


FACT_FIELDS = (
    'fact_id', 'student_id', 'catalog_version', 'capability_id', 'knowledge_point_id',
    'task_key', 'task_version', 'attempt_id', 'outcome', 'independence',
    'assistance_level', 'assistance_source', 'assistance_shown', 'retest_of_attempt_id',
    'evidence_ref', 'verifier_version', 'occurred_at',
)


def _parse_occurred_at(value):
    if isinstance(value, datetime):
        occurred = value
    elif isinstance(value, str):
        occurred = parse_datetime(value)
    else:
        occurred = None
    if occurred is None:
        raise FactError('occurred_at 必须是 ISO 8601 时间。')
    if timezone.is_naive(occurred):
        occurred = timezone.make_aware(occurred, timezone.get_current_timezone())
    return occurred


def _compare_payload(fact, payload):
    """Return True when a repeated fact_id carries identical content."""

    expected = {
        'student_id': payload['student'].id,
        'catalog_id': payload['catalog'].id,
        'capability_id': payload['capability'].id,
        'knowledge_point_id': payload.get('knowledge_point').id if payload.get('knowledge_point') else None,
        'task_id': payload.get('task').id if payload.get('task') else None,
        'task_version': payload.get('task_version') or '',
        'attempt_id': payload.get('attempt_id'),
        'outcome': payload['outcome'],
        'independence': payload['independence'],
        'assistance_level': payload['assistance_level'],
        'assistance_source': payload['assistance_source'],
        'assistance_shown': payload['assistance_shown'],
        'retest_of_attempt_id': payload.get('retest_of_attempt_id'),
        'evidence_ref': payload.get('evidence_ref') or '',
        'verifier_version': payload.get('verifier_version') or '',
        'occurred_at': payload['occurred_at'],
    }
    for field, value in expected.items():
        if getattr(fact, field) != value:
            return False
    return True


def normalize_fact_payload(payload):
    """Validate and resolve foreign keys.  Raises ``FactError``.

    ``student`` may be a user instance or a primary key, so both the HTTP API
    and in-process module callers can share this contract.
    """

    missing = [field for field in ('fact_id', 'student', 'catalog_version', 'capability_id', 'outcome', 'independence') if not payload.get(field)]
    if missing:
        raise FactError(f'缺少字段：{", ".join(missing)}')
    student_value = payload['student']
    student_id = getattr(student_value, 'pk', student_value)
    if not hasattr(student_value, 'pk'):
        student_value = get_user_model().objects.filter(pk=student_id).first()
        if student_value is None:
            raise FactError(f'学生 {student_id} 不存在。')

    catalog = CatalogVersion.objects.filter(version=payload['catalog_version']).first()
    if not catalog:
        raise FactError(f'目录版本 {payload["catalog_version"]} 不存在。')
    capability = catalog.capabilities.filter(stable_id=payload['capability_id']).first()
    if not capability:
        raise FactError(f'能力 {payload["capability_id"]} 不在目录 {catalog.version} 中。')

    knowledge_point = None
    if payload.get('knowledge_point_id'):
        knowledge_point = KnowledgePoint.objects.filter(
            catalog=catalog, stable_id=payload['knowledge_point_id'],
        ).first()
        if not knowledge_point:
            raise FactError(f'知识点 {payload["knowledge_point_id"]} 不在目录中。')

    task = None
    if payload.get('task_key'):
        task = TaskPackage.objects.filter(
            catalog=catalog,
            task_key=payload['task_key'],
            version=payload.get('task_version') or '',
        ).first()
        if not task:
            raise FactError(f'任务 {payload["task_key"]}@{payload.get("task_version")} 不在目录中。')

    attempt_id = payload.get('attempt_id')
    if attempt_id:
        attempt = TaskAttempt.objects.filter(attempt_id=attempt_id).first()
        if not attempt:
            raise FactError(f'尝试 {attempt_id} 不存在。')
        if attempt.student_id != student_id:
            raise FactError('尝试不属于该学生。')

    retest_of_attempt_id = payload.get('retest_of_attempt_id')
    if retest_of_attempt_id:
        original = TaskAttempt.objects.filter(attempt_id=retest_of_attempt_id).first()
        if not original:
            raise FactError(f'复测关联的原尝试 {retest_of_attempt_id} 不存在。')
        if original.student_id != student_id:
            raise FactError('复测关联的原尝试不属于该学生。')

    outcome = payload['outcome']
    if outcome not in dict(constants.OUTCOME_CHOICES):
        raise FactError(f'未知核验结论：{outcome}')
    independence = payload['independence']
    if independence not in dict(constants.INDEPENDENCE_CHOICES):
        raise FactError(f'未知独立性：{independence}')

    assistance_level = int(payload.get('assistance_level') or 0)
    if assistance_level < 0 or assistance_level > 4:
        raise FactError('帮助层级必须在 0—4。')
    assistance_shown = bool(payload.get('assistance_shown'))
    assistance_source = payload.get('assistance_source') or constants.ASSISTANCE_SOURCE_NONE
    if assistance_source not in dict(constants.ASSISTANCE_SOURCE_CHOICES):
        raise FactError(f'未知帮助来源：{assistance_source}')
    if independence == constants.INDEPENDENCE_ASSISTED:
        if not assistance_shown or assistance_level < 1:
            raise FactError('受助状态必须记录实际展示的帮助层级（1—4）。')
        if assistance_source in (constants.ASSISTANCE_SOURCE_NONE, constants.ASSISTANCE_SOURCE_UNKNOWN):
            raise FactError('受助状态必须注明帮助来源。')
    if independence == constants.INDEPENDENCE_INDEPENDENT and assistance_shown:
        raise FactError('实际展示过帮助时不能标记为平台内独立。')

    if outcome == constants.OUTCOME_PASSED and independence == constants.INDEPENDENCE_ASSISTED:
        pass
    if outcome == constants.OUTCOME_ENVIRONMENT_AFFECTED and independence == constants.INDEPENDENCE_INDEPENDENT:
        raise FactError('受环境影响的结果不能标记为独立。')

    return {
        'fact_id': str(payload['fact_id']),
        'student': student_value,
        'catalog': catalog,
        'capability': capability,
        'knowledge_point': knowledge_point,
        'task': task,
        'task_version': payload.get('task_version') or (task.version if task else ''),
        'attempt_id': attempt_id,
        'outcome': outcome,
        'independence': independence,
        'assistance_level': assistance_level,
        'assistance_source': assistance_source,
        'assistance_shown': assistance_shown,
        'retest_of_attempt_id': retest_of_attempt_id,
        'first_attempt': bool(payload.get('first_attempt', True)),
        'evidence_ref': payload.get('evidence_ref') or '',
        'verifier_version': payload.get('verifier_version') or '',
        'occurred_at': _parse_occurred_at(payload.get('occurred_at')),
        'payload': payload.get('payload') or {},
    }


@transaction.atomic
def ingest_verification_fact(payload, actor=None):
    """Persist one fact idempotently, then update the path state.

    Returns ``(fact, state, path_changed, created)``.
    """

    normalized = normalize_fact_payload(payload)
    existing = VerificationFact.objects.select_for_update().filter(fact_id=normalized['fact_id']).first()
    if existing:
        if not _compare_payload(existing, normalized):
            raise FactConflict('相同 fact_id 对应不同内容，拒绝覆盖；请使用新的 fact_id。')
        state = CapabilityState.objects.filter(
            student=existing.student, catalog=existing.catalog, capability=existing.capability,
        ).first()
        return existing, state, False, False

    fact = VerificationFact.objects.create(**normalized)
    state, changed = apply_fact(fact, actor=actor)
    emit_event(
        user=fact.student,
        event_type='verification_result',
        event_id=f'lm-fact-{fact.fact_id}',
        catalog=fact.catalog,
        task=fact.task,
        attempt_id=fact.attempt_id,
        capability_ids=[fact.capability.stable_id],
        evidence_ref=fact.evidence_ref,
        verifier_version=fact.verifier_version,
        assistance_level=fact.assistance_level,
        assistance_source=fact.assistance_source,
        assistance_shown=fact.assistance_shown,
        extra={
            'fact_id': fact.fact_id,
            'outcome': fact.outcome,
            'independence': fact.independence,
            'retest_of_attempt_id': str(fact.retest_of_attempt_id or ''),
        },
    )
    return fact, state, changed, True


def build_ack(fact, state, path_changed, created):
    return {
        'accepted': True,
        'created': created,
        'path_changed': path_changed,
        'fact_id': fact.fact_id,
        'catalog_version': fact.catalog.version,
        'capability_id': fact.capability.stable_id,
        'state': state.state if state else None,
        'state_label': constants.STATE_LABELS.get(state.state) if state else None,
        'rule_version': fact.catalog.rule_version or constants.RULE_VERSION,
        'module6_connected': False,
        'note': '本地事实接口已接收；真实模块六联调尚未完成。',
    }


class VerificationFactSource(Protocol):
    """Read-side contract for modules that need module-1 path state."""

    def fetch_facts(self, student_id, catalog_version, since=None):
        ...

    def fetch_states(self, student_id, catalog_version):
        ...


class DjangoVerificationFactSource:
    """Local, real-DB implementation of the read-side hand-off."""

    def fetch_facts(self, student_id, catalog_version, since=None):
        queryset = VerificationFact.objects.filter(
            student_id=student_id, catalog__version=catalog_version,
        ).select_related('capability', 'task').order_by('occurred_at', 'fact_id')
        if since:
            queryset = queryset.filter(occurred_at__gte=since)
        return queryset

    def fetch_states(self, student_id, catalog_version):
        return CapabilityState.objects.filter(
            student_id=student_id, catalog__version=catalog_version,
        ).select_related('capability')


@dataclass
class MemoryVerificationFactSource:
    """Local test double.  Not a persistence backend."""

    facts: list
    states: list

    def fetch_facts(self, student_id, catalog_version, since=None):
        return [
            fact for fact in self.facts
            if fact['student_id'] == student_id
            and fact['catalog_version'] == catalog_version
            and (since is None or fact['occurred_at'] >= since)
        ]

    def fetch_states(self, student_id, catalog_version):
        return [
            state for state in self.states
            if state['student_id'] == student_id
            and state['catalog_version'] == catalog_version
        ]
