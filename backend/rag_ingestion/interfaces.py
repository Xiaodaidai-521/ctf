"""Pipeline contracts. The orchestrator depends only on these abstractions.

Keeping third-party libraries behind these Protocols is what lets us swap a
parser (markitdown -> docling -> pdfplumber) or the vector backend without
touching ``pipeline.py``.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, runtime_checkable
from uuid import UUID


class SupersededIngestionError(RuntimeError):
    """An older ingestion attempt no longer owns this document."""


@dataclass
class ParsedDocument:
    """Normalized output of a parser: Markdown-ish text plus structure hints."""

    text: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class Chunk:
    """A retrievable unit of text with ordering and provenance metadata."""

    text: str
    order: int
    title: str = ''
    metadata: Dict = field(default_factory=dict)


@dataclass
class EmbeddedChunk:
    """A chunk plus its semantic vector and the portable local vector."""

    chunk: Chunk
    vector: List[float]
    local_vector: List[float]
    model: str
    dimension: int


@runtime_checkable
class DocumentParser(Protocol):
    """Turn raw bytes of one format into normalized text."""

    def supports(self, *, filename: str, mime: str) -> bool: ...

    def parse(self, data: bytes, *, filename: str, mime: str) -> ParsedDocument: ...


@runtime_checkable
class TextChunker(Protocol):
    """Split normalized text into retrievable chunks."""

    def split(self, text: str, *, metadata: Dict) -> List[Chunk]: ...


@runtime_checkable
class Embedder(Protocol):
    """Embed chunk texts into vectors."""

    def embed(self, chunks: List[Chunk]) -> List[EmbeddedChunk]: ...


@runtime_checkable
class ChunkRepository(Protocol):
    """Persist embedded chunks into the shared vector store."""

    def replace(
        self, *, document_id: int, source_type: str, embedded: List[EmbeddedChunk],
        base_metadata: Dict, ingestion_token: Optional[UUID] = None,
    ) -> int: ...
