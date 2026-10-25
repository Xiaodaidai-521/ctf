"""Deterministic, explainable recommendation.

Ordering follows operation plan section 4:
到期复测 → 当前目标缺失的先修 → 未通过知识点练习 → 受助后的巩固 → 新能力任务.

The function never calls a model.  Given the same catalog, states, facts and
rule version it returns the same items and reasons.  Every run stores its
input snapshot and output for later explanation and regression.
"""

import hashlib
import json

from django.conf import settings
from django.utils import timezone

from .. import constants
from .events import emit_event
from .pathing import refresh_due_retests
from ..models import (
    Capability,
    CapabilityState,
    DiagnosticSession,
    RecommendationRun,
    TaskAttempt,
    TaskPackage,
    TeacherAdjustment,
    VerificationFact,
)


class RecommendationError(ValueError):
    pass


def _canonical_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _capability_sort_key(capability):
    return (capability.course_order, capability.stable_id)


def _task_payload(task):
    if task is None:
        return None
    return {
        'id': task.id,
        'task_key': task.task_key,
        'version': task.version,
        'title': task.title,
        'purpose': task.purpose,
        'purpose_label': dict(constants.PURPOSE_CHOICES).get(task.purpose, task.purpose),
        'execution_mode': task.execution_mode,
        'track': task.track,
        'course_order': task.course_order,
    }


def _attempted_task_keys(student, catalog):
    # A claimed/in-progress attempt is not a completed attempt: it must not
    # hide an otherwise valid teacher assignment or practice task.  The claim
    # endpoint itself is idempotent and returns the existing attempt.
    return {
        attempt.task.task_key
        for attempt in TaskAttempt.objects.filter(
            student=student,
            catalog=catalog,
            status__in=(
                constants.ATTEMPT_SUBMITTED,
                constants.ATTEMPT_PENDING_VERIFICATION,
                constants.ATTEMPT_VERIFIED,
            ),
        ).select_related('task')
    }


def _satisfied_capability_ids(states):
    return {
        stable_id for stable_id, state in states.items()
        if state.state in constants.PREREQUISITE_SATISFIED_STATES
    }


def _select_task(*, capability, purposes, satisfied, attempted, catalog, exclude_keys=()):
    queryset = (
        TaskPackage.objects.filter(
            catalog=catalog,
            status=constants.TASK_STATUS_FROZEN,
            capabilities=capability,
            purpose__in=purposes,
        )
        .prefetch_related('prerequisite_capabilities')
        .distinct()
    )
    candidates = []
    for task in queryset:
        if not task.is_recommendable:
            continue
        if task.task_key in exclude_keys or task.task_key in attempted:
            continue
        required = {
            cap.stable_id for cap in task.prerequisite_capabilities.all()
        }
        if not required.issubset(satisfied):
            continue
        candidates.append(task)
    if not candidates:
        return None
    return min(candidates, key=lambda task: (task.course_order, task.task_key, task.version))


