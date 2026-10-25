"""Read models for the capability map page.

Students get a teaching-facing payload: no internal reason codes, evidence
references, task keys, rule slugs or legacy-mapping audit fields.  Teachers get
the full audit payload.  A capability without evidence is ``待诊断``; a
dimension that has no open capability is ``未开展``.  Neither is turned into a
low score.
"""

import re

from . import pathing
from .. import constants
from ..models import VerificationFact


def _state_payload(state):
    if state is None:
        return {
            'state': constants.STATE_NEEDS_DIAGNOSIS,
            'state_label': constants.STATE_LABELS[constants.STATE_NEEDS_DIAGNOSIS],
            'diagnosis_result': constants.DIAGNOSIS_UNKNOWN,
            'reason_code': '',
            'retest_due_at': None,
            'evidence_ref': '',
            'updated_at': None,
        }
    return {
        'state': state.state,
        'state_label': constants.STATE_LABELS.get(state.state, state.state),
        'diagnosis_result': state.diagnosis_result,
        'reason_code': state.reason_code,
        'retest_due_at': state.retest_due_at.isoformat() if state.retest_due_at else None,
        'evidence_ref': state.evidence_ref,
        'updated_at': state.updated_at.isoformat() if state.updated_at else None,
    }


def _dimension_summary(capabilities, include_counts=True, internal_states=None):
    summary = {}
    internal_states = internal_states or {}
    for dimension in constants.DIMENSION_ORDER:
        dimension_capabilities = [cap for cap in capabilities if cap['dimension'] == dimension]
        states = [
            internal_states.get(cap['title'], constants.STATE_NEEDS_DIAGNOSIS)
            for cap in dimension_capabilities
        ]
        counts = {}
        for state in states:
            counts[state] = counts.get(state, 0) + 1
        if not dimension_capabilities:
            display = constants.STATE_NOT_ATTEMPTED
        elif any(state == constants.STATE_NEEDS_PRACTICE for state in states):
            display = constants.STATE_NEEDS_PRACTICE
        elif any(state == constants.STATE_ASSISTED_PASS for state in states):
            display = constants.STATE_ASSISTED_PASS
        elif any(state == constants.STATE_INDEPENDENT for state in states):
            display = constants.STATE_INDEPENDENT
        elif any(state == constants.STATE_NEEDS_DIAGNOSIS for state in states):
            display = constants.STATE_NEEDS_DIAGNOSIS
        else:
            display = constants.STATE_NOT_ATTEMPTED
        entry = {
            'dimension': dimension,
            'label': constants.DIMENSION_LABELS[dimension],
            'display_state': display,
            'display_label': constants.STATE_LABELS.get(display, display),
            'tone': constants.STATE_TONES.get(display, 'neutral'),
            'capability_count': len(dimension_capabilities),
        }
        if include_counts:
            entry['counts'] = counts
        summary[dimension] = entry
    return [summary[dimension] for dimension in constants.DIMENSION_ORDER]


def _student_evidence(capability_facts):
    if not capability_facts:
        return {'fact_count': 0, 'latest': None}
    latest = capability_facts[0]
    return {
        'fact_count': len(capability_facts),
        'latest': {
            'outcome_label': dict(constants.OUTCOME_CHOICES).get(latest.outcome, '已记录'),
            'assisted': latest.independence == constants.INDEPENDENCE_ASSISTED,
            'occurred_at': latest.occurred_at.isoformat(),
            'task_title': latest.task.title if latest.task else '',
        },
    }


def _student_capability_payload(*, capability, state, evidence, prerequisites):
    return {
        'title': capability.title,
        'observable_objective': capability.observable_objective,
        'dimension': capability.dimension,
        'dimension_label': constants.DIMENSION_LABELS[capability.dimension],
        'difficulty': capability.difficulty,
        'availability_label': (
            '已开放' if capability.status == constants.CAPABILITY_STATUS_OPEN else '暂未开放'
        ),
        'knowledge_points': [{'name': point.name} for point in capability.knowledge_points.all()],
        'prerequisites': prerequisites,
        'state_label': state['state_label'],
        'tone': constants.STATE_TONES.get(state['state'], 'neutral'),
        'retest_due_at': state['retest_due_at'],
        'evidence': evidence,
    }


