"""Structure-aware chunking.

Both the optional LangChain path and the built-in fallback use original-text
windows from ``legal_kb.ChunkingService`` with the same Markdown heading paths.
The built-in path does not require any third-party Markdown dependency.
"""

import logging
import re
from bisect import bisect_left, bisect_right
from typing import Dict, List

from django.conf import settings

from .interfaces import Chunk

logger = logging.getLogger(__name__)


class StructureAwareChunker:
    """Split Markdown/plain text into chunks, preserving heading paths."""

    HEADING = re.compile(r'^ {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)$')
    FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = int(
            chunk_size if chunk_size is not None else getattr(settings, 'RAG_INGESTION_CHUNK_SIZE', 800)
        )
        self.chunk_overlap = int(
            chunk_overlap if chunk_overlap is not None
            else getattr(settings, 'RAG_INGESTION_CHUNK_OVERLAP', 100)
        )
        from legal_kb.services.chunking_service import ChunkingService
        ChunkingService.validate_window(self.chunk_size, self.chunk_overlap)

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
                separators=['。', '！', '？', '；', '!', '?', ';', '\n', '，', '、', ',', ' ', ''],
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
            # Use original-text windows for identical overlap/tail handling in
            # both backends. Never reconstruct source text from header fragments.
            return self._split_with_builtin(text, base_metadata) if chunks else None
        except Exception as exc:
            logger.warning(
                'rag_ingestion_langchain_splitter_failed',
                extra={'event': 'rag_ingestion_langchain_splitter_failed',
                       'error_type': type(exc).__name__},
            )
            return None

    @classmethod
    def _markdown_structure(cls, text: str):
        """Locate heading paths and body spans without rewriting the source."""
        headings = []
        body_spans = []
        stack = []
        fence = None
        offset = 0
        for line in text.splitlines(keepends=True):
            content = line.rstrip('\r\n')
            delimiter = cls.FENCE.match(content)
            is_heading = False
            if fence is not None:
                if (delimiter and delimiter.group(1)[0] == fence[0]
                        and len(delimiter.group(1)) >= len(fence)
                        and not delimiter.group(2).strip()):
                    fence = None
            elif delimiter and (delimiter.group(1)[0] == '~' or '`' not in delimiter.group(2)):
                fence = delimiter.group(1)
            else:
                match = cls.HEADING.match(content)
                if match:
                    level = len(match.group(1))
                    title = re.sub(r'(?:^|[ \t]+)#+[ \t]*$', '', match.group(2) or '').strip()
                    while stack and stack[-1][0] >= level:
                        stack.pop()
                    stack.append((level, title))
                    headings.append((offset, tuple(title for _, title in stack if title)))
                    is_heading = True
            if not is_heading and content.strip():
                body_spans.append((offset + len(content) - len(content.lstrip()),
                                   offset + len(content.rstrip())))
            offset += len(line)
        return headings, body_spans

    def _split_with_builtin(self, text: str, base_metadata: Dict) -> List[Chunk]:
        from legal_kb.services.chunking_service import ChunkingService

        pieces = ChunkingService.split_plain_text(text, max_chars=self.chunk_size, overlap=self.chunk_overlap)
        headings, body_spans = self._markdown_structure(text)
        heading_starts = [position for position, _ in headings]
        body_ends = [end for _, end in body_spans]
        chunks = []
        start = 0
        for piece in pieces:
            end = start + len(piece.text)
            first_heading = max(0, bisect_right(heading_starts, start) - 1)
            last_heading = bisect_left(heading_starts, end)
            paths = list(dict.fromkeys(path for _, path in headings[first_heading:last_heading]))

            # Consecutive parent/child headings describe the first body text.
            # Keep all crossed sections separately, including the overlap's path.
            body_index = bisect_right(body_ends, start)
            position = end - 1
            if body_index < len(body_spans) and body_spans[body_index][0] < end:
                position = max(start, body_spans[body_index][0])
            heading_index = bisect_right(heading_starts, position) - 1
            heading_path = list(headings[heading_index][1]) if heading_index >= 0 else []
            chunks.append(Chunk(
                text=piece.text,
                order=piece.order,
                title=heading_path[-1] if heading_path else piece.title,
                metadata={**base_metadata, 'chunk_key': piece.clause_key,
                          'heading_path': heading_path, 'heading_paths': [list(path) for path in paths],
                          'chunking_version': ChunkingService.VERSION},
            ))
            start = end - self.chunk_overlap
        return chunks