def _build_snapshot(student, catalog, goal_track, now):
    states = {
        state.capability.stable_id: state
        for state in CapabilityState.objects.filter(student=student, catalog=catalog)
        .select_related('capability')
    }
    facts = list(
        VerificationFact.objects.filter(student=student, catalog=catalog)
        .select_related('capability', 'task')
        .order_by('fact_id')
    )
    diagnosed_tracks = set()
    for session in DiagnosticSession.objects.filter(
        student=student, catalog=catalog, status='completed',
    ):
        if session.goal_track == constants.TRACK_BOTH:
            diagnosed_tracks.update({constants.TRACK_DATA, constants.TRACK_NETWORK})
        else:
            diagnosed_tracks.add(session.goal_track)

    tasks = list(
        TaskPackage.objects.filter(catalog=catalog)
        .prefetch_related('capabilities', 'prerequisite_capabilities')
        .order_by('task_key', 'version')
    )
    attempts = list(
        TaskAttempt.objects.filter(student=student, catalog=catalog)
        .exclude(status=constants.ATTEMPT_ABANDONED)
        .select_related('task')
        .order_by('attempt_id')
    )
    adjustments = list(
        TeacherAdjustment.objects.filter(
            student=student, catalog=catalog, status__in=['recorded', 'applied'],
        ).select_related('task').order_by('id')
    )

    snapshot = {
        'catalog_version': catalog.version,
        'rule_version': catalog.rule_version or constants.RULE_VERSION,
        'goal_track': goal_track or constants.TRACK_BOTH,
        'config': {
            'retest_interval_days': int(getattr(settings, 'LEARNING_MAP_RETEST_INTERVAL_DAYS', 3)),
            'prerequisite_satisfied_states': sorted(constants.PREREQUISITE_SATISFIED_STATES),
            'core_requires_ai': False,
        },
        'states': [
            {
                'capability_id': stable_id,
                'state': state.state,
                'diagnosis_result': state.diagnosis_result,
                'reason_code': state.reason_code,
                'retest_due_at': state.retest_due_at.isoformat() if state.retest_due_at else None,
                'evidence_ref': state.evidence_ref,
            }
            for stable_id, state in sorted(states.items())
        ],
        'facts': [
            {
                'fact_id': fact.fact_id,
                'capability_id': fact.capability.stable_id,
                'outcome': fact.outcome,
                'independence': fact.independence,
                'retest_of_attempt_id': str(fact.retest_of_attempt_id) if fact.retest_of_attempt_id else None,
                'task_key': fact.task.task_key if fact.task else '',
                'occurred_at': fact.occurred_at.isoformat(),
            }
            for fact in facts
        ],
        'diagnosed_tracks': sorted(diagnosed_tracks),
        'tasks': [
            {
                'task_key': task.task_key,
                'version': task.version,
                'purpose': task.purpose,
                'status': task.status,
                'recommendable': task.is_recommendable,
                'requires_milestone_i': task.requires_milestone_i,
                'capability_ids': sorted(cap.stable_id for cap in task.capabilities.all()),
                'prerequisite_ids': sorted(cap.stable_id for cap in task.prerequisite_capabilities.all()),
                'course_order': task.course_order,
                'environment_available': task.environment_available,
                'materials_withdrawn': task.materials_withdrawn,
            }
            for task in tasks
        ],
        'attempts': [
            {
                'attempt_id': str(attempt.attempt_id),
                'task_key': attempt.task.task_key,
                'task_version': attempt.task_version,
                'status': attempt.status,
            }
            for attempt in attempts
        ],
        'adjustments': [
            {
                'id': adjustment.id,
                'action': adjustment.action,
                'task_key': adjustment.task.task_key if adjustment.task else '',
                'task_version': adjustment.task.version if adjustment.task else '',
                'status': adjustment.status,
                'rationale': adjustment.rationale,
            }
            for adjustment in adjustments
        ],
    }
    return snapshot, states, facts, diagnosed_tracks, tasks, attempts, adjustments


