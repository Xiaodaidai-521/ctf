import json
import re
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Material, MaterialChunk, MaterialRevision, ReviewAction, TaskMaterial
from .policy import can_manage, digest, material_ref, source_current, unavailable

REQUIRED = ('title', 'publisher', 'source_version', 'source_date', 'verified_at', 'license_id',
            'attribution_text', 'reuse_scope', 'applicability', 'source_snapshot')


def register(*, actor, catalog, material_class, tasks, metadata, hint_level=None, source_type='teacher_authored', source_object_id=None):
    material = Material(catalog=catalog, owner=actor, material_class=material_class,
                        hint_level=hint_level, source_type=source_type, source_object_id=source_object_id)
    if not can_manage(actor, material):
        raise PermissionDenied('Course review permission required.')
    if material_class not in dict(Material.CLASSES) or (material_class == 'hint' and hint_level not in (1, 2, 3, 4)):
        raise ValidationError('Invalid material class or hint level.')
    if material_class != 'hint' and hint_level is not None:
        raise ValidationError('Only hints have a level.')
    with transaction.atomic():
        material.save()
        return new_revision(actor=actor, material=material, tasks=tasks, metadata=metadata)


def new_revision(*, actor, material, tasks, metadata):
    with transaction.atomic():
        material = Material.objects.select_for_update().get(pk=material.pk)
        if not can_manage(actor, material):
            raise unavailable()
        if not tasks or any(task.catalog_id != material.catalog_id for task in tasks):
            raise ValidationError('Tasks must belong to the material catalog.')
        missing = [key for key in REQUIRED if not metadata.get(key)]
        if missing:
            raise ValidationError({'missing': missing})
        allowed = set(REQUIRED) | {'source_url', 'license_url', 'change_note', 'recheck_due_at', 'conflict_group'}
        if set(metadata) - allowed:
            raise ValidationError('Unknown source fields.')
        previous = material.revisions.order_by('-revision').first()
        material.ingestion_token = uuid.uuid4()
        material.save(update_fields=['ingestion_token'])
        revision = MaterialRevision.objects.create(
            material=material, author=actor, revision=(previous.revision + 1 if previous else 1),
            source_hash=digest(metadata['source_snapshot']), supersedes=previous,
            ingestion_token=material.ingestion_token, **metadata,
        )
        for task in tasks:
            TaskMaterial.objects.create(task=task, revision=revision,
                knowledge_point_ids=list(task.capabilities.values_list('knowledge_points__stable_id', flat=True).exclude(knowledge_points__isnull=True).distinct()),
                capability_ids=list(task.capabilities.values_list('stable_id', flat=True)))
        return revision


def parse_candidate(*, revision_id, token):
    """Parse outside the lock, then atomically install a complete candidate only."""
    revision = MaterialRevision.objects.get(pk=revision_id)
    text = revision.source_snapshot
    spans = [(match.start(), match.end()) for match in re.finditer(r'\S[^\n]*(?:\n(?!\n)[^\n]+)*', text)]
    if not spans:
        raise ValidationError('No parsable content.')
    with transaction.atomic():
        material = Material.objects.select_for_update().get(pk=revision.material_id)
        revision = MaterialRevision.objects.select_for_update().get(pk=revision_id)
        if str(material.ingestion_token) != str(token) or str(revision.ingestion_token) != str(token):
            raise ValidationError('Superseded ingestion token.')
        if revision.review_status != 'draft':
            raise ValidationError('Reviewed snapshots cannot be replaced.')
        if revision.parse_status == 'completed':
            return revision
        # A failed swap rolls back all rows; previously published revisions remain untouched.
        revision.chunks.all().delete()
        MaterialChunk.objects.bulk_create([
            MaterialChunk(revision=revision, index=index, start=start, end=end,
                          chunk_hash=digest(text[start:end]), locator={'paragraph': index + 1},
                          heading_path=[revision.title])
            for index, (start, end) in enumerate(spans)
        ])
        revision.parse_status = 'completed'
        revision.save(update_fields=['parse_status'])
        return revision


def _sync_static_cards(revision):
    from teaching_agent.models import HintCard, StudentAnalysis
    for binding in revision.bindings.select_related('task'):
        if revision.material.material_class == 'hint':
            HintCard.objects.filter(task=binding.task, level=revision.material.hint_level).update(is_active=False)
            HintCard.objects.update_or_create(task=binding.task, level=revision.material.hint_level,
                version=f'm3-{revision.pk}', defaults={
                    'title': revision.title, 'content': revision.source_snapshot,
                    'material_ref': material_ref(revision), 'is_active': True,
                })
        elif revision.material.material_class == 'student_analysis':
            StudentAnalysis.objects.filter(task=binding.task).update(is_active=False)
            StudentAnalysis.objects.update_or_create(task=binding.task, version=f'm3-{revision.pk}', defaults={
                'title': revision.title, 'content': revision.source_snapshot,
                'content_ref': material_ref(revision), 'is_active': True,
            })


