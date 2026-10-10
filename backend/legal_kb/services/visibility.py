"""Document visibility enforcement for the shared knowledge embedding table.

Authorization is decided against the CURRENT ``rag_ingestion.DocumentSource``
visibility, never the ``metadata.visibility`` snapshot stored on a chunk at
ingest time. A snapshot can go stale (visibility tightened after ingest, or an
old index kept after a failed re-ingest), so relying on it would leak content.
When a chunk has no live DocumentSource, access is denied (fail closed).

Platform content (legal clauses, challenges, articles, resources, knowledge
concepts) has no restricted visibility and is never filtered here.

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
    excluded. Non-document rows are never excluded.
    """
    # Lazy import avoids a legal_kb <-> rag_ingestion import cycle at load time.
    from django.contrib.contenttypes.models import ContentType

    from rag_ingestion.models import DocumentSource

    allowed = list(allowed_document_visibilities(user))
    document_ct = ContentType.objects.get_for_model(DocumentSource)
    allowed_document_ids = DocumentSource.objects.filter(
        visibility__in=allowed
    ).values('id')

    return queryset.exclude(
        Q(source_type='document')
        & ~Q(content_type=document_ct, object_id__in=allowed_document_ids)
    )