def _student_prerequisites(capability, states):
    result = []
    for prerequisite in capability.prerequisites.all():
        state = states.get(prerequisite.id)
        state_value = state.state if state else constants.STATE_NEEDS_DIAGNOSIS
        result.append({
            'title': prerequisite.title,
            'state_label': constants.STATE_LABELS.get(state_value, state_value),
            'tone': constants.STATE_TONES.get(state_value, 'muted'),
        })
    return result


def _teacher_capability_payload(*, capability, state_payload, evidence, prerequisites):
    return {
        'capability_id': capability.stable_id,
        'title': capability.title,
        'observable_objective': capability.observable_objective,
        'dimension': capability.dimension,
        'dimension_label': constants.DIMENSION_LABELS[capability.dimension],
        'difficulty': capability.difficulty,
        'status': capability.status,
        'status_label': constants.CAPABILITY_STATUS_LABELS[capability.status],
        'course_order': capability.course_order,
        'knowledge_points': [
            {'knowledge_point_id': point.stable_id, 'name': point.name}
            for point in capability.knowledge_points.all()
        ],
        'prerequisites': prerequisites,
        **state_payload,
        'evidence': evidence,
    }


def build_capability_map(*, student, catalog, goal_track=None, audience='student'):
    scope = (
        {constants.TRACK_DATA, constants.TRACK_NETWORK}
        if goal_track in (None, '', constants.TRACK_BOTH) else {goal_track}
    )
    states = pathing.state_for_student(student, catalog)
    facts = (
        VerificationFact.objects.filter(student=student, catalog=catalog)
        .select_related('capability', 'task')
        .order_by('-occurred_at')
    )
    facts_by_capability = {}
    for fact in facts:
        facts_by_capability.setdefault(fact.capability.stable_id, []).append(fact)

    is_student = audience == 'student'
    tracks = []
    state_counts = {}

    for track in (constants.TRACK_DATA, constants.TRACK_NETWORK):
        if track not in scope:
            continue
        capabilities = list(
            catalog.capabilities.filter(track=track)
            .prefetch_related('knowledge_points', 'prerequisites')
            .order_by('course_order', 'stable_id')
        )
        capability_payloads = []
        for capability in capabilities:
            state = states.get(capability.id)
            state_payload = _state_payload(state)
            if capability.status != constants.CAPABILITY_STATUS_OPEN:
                state_payload.update({
                    'state': constants.STATE_NOT_ATTEMPTED,
                    'state_label': constants.STATE_LABELS[constants.STATE_NOT_ATTEMPTED],
                    'reason_code': capability.status,
                })
            state_counts[state_payload['state']] = state_counts.get(state_payload['state'], 0) + 1
            capability_facts = facts_by_capability.get(capability.stable_id, [])

            if is_student:
                capability_payloads.append(_student_capability_payload(
                    capability=capability,
                    state=state_payload,
                    evidence=_student_evidence(capability_facts),
                    prerequisites=_student_prerequisites(capability, states),
                ))
            else:
                evidence = {
                    'fact_count': len(capability_facts),
                    'latest': None,
                    'outcomes': {},
                }
                for fact in capability_facts:
                    evidence['outcomes'][fact.outcome] = evidence['outcomes'].get(fact.outcome, 0) + 1
                if capability_facts:
                    latest = capability_facts[0]
                    evidence['latest'] = {
                        'fact_id': latest.fact_id,
                        'outcome': latest.outcome,
                        'independence': latest.independence,
                        'assistance_level': latest.assistance_level,
                        'assistance_source': latest.assistance_source,
                        'assistance_shown': latest.assistance_shown,
                        'evidence_ref': latest.evidence_ref,
                        'verifier_version': latest.verifier_version,
                        'occurred_at': latest.occurred_at.isoformat(),
                        'task_key': latest.task.task_key if latest.task else '',
                        'task_version': latest.task_version,
                    }
                prerequisites = [
                    {
                        'capability_id': prerequisite.stable_id,
                        'title': prerequisite.title,
                        'state': (
                            states[prerequisite.id].state if prerequisite.id in states
                            else constants.STATE_NEEDS_DIAGNOSIS
                        ),
                        'state_label': constants.STATE_LABELS.get(
                            states[prerequisite.id].state
                            if prerequisite.id in states else constants.STATE_NEEDS_DIAGNOSIS,
                        ),
                    }
                    for prerequisite in capability.prerequisites.all()
                ]
                capability_payloads.append(_teacher_capability_payload(
                    capability=capability,
                    state_payload=state_payload,
                    evidence=evidence,
                    prerequisites=prerequisites,
                ))

        tracks.append({
            'track': track,
            'label': constants.TRACK_LABELS[track],
            'capabilities': capability_payloads,
            'dimensions': _dimension_summary(
                capability_payloads,
                include_counts=not is_student,
                internal_states={
                    capability.title: (
                        constants.STATE_NOT_ATTEMPTED
                        if capability.status != constants.CAPABILITY_STATUS_OPEN
                        else _state_payload(states.get(capability.id))['state']
                    )
                    for capability in capabilities
                },
            ),
        })

    if is_student:
        catalog_payload = {
            'version_label': (catalog.version or '').replace('-candidate', '').strip('-') or catalog.version,
            'label': re.sub(r'（[^）]*）', '', catalog.label).strip() or catalog.label,
            'status_label': (
                '已发布' if catalog.status == constants.CATALOG_STATUS_PUBLISHED else '预览（未发布）'
            ),
            'is_published': catalog.status == constants.CATALOG_STATUS_PUBLISHED,
            'updated_at': catalog.updated_at.isoformat() if catalog.updated_at else None,
        }
        summary = {
            'open_capabilities': catalog.capabilities.filter(
                status=constants.CAPABILITY_STATUS_OPEN,
            ).count(),
            'independent_count': state_counts.get(constants.STATE_INDEPENDENT, 0),
            'assisted_count': (
                state_counts.get(constants.STATE_ASSISTED_PASS, 0)
                + state_counts.get(constants.STATE_RETEST_PENDING, 0)
            ),
            'needs_practice_count': state_counts.get(constants.STATE_NEEDS_PRACTICE, 0),
        }
        versions = {
            'catalog_version_label': (
                (catalog.version or '').replace('-candidate', '').strip('-') or catalog.version
            ),
            'updated_at': catalog.updated_at.isoformat() if catalog.updated_at else None,
            'data_source_label': '平台核验记录',
        }
    else:
        catalog_payload = {
            'version': catalog.version,
            'label': catalog.label,
            'status': catalog.status,
            'status_label': catalog.get_status_display(),
            'rule_version': catalog.rule_version,
            'published_at': catalog.published_at.isoformat() if catalog.published_at else None,
        }
        legacy_counts = {'mapped': 0, 'proposed': 0, 'unmapped': 0, 'split': 0}
        for mapping in catalog.legacy_mappings.all():
            legacy_counts[mapping.mapping_status] = legacy_counts.get(mapping.mapping_status, 0) + 1
        summary = {
            'legacy_mappings': legacy_counts,
            'unmapped_excluded_from_capability_totals': True,
            'open_capabilities': catalog.capabilities.filter(
                status=constants.CAPABILITY_STATUS_OPEN,
            ).count(),
        }
        versions = {
            'catalog_version': catalog.version,
            'rule_version': catalog.rule_version,
            'task_versions': sorted({
                f'{task.task_key}@{task.version}' for task in catalog.tasks.all()
            }),
        }

    return {
        'catalog': catalog_payload,
        'student': (
            {'username': student.username} if is_student
            else {'id': student.id, 'username': student.username}
        ),
        'tracks': tracks,
        'summary': summary,
        'versions': versions,
    }
