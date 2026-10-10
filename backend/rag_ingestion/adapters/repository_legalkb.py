"""Repository adapter persisting chunks into legal_kb.LegalKnowledgeEmbedding.

This keeps a single, shared vector store. Uploaded documents are written under
``source_type='document'`` with the GenericForeignKey pointing at
``rag_ingestion.DocumentSource``.
"""

from typing import Dict, List

from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction

from ..interfaces import EmbeddedChunk


class LegalKbChunkRepository:
    """Write embedded chunks into the shared embedding table, idempotently."""

    def replace(
        self,
        *,
        document_id: int,
        source_type: str,
        embedded: List[EmbeddedChunk],
        base_metadata: Dict,
    ) -> int:
        from legal_kb.models import LegalKnowledgeEmbedding
        from legal_kb.services.hashing import sha256_text

        from ..models import DocumentSource

        content_type = ContentType.objects.get_for_model(DocumentSource)

        # Atomic swap: deleting the old index and writing the new chunks happen in
        # one transaction, so a mid-write failure rolls back and leaves the
        # previous index intact instead of a half-rebuilt one. Parsing and (remote)
        # embedding already happened before this call, so the transaction is short.
        with transaction.atomic():
            LegalKnowledgeEmbedding.objects.filter(
                content_type=content_type,
                object_id=document_id,
                source_type=source_type,
            ).delete()

            created = 0
            for item in embedded:
                is_semantic = len(item.vector) == 1024
                store_vector = item.vector if (is_semantic and connection.vendor == 'postgresql') else None
                metadata = {
                    **base_metadata,
                    **(item.chunk.metadata or {}),
                    'vector_model': item.model if is_semantic else 'local-hash-v1',
                }
                LegalKnowledgeEmbedding.objects.create(
                    source_type=source_type,
                    content_type=content_type,
                    object_id=document_id,
                    chunk_index=max(item.chunk.order - 1, 0),
                    title=(item.chunk.title or base_metadata.get('title') or '')[:300],
                    text=item.chunk.text,
                    text_hash=sha256_text(item.chunk.text),
                    embedding=item.local_vector,
                    embedding_vector=store_vector,
                    embedding_model='local-hash-v1',
                    embedding_dimension=len(item.local_vector),
                    metadata=metadata,
                )
                created += 1
            return created
