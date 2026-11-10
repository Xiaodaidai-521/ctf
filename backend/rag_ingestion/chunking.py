"""Structure-aware chunking.

Primary strategy reuses the project's existing ``legal_kb.ChunkingService``
(zero new dependency). If ``langchain-text-splitters`` (MIT, standalone small
package) is installed, a Markdown-header-aware splitter is used for richer
heading metadata. Everything degrades gracefully to the built-in splitter.
"""

import logging
from typing import Dict, List

from django.conf import settings

from .interfaces import Chunk

logger = logging.getLogger(__name__)


class StructureAwareChunker:
    """Split Markdown/plain text into chunks, preserving heading paths."""

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = int(
            chunk_size or getattr(settings, 'RAG_INGESTION_CHUNK_SIZE', 1000)
        )
        self.chunk_overlap = int(
            chunk_overlap if chunk_overlap is not None
            else getattr(settings, 'RAG_INGESTION_CHUNK_OVERLAP', 120)
        )

    def split(self, text: str, *, metadata: Dict = None) -> List[Chunk]:
        base_metadata = dict(metadata or {})
        clean = (text or '').strip()
        if not clean:
            return []
        chunks = self._split_with_langchain(clean, base_metadata)
        if chunks is None:
            chunks = self._split_with_builtin(clean, base_metadata)
        return chunks

    def _split_with_langchain(self, text: str, base_metadata: Dict):
        if not getattr(settings, 'RAG_INGESTION_USE_LANGCHAIN_SPLITTER', True):
            return None
        try:
            from langchain_text_splitters import (
                MarkdownHeaderTextSplitter,
                RecursiveCharacterTextSplitter,
            )
        except Exception:
            # Optional dependency absent: fall back to the built-in splitter.
            return None

        try:
            headers = [('#', 'h1'), ('##', 'h2'), ('###', 'h3')]
            header_docs = MarkdownHeaderTextSplitter(
                headers_to_split_on=headers
            ).split_text(text)
            recursive = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
            documents = recursive.split_documents(header_docs)
            chunks = []
            for order, doc in enumerate(documents, start=1):
                heading_path = [
                    value for key, value in doc.metadata.items()
                    if key in {'h1', 'h2', 'h3'} and value
                ]
                metadata = {**base_metadata, 'heading_path': heading_path}
                chunks.append(Chunk(
                    text=doc.page_content.strip(),
                    order=order,
                    title=heading_path[-1] if heading_path else '',
                    metadata=metadata,
                ))
            chunks = [chunk for chunk in chunks if chunk.text]
            return chunks or None
        except Exception as exc:
            logger.warning(
                'rag_ingestion_langchain_splitter_failed',
                extra={'event': 'rag_ingestion_langchain_splitter_failed',
                       'error_type': type(exc).__name__},
            )
            return None

    def _split_with_builtin(self, text: str, base_metadata: Dict) -> List[Chunk]:
        from legal_kb.services.chunking_service import ChunkingService

        pieces = ChunkingService.split_plain_text(text, max_chars=self.chunk_size)
        chunks = []
        for piece in pieces:
            chunks.append(Chunk(
                text=piece.text,
                order=piece.order,
                title=piece.title,
                metadata={**base_metadata, 'chunk_key': piece.clause_key},
            ))
        return chunks