def transition(*, actor, material_id, expected_revision, action, idempotency_key, reason):
    if action not in {'submit', 'approve', 'publish', 'withdraw'} or not reason.strip() or not idempotency_key or len(idempotency_key) > 64:
        raise ValidationError('Action, reason and bounded idempotency key are required.')
    with transaction.atomic():
        try:
            material = Material.objects.select_for_update().get(material_id=material_id)
            revision = MaterialRevision.objects.select_for_update().get(material=material, revision=expected_revision)
        except (Material.DoesNotExist, MaterialRevision.DoesNotExist):
            raise unavailable()
        if not can_manage(actor, material):
            raise unavailable()
        fingerprint = digest(json.dumps([actor.pk, action, expected_revision, reason], ensure_ascii=False))
        previous = ReviewAction.objects.filter(revision=revision, idempotency_key=idempotency_key).first()
        if previous:
            if previous.fingerprint != fingerprint:
                raise ValidationError('Idempotency key conflicts with previous action.')
            return revision
        if action != 'withdraw' and material.revisions.order_by('-revision').first().pk != revision.pk:
            raise ValidationError('Revision has changed; refresh before review.')
        required_state = {'submit': 'draft', 'approve': 'in_review', 'publish': 'approved'}
        if action in required_state and revision.review_status != required_state[action]:
            raise ValidationError('Invalid review state transition.')
        if action in {'submit', 'approve', 'publish'}:
            if revision.parse_status != 'completed' or not revision.chunks.exists():
                raise ValidationError('Complete chunk inspection is required.')
            from .services import chunk_text
            for chunk in revision.chunks.all():
                chunk_text(chunk, revision)
        if action == 'approve':
            if not revision.author_id or actor.pk in {material.owner_id, revision.author_id}:
                raise ValidationError('A second teacher must review this revision.')
            revision.reviewer = actor
            revision.reviewed_at = timezone.now()
        if action == 'publish':
            if (not revision.author_id or not revision.reviewer_id
                    or revision.reviewer_id in {material.owner_id, revision.author_id}
                    or not can_manage(revision.reviewer, material)):
                raise ValidationError('Current independent review permission is required.')
            if revision.license_id == 'LicenseRef-Project-Internal-Pending':
                raise ValidationError('Candidate reuse permission is pending; register a reviewed licensed revision first.')
            if not source_current(revision):
                raise ValidationError('Source is unavailable or changed; do not publish.')
            if revision.recheck_due_at and revision.recheck_due_at <= timezone.now():
                raise ValidationError('Source is stale; review a new revision.')
            material.published_scope = 'learner' if material.material_class in {'lesson', 'hint', 'student_analysis'} else 'internal'
            material.revoked_at = None
            revision.published_at = timezone.now()
            material.revisions.filter(review_status='published').exclude(pk=revision.pk).update(review_status='superseded')
            _sync_static_cards(revision)
        if action == 'withdraw':
            material.revoked_at = timezone.now()
            from teaching_agent.models import HintCard, StudentAnalysis
            HintCard.objects.filter(material_ref=material_ref(revision)).update(is_active=False)
            StudentAnalysis.objects.filter(content_ref=material_ref(revision)).update(is_active=False)
        revision.review_status = {'submit': 'in_review', 'approve': 'approved', 'publish': 'published', 'withdraw': 'withdrawn'}[action]
        revision.save(update_fields=['review_status', 'reviewer', 'reviewed_at', 'published_at'])
        material.acl_version += 1
        material.save(update_fields=['acl_version', 'published_scope', 'revoked_at'])
        ReviewAction.objects.create(revision=revision, actor=actor, action=action, idempotency_key=idempotency_key,
                                   fingerprint=fingerprint, reason=reason[:500], acl_version=material.acl_version)
        return revision


def inspection(revision, actor):
    if not can_manage(actor, revision.material):
        raise unavailable()
    return {
        'material_id': str(revision.material.material_id), 'revision': revision.revision,
        'title': revision.title, 'source_version': revision.source_version,
        'source_date': revision.source_date, 'verified_at': revision.verified_at,
        'source_hash': revision.source_hash, 'parser_version': revision.parser_version,
        'author_id': revision.author_id, 'reviewer_id': revision.reviewer_id,
        'reviewed_at': revision.reviewed_at, 'published_at': revision.published_at,
        'recheck_due_at': revision.recheck_due_at, 'applicability': revision.applicability,
        'change_note': revision.change_note, 'conflict_group': revision.conflict_group,
        'source_url': revision.source_url, 'publisher': revision.publisher,
        'license_id': revision.license_id, 'license_url': revision.license_url,
        'attribution_text': revision.attribution_text, 'reuse_scope': revision.reuse_scope,
        'material_class': revision.material.material_class, 'hint_level': revision.material.hint_level,
        'review_status': revision.review_status, 'parse_status': revision.parse_status,
        'acl_version': revision.material.acl_version, 'published_scope': revision.material.published_scope,
        'source_snapshot': revision.source_snapshot,
        'chunks': [{'chunk_ref': str(chunk.pk), 'locator': chunk.locator,
                    'location_notice': '' if chunk.locator else '定位待人工补齐',
                    'heading_path': chunk.heading_path, 'text': revision.source_snapshot[chunk.start:chunk.end]}
                   for chunk in revision.chunks.all()],
        'tasks': list(revision.bindings.values('task__task_key', 'task__version', 'knowledge_point_ids')),
        'affected_task_count': TaskMaterial.objects.filter(revision__material=revision.material).values('task_id').distinct().count(),
        'preview_notice': '管理审阅不代表学生可读；学生预览必须使用其真实尝试和课程授权。',
    }
