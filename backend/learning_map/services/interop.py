"""Standards adapters reused by module 1.

Two external standards are used as exchange formats only; neither adds a
runtime service or a second event store:

* 1EdTech CASE v1.1 CFPackage — capability catalog export.  The official JSON
  schema is vendored at ``fixtures/case-v1p1-cfpackage.schema.json`` (from
  https://github.com/1EdTech/OpenCASE, Apache-2.0) and used by tests.
* xAPI 1.0.3 statement — verification evidence export for a future LRS.

The local database remains the source of truth.
"""

import uuid
from datetime import datetime, timezone as dt_timezone

from django.conf import settings

from .. import constants
from ..models import Capability, KnowledgePoint, VerificationFact


CASE_SCHEMA_VERSION = '1.1'


def _base_uri():
    return getattr(settings, 'LEARNING_MAP_BASE_URI', 'https://ctf.local/learning-map').rstrip('/')


def _identifier(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, '/'.join([_base_uri(), *[str(part) for part in parts]])))


def _uri(*parts):
    return f"{_base_uri()}/{'/'.join(str(part) for part in parts)}"


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(dt_timezone.utc).isoformat().replace('+00:00', 'Z')
    return str(value)


def _last_change(catalog):
    stamp = catalog.updated_at or catalog.created_at
    return _iso(stamp)


def export_case_package(catalog):
    """Build a CASE v1.1 CFPackage for the catalog.

    Capabilities and knowledge points become CFItems.  Prerequisites become
    ``precedes`` associations (origin must come before destination), and
    knowledge points are ``isChildOf`` their capabilities.
    """

    base = _base_uri()
    document_identifier = _identifier('case', 'document', catalog.version)
    document_uri = _uri('case', catalog.version)
    package_uri = {'title': f'{catalog.label}', 'identifier': document_identifier, 'uri': document_uri}
    last_change = _last_change(catalog)

    items = []
    item_uris = {}
    for capability in catalog.capabilities.prefetch_related('knowledge_points', 'prerequisites').order_by('course_order', 'stable_id'):
        item_identifier = _identifier('case', 'item', catalog.version, capability.stable_id)
        item_uri = _uri('case', catalog.version, 'item', capability.stable_id)
        item_uris[('capability', capability.stable_id)] = item_uri
        items.append({
            'identifier': item_identifier,
            'uri': item_uri,
            'fullStatement': f'{capability.title}：{capability.observable_objective}',
            'humanCodingScheme': capability.stable_id,
            'CFItemType': 'Competency',
            'lastChangeDateTime': last_change,
            'extensions': {
                'lm:track': capability.track,
                'lm:dimension': capability.dimension,
                'lm:difficulty': capability.difficulty,
                'lm:status': capability.status,
                'lm:open': capability.is_open,
                'lm:catalogVersion': catalog.version,
            },
        })
        for point in capability.knowledge_points.all().order_by('sort_order', 'stable_id'):
            key = ('knowledge_point', point.stable_id)
            if key in item_uris:
                continue
            point_identifier = _identifier('case', 'item', catalog.version, point.stable_id)
            point_uri = _uri('case', catalog.version, 'item', point.stable_id)
            item_uris[key] = point_uri
            items.append({
                'identifier': point_identifier,
                'uri': point_uri,
                'fullStatement': point.name,
                'humanCodingScheme': point.stable_id,
                'CFItemType': 'KnowledgePoint',
                'lastChangeDateTime': last_change,
                'extensions': {
                    'lm:track': point.track,
                    'lm:parentCapability': capability.stable_id,
                    'lm:catalogVersion': catalog.version,
                },
            })

    associations = []

    def add_association(association_type, origin_uri, destination_uri, note=''):
        associations.append({
            'identifier': _identifier(
                'case', 'association', catalog.version, association_type,
                origin_uri, destination_uri,
            ),
            'associationType': association_type,
            'uri': _uri(
                'case', catalog.version, 'association',
                _identifier(association_type, origin_uri, destination_uri),
            ),
            'originNodeURI': {'title': '', 'identifier': _identifier(origin_uri), 'uri': origin_uri},
            'destinationNodeURI': {'title': '', 'identifier': _identifier(destination_uri), 'uri': destination_uri},
            'lastChangeDateTime': last_change,
            'notes': note,
            'extensions': {'lm:catalogVersion': catalog.version},
        })

    for capability in catalog.capabilities.prefetch_related('knowledge_points', 'prerequisites'):
        capability_uri = item_uris[('capability', capability.stable_id)]
        for point in capability.knowledge_points.all():
            point_uri = item_uris.get(('knowledge_point', point.stable_id))
            if point_uri:
                add_association('isChildOf', point_uri, capability_uri, '知识点属于能力')
        for prerequisite in capability.prerequisites.all():
            prerequisite_uri = item_uris.get(('capability', prerequisite.stable_id))
            if prerequisite_uri:
                add_association('precedes', prerequisite_uri, capability_uri, '先修能力')

    return {
        'CFDocument': {
            'identifier': document_identifier,
            'uri': document_uri,
            'caseVersion': CASE_SCHEMA_VERSION,
            'creator': 'CTF Learning Platform',
            'publisher': 'CTF Learning Platform',
            'title': catalog.label,
            'description': f'双主线能力目录 {catalog.version}',
            'language': 'zh-CN',
            'version': catalog.version,
            'adoptionStatus': catalog.status,
            'lastChangeDateTime': last_change,
        },
        'CFItems': items,
        'CFAssociations': associations,
    }