def compute_recommendation(*, student, catalog, goal_track=None, actor=None, now=None):
    if goal_track in ('', None):
        goal_track = constants.TRACK_BOTH
    if goal_track not in (constants.TRACK_DATA, constants.TRACK_NETWORK, constants.TRACK_BOTH):
        raise RecommendationError('目标主线不合法。')

    now = now or timezone.now()
    refresh_due_retests(student, catalog, now=now)

    snapshot, states, facts, diagnosed_tracks, tasks, attempts, adjustments = _build_snapshot(
        student, catalog, goal_track, now,
    )
    inputs_hash = _canonical_hash(snapshot)

    scope_tracks = (
        {constants.TRACK_DATA, constants.TRACK_NETWORK}
        if goal_track == constants.TRACK_BOTH else {goal_track}
    )
    open_capabilities = [
        capability for capability in catalog.capabilities.filter(
            status=constants.CAPABILITY_STATUS_OPEN,
        ).prefetch_related('prerequisites', 'knowledge_points').order_by('course_order', 'stable_id')
        if capability.track in scope_tracks
    ]
    facts_by_capability = {}
    for fact in facts:
        facts_by_capability.setdefault(fact.capability.stable_id, []).append(fact)

    satisfied = _satisfied_capability_ids(states)
    attempted = _attempted_task_keys(student, catalog)
    items = []
    gaps = []
    seen_capabilities = set()
    seen_tasks = set()

    def add_gap(code, detail, *, capability=None, category=None, track=None):
        gaps.append({
            'code': code,
            'detail': detail,
            'category': category or '',
            'capability_id': capability.stable_id if capability else '',
            'capability_title': capability.title if capability else '',
            'track': track or (capability.track if capability else ''),
        })

    def add_task_item(*, category, capability, task, reason_code, reason_text, evidence_refs=None):
        if capability.stable_id in seen_capabilities or task.task_key in seen_tasks:
            return
        seen_capabilities.add(capability.stable_id)
        seen_tasks.add(task.task_key)
        items.append({
            'type': 'task',
            'category': category,
            'category_label': constants.RECOMMENDATION_CATEGORY_LABELS[category],
            'capability_id': capability.stable_id,
            'capability_title': capability.title,
            'dimension': capability.dimension,
            'knowledge_point_ids': sorted(point.stable_id for point in capability.knowledge_points.all()),
            'task': _task_payload(task),
            'reason': {
                'code': reason_code,
                'text': reason_text,
                'evidence_refs': list(evidence_refs or []),
                'rule_version': snapshot['rule_version'],
            },
        })

    # 0. Teacher assignment wins, but only if the task is still usable.
    for adjustment in adjustments:
        if adjustment.action != 'assign_task' or not adjustment.task_id:
            continue
        task = adjustment.task
        if (
            task.status != constants.TASK_STATUS_FROZEN
            or task.requires_milestone_i
            or not task.environment_available
            or task.materials_withdrawn
            or task.task_key in attempted
        ):
            add_gap(
                'teacher_task_unavailable',
                f'教师指定任务 {task.task_key} 当前不可用，需教师重新确认。',
                category='teacher_assigned',
                track=task.track,
            )
            continue
        capability = task.capabilities.order_by('course_order', 'stable_id').first()
        if not capability:
            continue
        if capability.stable_id in seen_capabilities or task.task_key in seen_tasks:
            continue
        seen_capabilities.add(capability.stable_id)
        seen_tasks.add(task.task_key)
        items.append({
            'type': 'task',
            'category': 'teacher_assigned',
            'category_label': constants.RECOMMENDATION_CATEGORY_LABELS['teacher_assigned'],
            'capability_id': capability.stable_id,
            'capability_title': capability.title,
            'dimension': capability.dimension,
            'knowledge_point_ids': sorted(point.stable_id for point in capability.knowledge_points.all()),
            'task': _task_payload(task),
            'adjustment_id': adjustment.id,
            'reason': {
                'code': 'teacher_assigned',
                'text': f'教师指定任务：{adjustment.rationale}',
                'evidence_refs': [],
                'rule_version': snapshot['rule_version'],
            },
        })

    # 1. Basic diagnosis when a track has no evidence and no completed diagnosis.
    for track in (constants.TRACK_DATA, constants.TRACK_NETWORK):
        if track not in scope_tracks:
            continue
        track_caps = [capability for capability in open_capabilities if capability.track == track]
        if not track_caps:
            continue
        has_facts = any(fact.capability.track == track for fact in facts)
        if track in diagnosed_tracks or has_facts:
            continue
        diagnosis_questions_exist = catalog.diagnostic_questions.filter(
            track=track, status__in=('frozen', 'reviewed', 'draft'),
        ).exists()
        items.append({
            'type': 'diagnostic',
            'category': 'diagnosis',
            'category_label': '基础诊断',
            'track': track,
            'track_label': constants.TRACK_LABELS[track],
            'capability_id': '',
            'capability_title': '',
            'task': None,
            'reason': {
                'code': 'no_evidence_start_with_diagnosis' if diagnosis_questions_exist else 'diagnosis_pool_empty',
                'text': (
                    '尚无核验证据，先完成基础诊断，再安排任务。'
                    if diagnosis_questions_exist else
                    '尚无核验证据，且该主线诊断题池为空，需课程负责人补题。'
                ),
                'evidence_refs': [],
                'rule_version': snapshot['rule_version'],
            },
        })

    # 2. Due retests.
    for capability in open_capabilities:
        state = states.get(capability.stable_id)
        if not state or state.state != constants.STATE_RETEST_PENDING:
            continue
        original_task_keys = {
            fact.task.task_key for fact in facts_by_capability.get(capability.stable_id, [])
            if fact.task_id
        }
        task = _select_task(
            capability=capability,
            purposes=[constants.PURPOSE_RETEST],
            satisfied=satisfied,
            attempted=attempted,
            catalog=catalog,
            exclude_keys=original_task_keys,
        )
        if not task:
            add_gap(
                'retest_pool_empty',
                f'{capability.stable_id} 复测题池没有可用的新场景任务，需教师补题。',
                capability=capability,
                category='due_retest',
            )
            continue
        add_task_item(
            category='due_retest',
            capability=capability,
            task=task,
            reason_code='retest_due',
            reason_text='受助通过后的新场景复测已到期，需无提示完成。',
            evidence_refs=[state.evidence_ref] if state.evidence_ref else [],
        )

    # 3. Missing prerequisites for capabilities in the current goal.
    for goal_capability in open_capabilities:
        if goal_capability.stable_id in seen_capabilities:
            continue
        state = states.get(goal_capability.stable_id)
        if state and state.state == constants.STATE_INDEPENDENT:
            continue
        for prerequisite in goal_capability.prerequisites.all().order_by('course_order', 'stable_id'):
            if prerequisite.stable_id in satisfied:
                continue
            if prerequisite.stable_id in seen_capabilities:
                continue
            if prerequisite.status != constants.CAPABILITY_STATUS_OPEN:
                add_gap(
                    'prerequisite_not_open',
                    f'目标能力 {goal_capability.stable_id} 的先修 {prerequisite.stable_id} 尚未开放，暂不能推荐。',
                    capability=prerequisite,
                    category='prerequisite',
                )
                continue
            task = _select_task(
                capability=prerequisite,
                purposes=[
                    constants.PURPOSE_PRACTICE,
                    constants.PURPOSE_VERIFICATION,
                    constants.PURPOSE_NEW_CAPABILITY,
                ],
                satisfied=satisfied,
                attempted=attempted,
                catalog=catalog,
            )
            if not task:
                add_gap(
                    'prerequisite_task_missing',
                    f'先修能力 {prerequisite.stable_id} 没有可用任务，需课程补充。',
                    capability=prerequisite,
                    category='prerequisite',
                )
                continue
            prereq_state = states.get(prerequisite.stable_id)
            add_task_item(
                category='prerequisite',
                capability=prerequisite,
                task=task,
                reason_code='prerequisite_missing',
                reason_text=f'目标能力 {goal_capability.stable_id} 的先修 {prerequisite.stable_id} 尚未取得独立证据。',
                evidence_refs=[prereq_state.evidence_ref] if prereq_state and prereq_state.evidence_ref else [],
            )

    # 4. Practice after a failed verification.
    for capability in open_capabilities:
        state = states.get(capability.stable_id)
        if not state or state.state != constants.STATE_NEEDS_PRACTICE:
            continue
        task = _select_task(
            capability=capability,
            purposes=[constants.PURPOSE_PRACTICE, constants.PURPOSE_VERIFICATION],
            satisfied=satisfied,
            attempted=attempted,
            catalog=catalog,
        )
        if not task:
            add_gap(
                'no_task_for_capability',
                f'{capability.stable_id} 未通过后没有可用练习任务。',
                capability=capability,
                category='practice',
            )
            continue
        add_task_item(
            category='practice',
            capability=capability,
            task=task,
            reason_code='verification_not_passed',
            reason_text='最近核验未通过，按已确认错因练习同知识点任务。',
            evidence_refs=[state.evidence_ref] if state.evidence_ref else [],
        )

    # 5. Consolidation after an assisted pass.
    for capability in open_capabilities:
        state = states.get(capability.stable_id)
        if not state or state.state != constants.STATE_ASSISTED_PASS:
            continue
        task = _select_task(
            capability=capability,
            purposes=[constants.PURPOSE_CONSOLIDATION, constants.PURPOSE_VERIFICATION],
            satisfied=satisfied,
            attempted=attempted,
            catalog=catalog,
        )
        if not task:
            add_gap(
                'no_consolidation_task',
                f'{capability.stable_id} 受助通过后没有巩固任务，需课程补充。',
                capability=capability,
                category='consolidation',
            )
            continue
        add_task_item(
            category='consolidation',
            capability=capability,
            task=task,
            reason_code='assisted_pass_consolidation',
            reason_text='受助通过不直接视为独立掌握，先完成巩固，再按到期日做无提示复测。',
            evidence_refs=[state.evidence_ref] if state.evidence_ref else [],
        )

    # 6. New capability tasks, only after a diagnosis (or existing track evidence).
    fact_tracks = {fact.capability.track for fact in facts}
    for capability in open_capabilities:
        if capability.stable_id in seen_capabilities:
            continue
        state = states.get(capability.stable_id)
        if state and state.state in (
            constants.STATE_INDEPENDENT,
            constants.STATE_NEEDS_PRACTICE,
            constants.STATE_ASSISTED_PASS,
            constants.STATE_RETEST_PENDING,
            constants.STATE_PENDING_REVIEW,
            constants.STATE_PENDING_VERIFICATION,
            constants.STATE_ENVIRONMENT_AFFECTED,
            constants.STATE_UNKNOWN,
        ):
            continue
        track_ready = capability.track in diagnosed_tracks or capability.track in fact_tracks
        if not track_ready:
            continue
        unmet = [
            prerequisite for prerequisite in capability.prerequisites.all()
            if prerequisite.stable_id not in satisfied
        ]
        if unmet:
            continue
        task = _select_task(
            capability=capability,
            purposes=[
                constants.PURPOSE_NEW_CAPABILITY,
                constants.PURPOSE_VERIFICATION,
                constants.PURPOSE_PRACTICE,
            ],
            satisfied=satisfied,
            attempted=attempted,
            catalog=catalog,
        )
        if not task:
            add_gap(
                'no_task_for_capability',
                f'{capability.stable_id} 没有可用新能力任务。',
                capability=capability,
                category='new_capability',
            )
            continue
        diagnosis_result = state.diagnosis_result if state else constants.DIAGNOSIS_UNKNOWN
        if diagnosis_result == constants.DIAGNOSIS_NEEDS_LEARNING:
            reason_code = 'diagnosis_suggests_learning'
            reason_text = '诊断显示该能力需要学习，先完成基础练习。'
        else:
            reason_code = 'new_capability_ready'
            reason_text = '先修已满足，可进入该能力的审核任务。'
        add_task_item(
            category='new_capability',
            capability=capability,
            task=task,
            reason_code=reason_code,
            reason_text=reason_text,
            evidence_refs=(
                [state.evidence_ref] if state and state.evidence_ref else []
            ),
        )

    # A completely empty track deserves an explicit gap, not silence.
    for track in sorted(scope_tracks):
        track_caps = [capability for capability in open_capabilities if capability.track == track]
        if not track_caps:
            continue
        track_cap_ids = {capability.stable_id for capability in track_caps}
        has_candidate_task = any(
            task.is_recommendable
            and task.purpose != constants.PURPOSE_RETEST
            and set(cap.stable_id for cap in task.capabilities.all()) & track_cap_ids
            for task in tasks
        )
        if not has_candidate_task:
            add_gap(
                'task_pool_empty',
                f'{constants.TRACK_LABELS[track]} 主线没有可推荐的已冻结任务。',
                category='new_capability',
                track=track,
            )

    category_rank = {name: index for index, name in enumerate(constants.RECOMMENDATION_CATEGORY_ORDER)}
    items.sort(key=lambda item: (
        0 if item['category'] == 'teacher_assigned' else 1,
        category_rank.get(item['category'], 99),
        item['task']['course_order'] if item.get('task') else 0,
        item.get('capability_id') or '',
        item['task']['task_key'] if item.get('task') else '',
        item.get('track', ''),
    ))
    for index, item in enumerate(items, start=1):
        item['priority'] = index
    deduped_gaps = []
    seen_gaps = set()
    for gap in gaps:
        key = (gap['code'], gap['capability_id'], gap['track'], gap['detail'])
        if key in seen_gaps:
            continue
        seen_gaps.add(key)
        deduped_gaps.append(gap)
    gaps = deduped_gaps
    gaps.sort(key=lambda gap: (category_rank.get(gap['category'], 99), gap['capability_id'], gap['code']))

    output = {
        'catalog_version': catalog.version,
        'rule_version': snapshot['rule_version'],
        'goal_track': goal_track,
        'core_requires_ai': False,
        'ai_used': False,
        'items': items,
        'gaps': gaps,
        'counts': {
            'items': len(items),
            'tasks': sum(1 for item in items if item['type'] == 'task'),
            'diagnostics': sum(1 for item in items if item['type'] == 'diagnostic'),
            'gaps': len(gaps),
        },
    }

    run = RecommendationRun.objects.create(
        student=student,
        catalog=catalog,
        goal_track=goal_track,
        rule_version=snapshot['rule_version'],
        inputs_hash=inputs_hash,
        input_snapshot=snapshot,
        output=output,
        ai_used=False,
    )

    emit_event(
        user=student,
        event_type='recommendation_issued',
        event_id=f'lm-rec-{run.id}',
        catalog=catalog,
        capability_ids=[item.get('capability_id') for item in items if item.get('capability_id')],
        extra={
            'run_id': run.id,
            'goal_track': goal_track,
            'rule_version': snapshot['rule_version'],
            'inputs_hash': inputs_hash,
            'ai_used': False,
        },
    )
    return run


