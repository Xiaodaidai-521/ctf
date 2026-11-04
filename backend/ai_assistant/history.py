"""Server-only readback provenance, not an ACL or a model citation parser.

New user bodies are direct user input (we cannot identify manually pasted text).
Assistant origins cover preparation plus the whole answer-chain dependency union,
including practice retrieval and earlier tutoring steps. Existing history replay
remains disabled. Legacy rows, opaque summaries/knowledge, unknown source kinds,
and malformed origins fail closed; no inference from timestamps or client flags.

Only bodies are restored. Stored metadata/display names are deliberately never
replayed: they have a different, historically unbounded provenance surface.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import json
from types import SimpleNamespace

from django.core import signing

_CURRENT = ContextVar('ai_history_origin', default=None)
_SALT = 'ai-assistant-history-v1'
REDACTED = '[历史内容未能验证材料权限，已隐藏]'
_RESOURCE_TYPES = {'resource', 'video', 'document', 'zip', 'report', 'course', 'textbook', 'ai_resource'}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _source_snapshot(kind, pk, user):
    """Reuse the actual detail API querysets (and evidence API), with no client filters.

    Do not implement a second status/role/grant policy here. Missing/deleted sources
    and failures are denied by callers. Fingerprints also invalidate edited sources.
    """
    if kind == 'evidence':
        from learning_knowledge.services import read_evidence
        return read_evidence(pk, user)
    from articles.views import ArticleViewSet
    from resources.views import ResourceDetailView
    from challenges.views import ChallengeViewSet
    from learning_paths.views import KnowledgeConceptViewSet
    view_class = {
        'article': ArticleViewSet, 'resource': ResourceDetailView,
        'challenge': ChallengeViewSet, 'knowledge_concept': KnowledgeConceptViewSet,
    }.get(kind)
    if view_class is None:
        raise ValueError('Unknown history source')
    view = view_class()
    view.request = SimpleNamespace(user=user, query_params={}, method='GET')
    view.action = 'retrieve'
    view.args, view.kwargs = (), {}
    view.check_permissions(view.request)
    obj = view.get_queryset().get(pk=pk)
    view.check_object_permissions(view.request, obj)
    # Content-bearing columns only; counters must not invalidate readback.
    fields = {
        'article': ('title', 'summary', 'content', 'tags'),
        'resource': ('title', 'description', 'tags', 'file'),
        'challenge': ('title', 'description', 'hint', 'category_id', 'difficulty'),
        'knowledge_concept': ('name', 'description'),
    }[kind]
    snapshot = {name: str(getattr(obj, name, '')) for name in fields}
    if kind in {'article', 'challenge'}:
        snapshot['category'] = obj.category.name if obj.category else ''
    elif kind == 'resource':
        snapshot['category'] = obj.category
    return snapshot


def _matches_projection(kind, item, snapshot):
    """Check captured input text, not merely its claimed ID, against live rows.

    Existing retrieval renders bounded/whitespace-normalized prefixes. This also
    catches cached names and a source changing between retrieval and capture.
    It does not claim to prove what a model used or to recognize arbitrary quotes.
    """
    if kind == 'evidence':
        return all(snapshot.get(key) == value for key, value in item.items())
    def normalized(value):
        return ' '.join(str(value or '').split())
    for key in ('title', 'name', 'description', 'hint', 'tags', 'category', 'category_name', 'difficulty', 'summary'):
        if key not in item or item[key] in (None, ''):
            continue
        actual = normalized(item[key])
        if key == 'summary':
            candidates = [snapshot.get(field) for field in ('summary', 'content', 'description')]
        else:
            candidates = [snapshot.get('category' if key == 'category_name' else key)]
        if not any(normalized(value).startswith(actual) for value in candidates):
            return False
    return True


@dataclass
class Origin:
    user: object
    complete: bool = True
    sources: dict = field(default_factory=dict)

    def add(self, kind, pk, *, projection=None):
        if not isinstance(pk, (str, int)) or isinstance(pk, bool) or not str(pk):
            self.complete = False
            return
        key = (kind, str(pk))
        try:
            snapshot = _source_snapshot(kind, pk, self.user)
            if projection is not None and not _matches_projection(kind, projection, snapshot):
                self.complete = False
            fingerprint = _digest(snapshot)
            if key in self.sources and self.sources[key] != fingerprint:
                self.complete = False
            self.sources[key] = fingerprint
        except Exception:
            self.complete = False

    def items(self, items):
        if not isinstance(items, list):
            self.complete = False
            return
        for item in items:
            if not isinstance(item, dict):
                self.complete = False
                continue
            if item.get('evidence_id'):
                self.add('evidence', item['evidence_id'], projection=item)
                continue
            kind = item.get('source_type') or item.get('type')
            if kind in _RESOURCE_TYPES:
                kind = 'resource'
            self.add(kind, item.get('id') or item.get('object_id'), projection=item)


def preparation_origin(user, specialists, challenge_info=None, request_data=None):
    """Called only on server-produced preparation, never request metadata."""
    origin = Origin(user)
    if challenge_info:
        origin.add('challenge', challenge_info.get('id'), projection=challenge_info)
    # Client history is discarded by the existing orchestrator. Explicit summaries
    # may still reach the tutoring chain, but cannot establish trusted provenance.
    if (request_data or {}).get('context_summary'):
        origin.complete = False
    resources = specialists.get('resources') or {}
    for key in ('resourceList', 'resources'):
        if key in resources:
            origin.items(resources[key])
    diagnosis = specialists.get('knowledgeDiagnosis') or {}
    for point in diagnosis.get('weakKnowledgePoints') or []:
        if isinstance(point, dict):
            origin.add('knowledge_concept', point.get('id'), projection=point)
        else:
            origin.complete = False
    knowledge = specialists.get('knowledgeContext') or {}
    # KnowledgeAgent currently drops evidence IDs from its derived text. Never
    # mistake a title/empty sources list for source-complete authorization.
    if any(knowledge.get(key) for key in ('definition', 'keyPoints', 'prerequisites', 'commonMistakes', 'retrievalContext', 'sources')):
        origin.complete = False
    return origin


@contextmanager
def track_origin(origin):
    token = _CURRENT.set(origin if isinstance(origin, Origin) else None)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def record_items(items):
    origin = _CURRENT.get()
    if origin is not None:
        origin.items(items)


def seal_origin(origin, *, conversation, role, content):
    if not isinstance(origin, Origin):
        return {}
    return signing.dumps({
        'v': 1, 'complete': origin.complete,
        'binding': _digest([conversation.pk, conversation.user_id, role, content]),
        'sources': [[kind, pk, fingerprint] for (kind, pk), fingerprint in sorted(origin.sources.items())],
    }, salt=_SALT)


def readable(message, user):
    if not user or not user.is_authenticated or not user.is_active or message.conversation.user_id != user.pk:
        return False
    try:
        from django.contrib.auth import get_user_model
        # Do not keep stale role flags on a request/force-authenticated user object.
        user = get_user_model().objects.get(pk=user.pk, is_active=True)
        data = signing.loads(message.history_origin, salt=_SALT)
        if (not isinstance(data, dict) or set(data) != {'v', 'complete', 'binding', 'sources'}
                or type(data['v']) is not int or data['v'] != 1 or data['complete'] is not True
                or data['binding'] != _digest([message.conversation_id, user.pk, message.role, message.content])
                or not isinstance(data['sources'], list) or len(data['sources']) > 128):
            return False
        for source in data['sources']:
            if (not isinstance(source, list) or len(source) != 3
                    or not all(isinstance(part, str) and part for part in source)
                    or _digest(_source_snapshot(source[0], source[1], user)) != source[2]):
                return False
        return True
    except Exception:
        return False


def history_message(message, user):
    allowed = readable(message, user)
    return {
        'id': message.id, 'role': message.role,
        'content': message.content if allowed else REDACTED,
        # Agent identity comes from the static registry, never stored display text.
        'agent_id': message.agent_id if message.agent_id in {
            'tutor', 'assessor', 'code_mentor', 'analyst', 'security', 'developer',
            'tester', 'legal_reviewer', 'xiaohei', 'architect', 'content_gen',
        } else None,
        'agent_name': '', 'provider': '', 'metadata': {},
        'redacted': not allowed, 'created_at': message.created_at.isoformat(),
    }


def create_message(*, origin=None, **kwargs):
    from .models import AIMessage
    kwargs['history_origin'] = seal_origin(
        origin, conversation=kwargs['conversation'], role=kwargs['role'], content=kwargs['content'],
    )
    return AIMessage.objects.create(**kwargs)
