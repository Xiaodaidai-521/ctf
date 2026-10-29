"""All teaching material reads use live database authority, never chunk metadata."""
import hashlib
from dataclasses import dataclass

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.utils import timezone
from rest_framework.exceptions import NotFound

from learning_map import constants
from learning_map.models import TaskAttempt
from .models import CourseGrant, Material, MaterialRevision, TaskMaterial

POLICY_VERSION = 'm3-policy-1'
SAFE_SOURCE_TYPES = frozenset({'knowledge_concept', 'article', 'resource', 'legal_clause'})
SOURCE_MODELS = {
    'article': ('articles', 'Article', 'content'),
    'resource': ('resources', 'Resource', 'description'),
    'knowledge_concept': ('learning_paths', 'KnowledgeConcept', 'description'),
    'legal_clause': ('legal_kb', 'LegalClause', 'text'),
    'document': ('rag_ingestion', 'DocumentSource', None),
}


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def authenticated(user):
    return bool(user and user.is_authenticated and user.is_active)


def is_admin(user):
    return authenticated(user) and (user.is_superuser or getattr(user, 'role', '') == 'admin')


def unavailable():
    return NotFound('Material unavailable.')


@dataclass(frozen=True)
class Scope:
    user: object
    attempt_id: object
    purpose: str = 'lesson'
    hint_level: int = 0


def live_attempt(scope):
    if not authenticated(scope.user) or not get_user_model().objects.filter(pk=scope.user.pk, is_active=True).exists():
        raise unavailable()
    try:
        attempt = TaskAttempt.objects.select_related('task', 'catalog').get(
            attempt_id=scope.attempt_id, student_id=scope.user.pk,
        )
    except (TaskAttempt.DoesNotExist, ValueError, TypeError):
        raise unavailable()
    if (attempt.task_version != attempt.task.version or attempt.catalog_id != attempt.task.catalog_id
            or not attempt.catalog.is_published or not attempt.task.is_recommendable
            or not CourseGrant.objects.filter(user=scope.user, catalog=attempt.catalog, active=True).exists()):
        raise unavailable()
    return attempt


def can_manage(user, material):
    if not authenticated(user):
        return False
    grant = CourseGrant.objects.filter(user=user, catalog_id=material.catalog_id, active=True).first()
    if material.material_class == 'grading_secret':
        return bool(is_admin(user) and grant and grant.maintain_secrets)
    return bool(is_admin(user) or (getattr(user, 'role', '') == 'teacher' and grant and grant.can_review))


def source_current(revision):
    material = revision.material
    if material.source_type == 'teacher_authored':
        return bool(revision.source_snapshot and digest(revision.source_snapshot) == revision.source_hash)
    config = SOURCE_MODELS.get(material.source_type)
    if not config or not material.source_object_id:
        return False
    registrations = Material.objects.filter(source_type=material.source_type, source_object_id=material.source_object_id)
    if registrations.exclude(material_class=material.material_class, hint_level=material.hint_level).exists():
        return False  # Conflicting classifications require review, never the weakest registration.
    app, model, field = config
    source = apps.get_model(app, model).objects.filter(pk=material.source_object_id).first()
    if not source:
        return False
    if material.source_type == 'document':
        # Documents are deliberately not opened to the learner retrieval index in phase 1.
        return False
    if material.source_type in ('article', 'resource') and getattr(source, 'status', '') != 'approved':
        return False
    if material.source_type == 'legal_clause' and source.document.status != 'active':
        return False
    return digest(getattr(source, field, '') or '') == revision.source_hash


def authorize(revision_id, scope, *, allow_stale=False):
    """Return current rows or None. A teacher's learner preview never calls can_manage."""
    try:
        attempt = live_attempt(scope)
        revision = MaterialRevision.objects.select_related('material').get(pk=revision_id)
        material = revision.material
        if (material.catalog_id != attempt.catalog_id or material.policy_version != POLICY_VERSION
                or material.revoked_at or material.published_scope != 'learner'
                or revision.review_status != 'published' or revision.parse_status != 'completed'
                or not TaskMaterial.objects.filter(task=attempt.task, revision=revision).exists()
                or not source_current(revision)):
            return None
        if revision.recheck_due_at and revision.recheck_due_at <= timezone.now() and not allow_stale:
            return None
        if material.material_class == 'lesson' and scope.purpose == 'lesson':
            return revision, attempt
        if material.material_class == 'hint' and scope.purpose == 'hint_delivery':
            # Only existing module-2 deliveries authorize a hint; query text/role cannot unlock it.
            from teaching_agent.models import HintDelivery
            if material.hint_level == scope.hint_level and HintDelivery.objects.filter(
                student=scope.user, attempt=attempt, card__material_ref=material_ref(revision),
                card__level=scope.hint_level, displayed_at__isnull=False,
            ).exists():
                return revision, attempt
        return None
    except (DatabaseError, MaterialRevision.DoesNotExist, NotFound, ValueError, TypeError):
        return None


def material_ref(revision):
    return f'm3:{revision.material.material_id}:{revision.revision}'


def registered_revision(ref):
    if not isinstance(ref, str) or not ref.startswith('m3:'):
        return None
    try:
        _, material_id, number = ref.split(':')
        return MaterialRevision.objects.select_related('material').get(material__material_id=material_id, revision=int(number))
    except (ValueError, TypeError, MaterialRevision.DoesNotExist):
        return None


def require_card(context, ref, material_class, level=None):
    """Additional gate for registered module-2 cards; legacy reviewed cards keep their existing gate."""
    if not str(ref).startswith('m3:'):
        if TaskMaterial.objects.filter(task=context.task).exists():
            raise unavailable()
        return
    revision = registered_revision(ref)
    scope = Scope(context.attempt.student, context.attempt.attempt_id)
    attempt = live_attempt(scope)
    if (not revision or revision.material.material_class != material_class
            or revision.material.revoked_at or revision.review_status != 'published'
            or revision.material.published_scope != 'learner' or not source_current(revision)
            or revision.material.policy_version != POLICY_VERSION or revision.parse_status != 'completed'
            or revision.material.catalog_id != attempt.catalog_id
            or not TaskMaterial.objects.filter(task=attempt.task, revision=revision).exists()
            or (revision.recheck_due_at and revision.recheck_due_at <= timezone.now())
            or (level is not None and revision.material.hint_level != level)):
        raise unavailable()
    return revision


def task_policy_stamp(task):
    stamp = []
    for binding in TaskMaterial.objects.filter(task=task).select_related('revision__material').order_by('pk'):
        revision = binding.revision
        material = revision.material
        stamp.append((revision.pk, revision.review_status, revision.parse_status,
                      material.acl_version, material.revoked_at, material.policy_version,
                      material.published_scope, revision.source_hash, source_current(revision),
                      bool(revision.recheck_due_at and revision.recheck_due_at <= timezone.now())))
    return stamp


def filter_legacy_queryset(queryset, source_type, user):
    """Registered course materials never escape via unrelated public detail/download APIs."""
    ids = Material.objects.filter(source_type=source_type).values_list('source_object_id', flat=True)
    return queryset.exclude(pk__in=ids)