def _display_version(version):
    cleaned = (version or '').replace('-candidate', '').strip('-')
    return cleaned or version


def student_recommendation_view(run):
    """Teaching-facing recommendation payload.

    Internal task keys, rule slugs, input hashes, capability IDs and gap codes
    stay in the stored run / teacher endpoint.
    """

    items = []
    for item in run.output.get('items', []):
        if item.get('type') == 'diagnostic':
            items.append({
                'kind': 'diagnosis',
                'category_label': item.get('category_label', '基础诊断'),
                'track_label': item.get('track_label', ''),
                'reason_text': item.get('reason', {}).get('text', ''),
                'priority': item.get('priority'),
            })
        else:
            task = item.get('task') or {}
            items.append({
                'kind': 'task',
                'category_label': item.get('category_label', ''),
                'task': {
                    'id': task.get('id'),
                    'title': task.get('title', ''),
                    'version_label': _display_version(task.get('version', '')),
                    'purpose_label': task.get('purpose_label', ''),
                },
                'reason_text': item.get('reason', {}).get('text', ''),
                'priority': item.get('priority'),
            })
    return {
        'generated_at': run.created_at.isoformat(),
        'goal_track': run.goal_track,
        'items': items,
        'counts': {'items': len(items)},
        'notice': None if items else '当前暂无可推荐任务，课程或教师正在补充材料。',
    }
