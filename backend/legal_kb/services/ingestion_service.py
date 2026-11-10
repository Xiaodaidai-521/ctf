"""Knowledge-base ingestion service."""

from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db import transaction
from django.utils import timezone

from audit.models import AuditEvent
from audit.services import AuditLedgerService
from data_security.adapters.django.rag import RagProtectionError, protect_rag, rag_protection_enabled
from rag_ingestion.registry import get_embedding_service

from ..permissions import IsLegalKbAdmin
from ..models import KbIngestionJob, LegalClause, LegalDocument, LegalKnowledgeEmbedding
from .chunking_service import ChunkingService
from .embedding_service import EmbeddingService
from .hashing import sha256_text


class LegalKbIngestionService:
    """Parse a legal document into clauses and embeddings."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service if embedding_service is not None else get_embedding_service()

    def ingest_document(self, document: LegalDocument, actor=None) -> KbIngestionJob:
        """Create clauses and embedding rows for a legal document."""
        if rag_protection_enabled() and not IsLegalKbAdmin.allows(actor):
            raise RagProtectionError('RAG_AUTHORIZATION_REQUIRED')
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
                error_message=(f'{type(exc).__name__}: RAG_OPERATION_FAILED'
                               if rag_protection_enabled() else str(exc)),
                completed_at=now,
                updated_at=now,
            )
            job.refresh_from_db(fields=['status', 'error_message', 'completed_at', 'updated_at'])
            raise

    def _ingest_document(self, *, job: KbIngestionJob, document: LegalDocument, actor=None) -> KbIngestionJob:
        object_ref = f'rag/legal-document/{document.pk}'
        version = 'v' + str(int(document.updated_at.timestamp() * 1_000_000))
        headers = protect_rag({'title': document.title, 'metadata': document.metadata},
                              object_ref=object_ref, object_version=version)
        text = protect_rag(document.full_text, object_ref=object_ref, object_version=version)
        chunks = ChunkingService.split_legal_text(text)
        prepared = [(chunk, self.embedding_service.embed_text(chunk.text),
                     self.embedding_service.embed_local_text(chunk.text)) for chunk in chunks]
        document_ct = ContentType.objects.get_for_model(document)
        clause_ct = ContentType.objects.get_for_model(LegalClause)
        with transaction.atomic():
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

            for chunk, semantic_embedding, embedding in prepared:
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
                        **headers['metadata'],
                        'document_id': document.id,
                        'document_title': headers['title'],
                        'clause_key': clause.clause_key,
                        'vector_model': self.embedding_service.model,
                        'vector_space': self.embedding_service.vector_space,
                        'retrieval_mode': self.embedding_service.retrieval_mode,
                    },
                )

            job.status = 'completed'
            job.total_chunks = len(chunks)
            job.embedded_chunks = len(chunks)
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'total_chunks', 'embedded_chunks', 'completed_at', 'updated_at'])

            AuditEvent.log(
                category='kb_ingestion',
                summary=f'Legal document ingested: {headers["title"]}',
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
                    'title': headers['title'],
                    'source_hash': document.source_hash,
                    'chunks': len(chunks),
                    'embedding_model': self.embedding_service.model,
                },
            )
        return job
