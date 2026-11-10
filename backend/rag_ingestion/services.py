"""Facade coordinating DocumentSource lifecycle with the ingestion pipeline."""

import hashlib
import logging
from typing import Dict, Optional
from uuid import uuid4

from django.db import transaction

from data_security.adapters.django.rag import RagProtectionError, protect_rag, rag_protection_enabled

from .interfaces import SupersededIngestionError
from .models import DocumentSource
from .pipeline import IngestionPipeline
from .registry import get_pipeline

logger = logging.getLogger(__name__)


class IngestionService:
    """Register an uploaded document, run the pipeline, track status + audit."""

    def __init__(self, pipeline: Optional[IngestionPipeline] = None):
        self.pipeline = pipeline if pipeline is not None else get_pipeline()

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
        if rag_protection_enabled() and not (
            uploaded_by and uploaded_by.is_authenticated and uploaded_by.is_active
            and (uploaded_by.is_staff or getattr(uploaded_by, 'role', '') == 'admin')
        ):
            raise RagProtectionError('RAG_AUTHORIZATION_REQUIRED')
        headers = protect_rag({'title': title or filename, 'filename': filename,
                               'mime': mime or '', 'metadata': metadata or {}},
                              object_ref='rag/upload-' + source_hash, object_version='v1', outlet='rag')
        # Serialize task claims, not parsing or remote embedding. get_or_create
        # retries a concurrent unique-key insert; the row lock then protects the
        # completed check and assignment of a new task token together.
        with transaction.atomic():
            document, _ = DocumentSource.objects.select_for_update().get_or_create(
                source_hash=source_hash,
            )
            if document.status == 'completed' and not reingest:
                return document
            token = uuid4()
            document.title = headers['title']
            document.filename = headers['filename']
            document.mime = headers['mime']
            document.byte_size = len(data or b'')
            document.visibility = visibility
            document.metadata = headers['metadata']
            document.uploaded_by = uploaded_by
            document.status = 'running'
            document.ingestion_token = token
            document.error_message = ''
            document.save()

        try:
            outcome = self.pipeline.run(
                data=data,
                filename=filename,
                mime=mime,
                document_id=document.id,
                source_type='document',
                base_metadata={**headers['metadata'], 'visibility': visibility},
                title=document.title,
                ingestion_token=token,
            )
        except SupersededIngestionError:
            document.refresh_from_db()
            return document
        except Exception as exc:
            document, updated = self._finish(
                document.id, token, status='failed',
                error_message=(f'{type(exc).__name__}: RAG_OPERATION_FAILED' if rag_protection_enabled()
                               else f'{type(exc).__name__}: {exc}'),
            )
            if updated:
                self._audit(document, action='ingest_failed', actor=uploaded_by)
                logger.warning(
                    'rag_ingestion_failed',
                    extra={'event': 'rag_ingestion_failed',
                           'document_id': document.id,
                           'error_type': type(exc).__name__},
                )
            return document

        document, updated = self._finish(
            document.id, token, status='completed', parser=outcome.parser,
            chunk_count=outcome.chunk_count, embedded_count=outcome.embedded_count,
            title=outcome.metadata['title'], filename=outcome.metadata['filename'], metadata=outcome.metadata,
            error_message='',
        )
        if updated:
            self._audit(document, action='ingest_completed', actor=uploaded_by)
        return document

    @staticmethod
    def _finish(document_id, token, **changes):
        """Only the current attempt may publish its state and statistics."""
        with transaction.atomic():
            document = DocumentSource.objects.select_for_update().get(pk=document_id)
            if document.ingestion_token != token or document.status != 'running':
                return document, False
            for name, value in changes.items():
                setattr(document, name, value)
            document.save(update_fields=[*changes, 'updated_at'])
            return document, True

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
