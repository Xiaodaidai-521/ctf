"""Knowledge-base ingestion service."""

from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db import transaction
from django.utils import timezone

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
            semantic_embedding = self.embedding_service.embed_text(chunk.text)
            embedding = self.embedding_service.embed_local_text(chunk.text)
            LegalKnowledgeEmbedding.objects.create(
                source_type='legal_clause',
                content_type=clause_ct,
                object_id=clause.id,
                chunk_index=0,
                title=clause.title or clause.clause_key,
                text=clause.text,
                text_hash=clause.text_hash,
                embedding=embedding,
                embedding_vector=(
                    semantic_embedding
                    if connection.vendor == 'postgresql' and len(semantic_embedding) == 1024
                    else None
                ),
                embedding_model='local-hash-v1',
                embedding_dimension=len(embedding),
                metadata={
                    'document_id': document.id,
                    'document_title': document.title,
                    'clause_key': clause.clause_key,
                    'vector_model': (
                        self.embedding_service.model
                        if len(semantic_embedding) == 1024
                        else 'local-hash-v1'
                    ),
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
