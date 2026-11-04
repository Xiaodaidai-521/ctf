"""Knowledge-base ingestion service."""

from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from users.permissions import is_staff_or_role

from audit.models import AuditEvent
from audit.services import AuditLedgerService

from ..models import KbIngestionJob, LegalClause, LegalDocument, LegalKnowledgeEmbedding
from .chunking_service import ChunkingService
from .embedding_service import EmbeddingService
from .hashing import sha256_text


class LegalKbIngestionService:
    """Parse a legal document into clauses and embeddings."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or EmbeddingService()

    def ingest_document(self, document: LegalDocument, actor=None) -> KbIngestionJob:
        """Create clauses and embedding rows for a legal document."""
        # Keep trusted actorless local commands, but never accept a student identity.
        if actor is not None and (not actor.is_active or not is_staff_or_role(actor, 'teacher', 'admin')):
            raise ValueError('Indexing requires an authorized staff or teacher actor.')
        job = KbIngestionJob.objects.create(
            job_type='legal_document',
            status='running',
            document=document,
            created_by=actor,
            source_payload={'document_id': document.id, 'source_hash': document.source_hash},
            started_at=timezone.now(),
        )
        try:
            return self._ingest_document(job=job, document=document, actor=actor)
        except Exception as exc:
            now = timezone.now()
            KbIngestionJob.objects.filter(pk=job.pk).update(
                status='failed',
                error_message=str(exc),
                completed_at=now,
                updated_at=now,
            )
            job.refresh_from_db(fields=['status', 'error_message', 'completed_at', 'updated_at'])
            raise

    @transaction.atomic
    def _ingest_document(self, *, job: KbIngestionJob, document: LegalDocument, actor=None) -> KbIngestionJob:
        # Lock the live source; stale callers cannot overwrite a newer rebuild.
        document = LegalDocument.objects.select_for_update().get(pk=document.pk)
        from learning_knowledge.models import Material

        registered = Material.objects.filter(
            source_type='legal_clause',
            source_object_id__in=LegalClause.objects.filter(document=document).values('pk'),
        ).exists()
        if registered:
            # Replacing registered clause IDs would also break task authorization.
            raise ValueError('Registered course materials require their task-scoped ingestion path.')
        if getattr(self.embedding_service, 'uses_remote_provider', False):
            from .visibility import _is_staff_or_admin, _is_teacher

            if not (_is_staff_or_admin(actor) or _is_teacher(actor)):
                raise ValueError('Remote indexing requires an authorized staff or teacher actor.')
        chunks = ChunkingService.split_legal_text(document.full_text)
        document_ct = ContentType.objects.get_for_model(document)
        clause_ct = ContentType.objects.get_for_model(LegalClause)
        LegalKnowledgeEmbedding.objects.filter(
            content_type=document_ct,
            object_id=document.id,
        ).delete()
        LegalKnowledgeEmbedding.objects.filter(
            source_type='legal_clause',
            content_type=clause_ct,
            metadata__document_id=document.id,
        ).delete()
        LegalClause.objects.filter(document=document).delete()

        for chunk in chunks:
            clause = LegalClause.objects.create(
                document=document,
                clause_key=chunk.clause_key,
                chapter=chunk.chapter,
                article_number=chunk.article_number,
                title=chunk.title,
                text=chunk.text,
                text_hash=sha256_text(chunk.text),
                order=chunk.order,
            )
            embedding = self.embedding_service.embed_text(chunk.text)
            LegalKnowledgeEmbedding.objects.create(
                source_type='legal_clause',
                content_type=clause_ct,
                object_id=clause.id,
                chunk_index=0,
                title=clause.title or clause.clause_key,
                text=clause.text,
                text_hash=clause.text_hash,
                **self.embedding_service.storage_fields(embedding),
                metadata={
                    'document_id': document.id,
                    'document_title': document.title,
                    'clause_key': clause.clause_key,
                    'vector_model': self.embedding_service.model,
                    'chunking_version': ChunkingService.VERSION,
                },
            )

        job.status = 'completed'
        job.total_chunks = len(chunks)
        job.embedded_chunks = len(chunks)
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'total_chunks', 'embedded_chunks', 'completed_at', 'updated_at'])

        AuditEvent.log(
            category='kb_ingestion',
            summary=f'Legal document ingested: {document.title}',
            user=actor,
            detail={'document_id': document.id, 'chunks': len(chunks)},
        )
        AuditLedgerService.append_entry(
            event_category='kb_ingestion',
            object_type='legal_kb.LegalDocument',
            object_id=document.id,
            actor=actor,
            payload={
                'document_id': document.id,
                'title': document.title,
                'source_hash': document.source_hash,
                'chunks': len(chunks),
                'embedding_model': self.embedding_service.model,
            },
        )
        return job
