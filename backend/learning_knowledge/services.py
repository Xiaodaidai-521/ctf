"""Static/lexical teaching retrieval. No embedding, reranker or generator calls."""
import re
from urllib.parse import urlsplit

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from .models import Evidence, EvidenceIssue, MaterialChunk, TaskMaterial
from .policy import POLICY_VERSION, Scope, authorize, digest, live_attempt, unavailable

SOURCE_DOMAINS = {'www.npc.gov.cn', 'openstd.samr.gov.cn', 'wstg.owasp.org', 'owasp.org', 'creativecommons.org'}


def safe_source_url(value):
    try:
        url = urlsplit(value)
        if url.scheme == 'https' and url.hostname in SOURCE_DOMAINS and not url.username and not url.password and url.port in (None, 443):
            return value
    except ValueError:
        pass
    return ''


def chunk_text(chunk, revision):
    text = revision.source_snapshot[chunk.start:chunk.end]
    if chunk.start >= chunk.end or chunk.end > len(revision.source_snapshot) or digest(text) != chunk.chunk_hash:
        raise unavailable()
    return text


def evidence_payload(evidence, user):
    scope = Scope(user, evidence.attempt.attempt_id, evidence.purpose)
    decision = authorize(evidence.chunk.revision_id, scope)
    if not decision:
        raise unavailable()
    revision, attempt = decision
    if (evidence.student_id != user.pk or evidence.acl_version != revision.material.acl_version
            or evidence.policy_version != POLICY_VERSION):
        raise unavailable()
    chunk = MaterialChunk.objects.get(pk=evidence.chunk_id)
    text = chunk_text(chunk, revision)
    binding = TaskMaterial.objects.get(task=attempt.task, revision=revision)
    return {
        'evidence_id': str(evidence.evidence_id),
        'material_id': str(revision.material.material_id),
        'material_revision': revision.revision,
        'chunk_ref': str(chunk.pk),
        'permission_decision_ref': str(evidence.decision_ref),
        'issued_at': evidence.issued_at.isoformat(),
        'title': revision.title,
        'source_kind': revision.material.source_type,
        'source_ref': f'm3-source:{revision.pk}',
        'source_url': safe_source_url(revision.source_url),
        'source_version': revision.source_version,
        'publisher': revision.publisher,
        'license_id': revision.license_id,
        'attribution_text': revision.attribution_text,
        'applicability': revision.applicability,
        'locator': chunk.locator,
        'location_status': 'located' if chunk.locator else 'unlocated',
        'location_notice': '' if chunk.locator else '定位待人工补齐',
        'excerpt': text[:360],
        'knowledge_point_ids': binding.knowledge_point_ids,
        'catalog_version': attempt.catalog.version,
        'view_endpoint': f'/api/learning-knowledge/evidence/{evidence.evidence_id}/',
    }


def read_evidence(evidence_id, user):
    try:
        evidence = Evidence.objects.select_related('attempt', 'chunk').get(evidence_id=evidence_id, student=user)
    except (Evidence.DoesNotExist, ValueError, TypeError):
        raise unavailable()
    return evidence_payload(evidence, user)


def _tokens(query):
    return set(re.findall(r'[a-z0-9_]+|[一-鿿]{2}', query.lower()))