def export_case_package_for_version(version):
    from .catalog import get_catalog
    return export_case_package(get_catalog(version=version, allow_candidate=True))


def _xapi_verb(fact):
    if fact.outcome == constants.OUTCOME_PASSED:
        return 'passed', {'en-US': 'passed', 'zh-CN': '通过'}
    if fact.outcome == constants.OUTCOME_FAILED:
        return 'failed', {'en-US': 'failed', 'zh-CN': '未通过'}
    if fact.outcome == constants.OUTCOME_ENVIRONMENT_AFFECTED:
        return 'experienced', {'en-US': 'experienced', 'zh-CN': '环境异常'}
    return 'completed', {'en-US': 'completed', 'zh-CN': '已处理'}


def export_xapi_statement(fact):
    """Map one verification fact to an xAPI 1.0.3 statement.

    The actor uses an internal account, never a real name/email.  No answer
    text, teacher key or credential is included.
    """

    verb_id, verb_display = _xapi_verb(fact)
    task_ref = (
        f'{fact.task.task_key}@{fact.task_version or fact.task.version}'
        if fact.task else
        f'capability:{fact.capability.stable_id}'
    )
    statement = {
        'id': str(uuid.uuid5(uuid.NAMESPACE_URL, f'{_base_uri()}/xapi/{fact.fact_id}')),
        'actor': {
            'objectType': 'Agent',
            'account': {
                'homePage': _base_uri(),
                'name': f'student-{fact.student_id}',
            },
        },
        'verb': {
            'id': f'http://adlnet.gov/expapi/verbs/{verb_id}',
            'display': verb_display,
        },
        'object': {
            'objectType': 'Activity',
            'id': _uri('xapi', 'task', task_ref),
            'definition': {
                'name': {'zh-CN': fact.task.title if fact.task else fact.capability.title},
                'type': 'http://adlnet.gov/expapi/activities/assessment',
            },
        },
        'result': {
            'success': fact.outcome == constants.OUTCOME_PASSED,
            'completion': fact.outcome not in (
                constants.OUTCOME_PENDING_REVIEW,
                constants.OUTCOME_VERIFICATION_FAILED,
            ),
        },
        'context': {
            'contextActivities': {
                'grouping': [
                    {'id': _uri('catalog', fact.catalog.version)},
                    {'id': _uri('capability', fact.capability.stable_id)},
                ],
            },
            'extensions': {
                'lm:catalogVersion': fact.catalog.version,
                'lm:capabilityId': fact.capability.stable_id,
                'lm:dimension': fact.dimension,
                'lm:independence': fact.independence,
                'lm:assistanceLevel': fact.assistance_level,
                'lm:assistanceSource': fact.assistance_source,
                'lm:assistanceShown': fact.assistance_shown,
                'lm:evidenceRef': fact.evidence_ref,
                'lm:verifierVersion': fact.verifier_version,
                'lm:outcome': fact.outcome,
            },
        },
        'timestamp': _iso(fact.occurred_at),
    }
    if fact.retest_of_attempt_id:
        statement['context']['extensions']['lm:retestOfAttemptId'] = str(fact.retest_of_attempt_id)
    return statement


def export_xapi_statements(student, catalog, limit=100):
    facts = VerificationFact.objects.filter(
        student=student, catalog=catalog,
    ).select_related('capability', 'task').order_by('-occurred_at')[:limit]
    return [export_xapi_statement(fact) for fact in facts]
