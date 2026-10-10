"""Facade coordinating DocumentSource lifecycle with the ingestion pipeline."""

import hashlib
import logging
from typing import Dict, Optional

from .models import DocumentSource
from .pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


class IngestionService:
    """Register an uploaded document, run the pipeline, track status + audit."""

    def __init__(self, pipeline: Optional[IngestionPipeline] = None):
        self.pipeline = pipeline or IngestionPipeline()

    def ingest_bytes(
        self,
        *,
        data: bytes,
        filename: str,
        mime: str = '',
        title: str = '',
        visibility: str = 'internal',
        uploaded_by=None,
        metadata: Optional[Dict] = None,
        reingest: bool = False,
    ) -> DocumentSource:
        source_hash = hashlib.sha256(data or b'').hexdigest()
        document = DocumentSource.objects.filter(source_hash=source_hash).first()
        if document and document.status == 'completed' and not reingest:
            return document  # idempotent: identical content already ingested

        # update_or_create is race-safe (it retries the get on a unique-constraint
        # IntegrityError), so two concurrent first-time uploads of identical
        # content won't crash with a duplicate source_hash.
        document, _ = DocumentSource.objects.update_or_create(
            source_hash=source_hash,
            defaults={
                'title': title or filename,
                'filename': filename,
                'mime': mime or '',
                'byte_size': len(data or b''),
                'visibility': visibility,
                'metadata': metadata or {},
                'uploaded_by': uploaded_by,
                'status': 'running',
                'error_message': '',
            },
        )

        try:
            outcome = self.pipeline.run(
                data=data,
                filename=filename,
                mime=mime,
                document_id=document.id,
                source_type='document',
                base_metadata={'visibility': visibility, **(metadata or {})},
                title=document.title,
            )
        except Exception as exc:
            document.status = 'failed'
            document.error_message = f'{type(exc).__name__}: {exc}'
            document.save(update_fields=['status', 'error_message', 'updated_at'])
            self._audit(document, action='ingest_failed', actor=uploaded_by)
            logger.warning(
                'rag_ingestion_failed',
                extra={'event': 'rag_ingestion_failed',
                       'document_id': document.id,
                       'error_type': type(exc).__name__},
            )
            return document

        document.status = 'completed'
        document.parser = outcome.parser
        document.chunk_count = outcome.chunk_count
        document.embedded_count = outcome.embedded_count
        document.save(update_fields=[
            'status', 'parser', 'chunk_count', 'embedded_count', 'updated_at',
        ])
        self._audit(document, action='ingest_completed', actor=uploaded_by)
        return document

    def _audit(self, document: DocumentSource, *, action: str, actor=None):
        try:
            from audit.models import AuditEvent

            AuditEvent.log(
                category='kb_ingestion',
                summary=f'RAG document {action}: {document.title}',
                user=actor,
                detail={
                    'document_id': document.id,
                    'action': action,
                    'status': document.status,
                    'parser': document.parser,
                    'chunk_count': document.chunk_count,
                    'embedded_count': document.embedded_count,
                },
            )
        except Exception:
            # Auditing is best-effort and must never break ingestion.
            pass