def search(scope, query='', request_id='', knowledge_point_ids=None):
    attempt = live_attempt(scope)
    # This public purpose is deliberately not a hint retrieval bypass.
    if scope.purpose != 'lesson':
        raise unavailable()
    bindings = TaskMaterial.objects.filter(task=attempt.task).select_related('revision__material')
    if knowledge_point_ids is not None:
        requested = set(knowledge_point_ids)
        bindings = [item for item in bindings if requested.intersection(item.knowledge_point_ids)]
    revisions = []
    stale = False
    for binding in bindings:
        decision = authorize(binding.revision_id, scope)
        if decision:
            revisions.append(decision[0])
        elif authorize(binding.revision_id, scope, allow_stale=True):
            stale = True
    stamp = '|'.join(f'{r.pk}:{r.material.acl_version}:{r.source_hash}' for r in revisions)
    key = 'm3-candidates:' + digest(f'{scope.user.pk}:{attempt.attempt_id}:{scope.purpose}:{scope.hint_level}:{POLICY_VERSION}:{stamp}:{query}')
    candidate_ids = cache.get(key)
    if candidate_ids is None:
        tokens = _tokens(query)
        ranked = []
        for revision in revisions:
            for chunk in revision.chunks.all():
                try:
                    text = chunk_text(chunk, revision)
                except NotFound:
                    continue
                score = sum(token in (revision.title + ' ' + text).lower() for token in tokens)
                if not query.strip() or score:
                    ranked.append((score, chunk.pk))
        candidate_ids = [pk for _, pk in sorted(ranked, key=lambda row: (-row[0], row[1]))[:12]]
        cache.set(key, candidate_ids, 300)  # IDs only; never authority and never source text.
    results, groups = [], set()
    if not isinstance(candidate_ids, list) or any(type(pk) is not int for pk in candidate_ids):
        candidate_ids = []
    chunks = MaterialChunk.objects.filter(pk__in=candidate_ids, revision_id__in=[r.pk for r in revisions]).in_bulk()
    for pk in candidate_ids:
        chunk = chunks.get(pk)
        if not chunk:
            continue
        decision = authorize(chunk.revision_id, scope)
        if not decision:
            continue
        revision, attempt = decision
        evidence, _ = Evidence.objects.get_or_create(
            student=scope.user, attempt=attempt, chunk=chunk,
            acl_version=revision.material.acl_version, purpose=scope.purpose,
            defaults={'policy_version': POLICY_VERSION},
        )
        try:
            results.append(evidence_payload(evidence, scope.user))
        except NotFound:
            continue
        if revision.conflict_group:
            groups.add(revision.conflict_group)
    status = 'sufficient' if results else ('stale' if stale else 'insufficient')
    if groups:
        status = 'conflict'
    elif any(item['location_status'] == 'unlocated' for item in results):
        status = 'unlocated'
    return {
        'request_id': request_id,
        'mode': 'lexical' if query.strip() else 'static',
        'results': results,
        'evidence_status': status,
        'notice': '当前授权材料不足，可继续提交或请求教师补查。' if not results else '证据仅支持其适用范围，不等于合规或正确性结论。',
    }


def verify_claim(*, user, evidence_ids, claim):
    """Citation existence does not entail a claim. Phase 1 never certifies model inference."""
    try:
        cards = [read_evidence(value, user) for value in evidence_ids]
    except Exception:
        return {'status': 'needs_review', 'supported': False, 'evidence_ids': []}
    return {'status': 'needs_review', 'supported': False, 'evidence_ids': [card['evidence_id'] for card in cards]}


def report_issue(*, scope, reason, request_id, evidence_id=None):
    from feedback_center import constants
    from feedback_center.services.submission import create_feedback

    if reason not in {'insufficient', 'conflict', 'stale', 'unlocated', 'material_error'}:
        raise unavailable()
    with transaction.atomic():
        attempt = live_attempt(scope)
        # Serialize same-attempt check+create on PostgreSQL, including the no-evidence case.
        type(attempt).objects.select_for_update().get(pk=attempt.pk)
        revision = None
        if evidence_id:
            read_evidence(evidence_id, scope.user)
            evidence = Evidence.objects.get(evidence_id=evidence_id, student=scope.user)
            if evidence.attempt_id != attempt.pk:
                raise unavailable()
            revision = evidence.chunk.revision
        existing = EvidenceIssue.objects.select_related('ticket').filter(
            attempt=attempt, revision=revision, reason=reason,
        ).exclude(ticket__status__in=[constants.STATUS_HANDLED, constants.STATUS_REJECTED]).first()
        if existing:
            return {'feedback_id': str(existing.ticket.feedback_id), 'created': False}
        generation = EvidenceIssue.objects.filter(attempt=attempt, revision=revision, reason=reason).count()
        ref = f'm3-source:{revision.pk}' if revision else f'm3-task:{attempt.task_id}'
        result = create_feedback(scope.user, {
            'attempt_id': str(attempt.attempt_id),
            'category': constants.CATEGORY_TEACHING,
            'issue_type': 'material_issue',
            'client_request_id': request_id,
            # Include the closed cycle so module 7 does not attach a new report to a closed ticket.
            'dispute': f'{reason}:{ref}:cycle:{generation}',
            'reason': '模块三受控材料补查，不自动更正成绩或来源。',
            'original_decision_ref': ref,
            'original_decision_version': str(revision.revision) if revision else attempt.task_version,
            'evidence': [],
        })
        EvidenceIssue.objects.get_or_create(ticket=result.ticket, defaults={'attempt': attempt, 'revision': revision, 'reason': reason})
        return {'feedback_id': str(result.ticket.feedback_id), 'created': result.created}
