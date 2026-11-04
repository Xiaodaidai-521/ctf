"""Structure-aware chunking.

Primary strategy reuses the project's existing ``legal_kb.ChunkingService``
(zero new dependency). If ``langchain-text-splitters`` (MIT, standalone small
package) is installed, a Markdown-header-aware splitter is used for richer
heading metadata. Everything degrades gracefully to the built-in splitter.
"""

import logging
import re
from typing import Dict, List

from django.conf import settings

from legal_kb.services.chunking_service import ChunkingService

from .interfaces import Chunk

logger = logging.getLogger(__name__)


class StructureAwareChunker:
    """Split Markdown/plain text into chunks, preserving heading paths."""

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = int(
            chunk_size if chunk_size is not None else getattr(
                settings, 'RAG_INGESTION_CHUNK_SIZE', ChunkingService.TEACHING_MAX_CHARS,
            )
        )
        self.chunk_overlap = int(
            chunk_overlap if chunk_overlap is not None else getattr(
                settings, 'RAG_INGESTION_CHUNK_OVERLAP', ChunkingService.TEACHING_OVERLAP,
            )
        )
        ChunkingService._window_options(self.chunk_size, self.chunk_overlap)

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
                separators=['\n\n', '\n', '。', '！', '？', '；', '!', '?', ';', '，', '、', ',', ' ', ''],
                keep_separator='end',
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
            # Header/recursive splitting can leave isolated headings or tiny
            # section tails. Re-window the original text rather than joining
            # overlapping chunks (which would duplicate content).
            minimum = min(ChunkingService.MIN_TAIL_CHARS, self.chunk_size)
            if len(text) >= minimum and any(len(chunk.text) < minimum for chunk in chunks):
                return None
            return chunks or None
        except Exception as exc:
            logger.warning(
                'rag_ingestion_langchain_splitter_failed',
                extra={'event': 'rag_ingestion_langchain_splitter_failed',
                       'error_type': type(exc).__name__},
            )
            return None

    def _split_with_builtin(self, text: str, base_metadata: Dict) -> List[Chunk]:
        pieces = ChunkingService.split_plain_text(
            text, max_chars=self.chunk_size, overlap=self.chunk_overlap,
        )
        headings = self._markdown_headings(text)
        chunks = []
        previous_end = 0
        for piece in pieces:
            start = text.find(piece.text, max(0, previous_end - self.chunk_overlap))
            end = start + len(piece.text)
            previous_end = end
            active = []
            paths = []
            for position, path in headings:
                if position <= start:
                    active = path
                elif position < end and path not in paths:
                    paths.append(path)
            if active and active not in paths:
                paths.insert(0, active)
            heading_path = paths[0] if paths else []
            chunks.append(Chunk(
                text=piece.text,
                order=piece.order,
                title=heading_path[-1] if heading_path else piece.title,
                metadata={
                    **base_metadata, 'chunk_key': piece.clause_key,
                    'heading_path': heading_path, 'heading_paths': paths,
                },
            ))
        return chunks

    @staticmethod
    def _markdown_headings(text):
        """Keep heading context even when small sections use built-in windows."""
        headings, stack = [], []
        offset = 0
        fence = ''
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            marker = re.match(r'^(`{3,}|~{3,})', stripped)
            if marker:
                token = marker.group()
                if not fence:
                    fence = token
                elif token[0] == fence[0] and len(token) >= len(fence):
                    fence = ''
            elif not fence:
                match = re.match(r'^(#{1,3})\s+(.+?)\s*$', stripped)
                if match:
                    level = len(match[1])
                    title = re.sub(r'\s+#+\s*$', '', match[2])
                    stack = [(depth, value) for depth, value in stack if depth < level]
                    stack.append((level, title))
                    headings.append((offset, [value for _, value in stack]))
            offset += len(line)
        return headings
