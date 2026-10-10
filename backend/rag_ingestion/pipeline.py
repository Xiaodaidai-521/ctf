"""Ingestion orchestrator. Depends only on app abstractions, not third parties."""

from dataclasses import dataclass, field
from typing import Dict, Optional

from .chunking import StructureAwareChunker
from .cleaning import clean_text
from .registry import select_parser


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

    def __init__(self, *, chunker=None, embedder=None, repository=None, parser_selector=None):
        self.chunker = chunker or StructureAwareChunker()
        self._embedder = embedder
        self._repository = repository
        self.parser_selector = parser_selector or select_parser

    @property
    def embedder(self):
        if self._embedder is None:
            from .adapters.embedder_legalkb import LegalKbEmbedder

            self._embedder = LegalKbEmbedder()
        return self._embedder

    @property
    def repository(self):
        if self._repository is None:
            from .adapters.repository_legalkb import LegalKbChunkRepository

            self._repository = LegalKbChunkRepository()
        return self._repository

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
    ) -> IngestionOutcome:
        parser = self.parser_selector(filename, mime)
        if parser is None:
            raise UnsupportedFormatError(f'No parser available for: {filename} ({mime})')

        parsed = parser.parse(data, filename=filename, mime=mime)
        text = clean_text(parsed.text)
        if not text.strip():
            raise EmptyDocumentError(f'No extractable text in: {filename}')

        metadata = {
            'source_type': source_type,
            'document_id': document_id,
            'filename': filename,
            'parser': parser.name,
            'title': title or filename,
        }
        metadata.update(parsed.metadata or {})
        if base_metadata:
            metadata.update(base_metadata)

        chunks = self.chunker.split(text, metadata={})
        embedded = self.embedder.embed(chunks)
        stored = self.repository.replace(
            document_id=document_id,
            source_type=source_type,
            embedded=embedded,
            base_metadata=metadata,
        )
        return IngestionOutcome(
            parser=parser.name,
            chunk_count=len(chunks),
            embedded_count=stored,
            metadata=metadata,
        )
