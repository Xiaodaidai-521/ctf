"""Ingestion orchestrator. Depends only on app abstractions, not third parties."""

from dataclasses import dataclass, field
from typing import Dict, Optional
from uuid import UUID

from .cleaning import clean_text


class UnsupportedFormatError(ValueError):
    """Raised when no registered parser can handle the uploaded file."""


class EmptyDocumentError(ValueError):
    """Raised when parsing yields no extractable text."""


@dataclass
class IngestionOutcome:
    parser: str
    chunk_count: int
    embedded_count: int
    metadata: Dict = field(default_factory=dict)


class IngestionPipeline:
    """loader(given bytes) -> parse -> clean -> chunk -> embed -> store."""

    def __init__(self, *, chunker, embedder, repository, parser_selector, protect):
        self.chunker, self.embedder, self.repository = chunker, embedder, repository
        self.parser_selector, self.protect = parser_selector, protect

    def run(
        self,
        *,
        data: bytes,
        filename: str,
        document_id: int,
        mime: str = '',
        source_type: str = 'document',
        base_metadata: Optional[Dict] = None,
        title: str = '',
        ingestion_token: Optional[UUID] = None,
    ) -> IngestionOutcome:
        parser = self.parser_selector(filename, mime)
        if parser is None:
            raise UnsupportedFormatError('RAG_FORMAT_UNSUPPORTED')

        parsed = parser.parse(data, filename=filename, mime=mime)
        text = clean_text(parsed.text)
        if not text.strip():
            raise EmptyDocumentError('RAG_TEXT_EMPTY')

        metadata = {
            **(parsed.metadata or {}),
            **(base_metadata or {}),
            'source_type': source_type,
            'document_id': document_id,
            'filename': filename,
            'parser': parser.name,
            'title': title or filename,
        }
        protected = self.protect({'text': text, 'metadata': metadata},
            object_ref=f'rag/document-{document_id}',
            object_version=str(ingestion_token) if ingestion_token is not None else 'unversioned', outlet='rag')
        text, metadata = protected['text'], protected['metadata']
        chunks = self.chunker.split(text, metadata={})
        embedded = self.embedder.embed(chunks)
        # Keep legacy/custom repositories compatible for unversioned direct runs.
        ownership = {'ingestion_token': ingestion_token} if ingestion_token is not None else {}
        stored = self.repository.replace(
            document_id=document_id,
            source_type=source_type,
            embedded=embedded,
            base_metadata=metadata,
            **ownership,
        )
        return IngestionOutcome(
            parser=parser.name,
            chunk_count=len(chunks),
            embedded_count=stored,
            metadata=metadata,
        )
