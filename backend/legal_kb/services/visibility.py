"""Document visibility enforcement for the shared knowledge embedding table.

Authorization is decided against the CURRENT ``rag_ingestion.DocumentSource``
visibility, never the ``metadata.visibility`` snapshot stored on a chunk at
ingest time. A snapshot can go stale (visibility tightened after ingest, or an
old index kept after a failed re-ingest), so relying on it would leak content.
When a chunk has no live DocumentSource, access is denied (fail closed).

Platform chunks are also checked against their current detail visibility.

This is the single place that decides who may read restricted documents, so it
is reused by every read path (REST browse API and RAG retrieval) instead of
only guarding the upload endpoint.
"""

from django.db.models import Q

# Visibility values stored on rag_ingestion.DocumentSource.
VISIBILITY_STAFF = 'staff'
VISIBILITY_INTERNAL = 'internal'
VISIBILITY_LEARNER = 'learner'

ALL_VISIBILITIES = (VISIBILITY_STAFF, VISIBILITY_INTERNAL, VISIBILITY_LEARNER)


def _is_staff_or_admin(user) -> bool:
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and (getattr(user, 'is_staff', False) or getattr(user, 'role', '') == 'admin')
    )


def _is_teacher(user) -> bool:
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'role', '') == 'teacher'
    )


def allowed_document_visibilities(user) -> set:
    """Return the document visibility levels a user may read.

    - staff/admin: everything, including staff-only uploads.
    - teacher: internal + learner (NOT staff-only).
    - everyone else (students, anonymous, internal service calls): learner only.
    """
    if _is_staff_or_admin(user):
        return set(ALL_VISIBILITIES)
    if _is_teacher(user):
        return {VISIBILITY_INTERNAL, VISIBILITY_LEARNER}
    return {VISIBILITY_LEARNER}


def apply_embedding_visibility(queryset, user):
    """Exclude document chunks the user may not read, by live DocumentSource.

    A ``source_type='document'`` chunk is kept only if it is backed by a
    DocumentSource whose CURRENT ``visibility`` the user is allowed to read.
    Chunks whose DocumentSource is missing or over the user's clearance are
    excluded. Platform rows additionally use their current detail querysets.
    """
    # Lazy import avoids a legal_kb <-> rag_ingestion import cycle at load time.
    from django.contrib.contenttypes.models import ContentType

    from rag_ingestion.models import DocumentSource

    allowed = list(allowed_document_visibilities(user))
    document_ct = ContentType.objects.get_for_model(DocumentSource)
    allowed_document_ids = DocumentSource.objects.filter(
        visibility__in=allowed, status='completed',
    ).values('id')

    queryset = queryset.exclude(
        Q(source_type='document')
        & ~Q(content_type=document_ct, object_id__in=allowed_document_ids)
    )
    return apply_platform_visibility(queryset, user)


def apply_platform_visibility(queryset, user):
    """An index snapshot cannot authorize withdrawn/deleted platform sources."""
    import importlib
    from types import SimpleNamespace
    from django.apps import apps
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.contenttypes.models import ContentType

    user = user or AnonymousUser()
    families = (
        ('article', 'articles', 'articles.views', 'ArticleViewSet'),
        ('resource', 'resources', 'resources.views', 'ResourceDetailView'),
        ('challenge', 'challenges', 'challenges.views', 'ChallengeViewSet'),
        ('knowledge_concept', 'learning_paths', 'learning_paths.views', 'KnowledgeConceptViewSet'),
    )
    for kind, app, module, name in families:
        if not apps.is_installed(app):
            queryset = queryset.exclude(source_type=kind)
            continue
        view = getattr(importlib.import_module(module), name)()
        view.request = SimpleNamespace(user=user, query_params={}, method='GET')
        view.action = 'retrieve'
        view.args, view.kwargs = (), {}
        try:
            view.check_permissions(view.request)
            visible = view.get_queryset()
        except Exception:
            queryset = queryset.exclude(source_type=kind)
            continue
        valid = Q(content_type=ContentType.objects.get_for_model(visible.model),
                  object_id__in=visible.values('pk'))
        if kind == 'challenge' and apps.is_installed('ai_assistant'):
            from ai_assistant.models import ChallengeKnowledgePack
            valid |= Q(content_type=ContentType.objects.get_for_model(ChallengeKnowledgePack),
                       object_id__in=ChallengeKnowledgePack.objects.filter(
                           challenge_id__in=visible.values('pk')).values('pk'))
        queryset = queryset.exclude(Q(source_type=kind) & ~valid)
    return queryset


def apply_teaching_visibility(queryset):
    """Document recall never bypasses registered course material gates.

    Course material is delivered by learning_knowledge's Scope gateway instead.
    Restrict new document recall to successful, unregistered source documents.
    """
    from django.contrib.contenttypes.models import ContentType
    from learning_knowledge.models import Material
    from rag_ingestion.models import DocumentSource

    doc_ct = ContentType.objects.get_for_model(DocumentSource)
    registered = Material.objects.filter(source_type='document').values('source_object_id')
    available = DocumentSource.objects.filter(status='completed').exclude(pk__in=registered).values('pk')
    return queryset.exclude(Q(source_type='document') & ~Q(content_type=doc_ct, object_id__in=available))
