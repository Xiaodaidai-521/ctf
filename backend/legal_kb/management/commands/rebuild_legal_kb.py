"""Explicit, versioned re-embedding of authorized existing chunks."""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from legal_kb.models import LegalClause, LegalDocument, LegalKnowledgeEmbedding
from legal_kb.services.embedding_service import EmbeddingService, EmbeddingUnavailableError
from legal_kb.services.visibility import apply_embedding_visibility, _is_staff_or_admin, _is_teacher


class Command(BaseCommand):
    help = (
        'Re-embed authorized KB chunks into the configured vector space. Atomic per source object; '
        'challenge and registered course material indexes are excluded. Does not re-chunk: '
        're-run prepare_legal_kb/normal document ingestion against originals for new boundaries.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--actor', required=True, help='Existing staff/admin or teacher username.')
        parser.add_argument('--source-type', choices=[choice[0] for choice in LegalKnowledgeEmbedding.SOURCE_TYPE_CHOICES])
        parser.add_argument('--object-id', type=int, help='Optionally limit to a source object ID.')
        parser.add_argument('--dry-run', action='store_true', help='Validate and count only; no provider requests or writes.')

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options['actor'], is_active=True).first()
        if not (_is_staff_or_admin(actor) or _is_teacher(actor)):
            raise CommandError('An active staff/admin or teacher actor is required.')
        service = EmbeddingService()
        try:
            service.validate_configuration()
        except EmbeddingUnavailableError as exc:
            raise CommandError(str(exc)) from None
        queryset = LegalKnowledgeEmbedding.objects.all()
        if options['source_type']:
            queryset = queryset.filter(source_type=options['source_type'])
        if options['object_id'] is not None:
            queryset = queryset.filter(object_id=options['object_id'])
        eligible = apply_embedding_visibility(queryset, actor)
        self.stdout.write(f'Target index version: {service.index_version}')
        self.stdout.write(f'Eligible chunks: {eligible.count()}; excluded chunks: {queryset.count() - eligible.count()}')
        self.stdout.write('Existing chunk boundaries are preserved; re-ingest originals to apply boundary-overlap-v2.')
        if options['dry_run']:
            self.stdout.write('Dry run: no embeddings requested or modified.')
            return

        rebuilt = 0
        # Capture IDs only, not candidate material, before authorization is rechecked.
        sources = list(eligible.order_by().values_list('content_type_id', 'object_id', 'source_type').distinct())
        for content_type_id, object_id, source_type in sources:
            try:
                with transaction.atomic():
                    content_type = ContentType.objects.get(pk=content_type_id)
                    model = content_type.model_class()
                    if model is None:
                        continue
                    # Match legal ingestion's parent lock before touching clause rows.
                    if model is LegalClause:
                        document_id = LegalClause.objects.filter(pk=object_id).values_list('document_id', flat=True).first()
                        if not LegalDocument.objects.select_for_update().filter(pk=document_id).exists():
                            continue
                    source = model.objects.select_for_update().filter(pk=object_id).first()
                    if source is None:
                        continue
                    current = apply_embedding_visibility(queryset.filter(
                        content_type_id=content_type_id, object_id=object_id, source_type=source_type,
                    ), actor)
                    rows = list(current.select_for_update().order_by('chunk_index', 'pk'))
                    if not rows:
                        continue
                    if len({row.chunk_index for row in rows}) != len(rows):
                        raise CommandError('Duplicate chunk generations found; re-ingest the source before rebuilding.')
                    vectors = service.embed_many([row.text for row in rows])
                    for row, vector in zip(rows, vectors):
                        for field, value in service.storage_fields(vector).items():
                            setattr(row, field, value)
                        row.metadata = {**(row.metadata or {}), 'vector_model': service.model}
                        row.save(update_fields=[
                            'embedding', 'embedding_vector', 'embedding_model', 'embedding_dimension',
                            'index_version', 'metadata', 'updated_at',
                        ])
                    rebuilt += len(rows)
            except CommandError:
                raise
            except Exception:
                # No provider exception, source title, chunk text or SQL in output.
                raise CommandError(
                    'Rebuild failed; the current source object was rolled back. '
                    'Earlier completed objects remain valid; rerun after fixing provider/data configuration.'
                ) from None
        self.stdout.write(self.style.SUCCESS(f'Rebuilt chunks: {rebuilt}'))
