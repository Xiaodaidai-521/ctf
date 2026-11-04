"""Boundary-aware text chunking for legal and teaching documents."""

import re
from dataclasses import dataclass, replace
from typing import List


@dataclass(frozen=True)
class TextChunk:
    """A chunk generated from a legal document."""

    clause_key: str
    title: str
    text: str
    order: int
    article_number: str = ''
    chapter: str = ''


class ChunkingService:
    """Split text into bounded windows while retaining citation identity."""

    ARTICLE_PATTERN = re.compile(r'(?m)^(第[零〇一二三四五六七八九十百千万0-9０-９]+条)')
    INLINE_ARTICLE_PATTERN = re.compile(r'(第[零〇一二三四五六七八九十百千万0-9０-９]+条)')

    VERSION = 'boundary-overlap-v3'
    DEFAULT_MAX_CHARS = 1200
    DEFAULT_OVERLAP = 160
    TEACHING_MAX_CHARS = 800
    TEACHING_OVERLAP = 100
    MIN_TAIL_CHARS = 120
    SENTENCE_PATTERN = re.compile(r'[。！？!?；;]+[”’"\']*|\.(?=\s|$)')
    PARAGRAPH_PATTERN = re.compile(r'\n\s*\n')
    SOFT_BOUNDARY_PATTERN = re.compile(r'[，、,：:]+[”’"\']*')
    LINE_PATTERN = re.compile(r'\n')

    @classmethod
    def split_legal_text(
        cls, text: str, max_chars: int = 1200, overlap: int = None,
    ) -> List[TextChunk]:
        """Preserve short articles and split long ones without losing citations."""
        cls._window_options(max_chars, overlap)
        clean_text = (text or '').strip()
        if not clean_text:
            return []

        parts = cls.ARTICLE_PATTERN.split(clean_text)
        chunks = cls._chunks_from_article_parts(parts)
        # Keep the existing fallback for laws whose articles share one line.
        if len(chunks) <= 1:
            parts = cls.INLINE_ARTICLE_PATTERN.split(clean_text)
            chunks = cls._chunks_from_article_parts(parts)
        if not chunks:
            return cls.split_plain_text(clean_text, max_chars=max_chars, overlap=overlap)

        result = []
        for chunk in chunks:
            pieces = cls.split_plain_text(chunk.text, max_chars=max_chars, overlap=overlap)
            for index, piece in enumerate(pieces, start=1):
                result.append(replace(
                    chunk,
                    clause_key=(chunk.clause_key if index == 1 else f'{chunk.clause_key}-part-{index}'),
                    text=piece.text,
                    order=len(result) + 1,
                ))
        return result

    @classmethod
    def _window_options(cls, max_chars, overlap):
        if not isinstance(max_chars, int) or max_chars <= 0:
            raise ValueError('max_chars must be a positive integer')
        if overlap is None:
            overlap = min(cls.DEFAULT_OVERLAP, max_chars // 5)
        if not isinstance(overlap, int) or not 0 <= overlap < max_chars:
            raise ValueError('overlap must satisfy 0 <= overlap < max_chars')
        return overlap

    @classmethod
    def tail_tolerance(cls, max_chars):
        """Only normal-sized windows may absorb up to 119 trailing characters."""
        return cls.MIN_TAIL_CHARS - 1 if max_chars >= cls.MIN_TAIL_CHARS else 0

    @classmethod
    def split_plain_text(
        cls, text: str, max_chars: int = 1200, overlap: int = None,
    ) -> List[TextChunk]:
        """Prefer sentence ends, then paragraphs, commas and line boundaries.

        The final window may exceed max_chars by at most tail_tolerance to avoid
        a tiny orphan. Small diagnostic windows remain strictly bounded. Overlap
        is in source characters; every window must advance beyond the last end.
        """
        overlap = cls._window_options(max_chars, overlap)
        clean_text = (text or '').strip()
        chunks = []
        start, previous_end = 0, 0
        tolerance = cls.tail_tolerance(max_chars)
        while start < len(clean_text):
            end = min(start + max_chars, len(clean_text))
            if end < len(clean_text):
                minimum = max(
                    start + min(cls.MIN_TAIL_CHARS, max_chars // 2),
                    previous_end + 1, start + overlap + 1,
                )
                for pattern in (
                    cls.SENTENCE_PATTERN, cls.PARAGRAPH_PATTERN,
                    cls.SOFT_BOUNDARY_PATTERN, cls.LINE_PATTERN,
                ):
                    boundaries = [
                        match.end() for match in pattern.finditer(clean_text, start, end)
                        if match.end() >= minimum
                    ]
                    if boundaries:
                        end = boundaries[-1]
                        break
                # Count the new suffix, not its overlapping context. This also
                # avoids almost-duplicate final chunks with large overlap.
                if (len(clean_text) - end < cls.MIN_TAIL_CHARS
                        and len(clean_text) - start <= max_chars + tolerance):
                    end = len(clean_text)
            chunk_text = clean_text[start:end].strip()
            if chunk_text:
                order = len(chunks) + 1
                chunks.append(TextChunk(
                    clause_key=f'chunk-{order}', title=f'Chunk {order}',
                    text=chunk_text, order=order,
                ))
            if end == len(clean_text):
                break
            previous_end = end
            start = end - overlap
        return chunks

    @classmethod
    def _chunks_from_article_parts(cls, parts: List[str]) -> List[TextChunk]:
        if len(parts) <= 1:
            return []

        prefix = parts[0].strip()
        chunks: List[TextChunk] = []
        seen_keys = {}
        for index in range(1, len(parts), 2):
            article = parts[index].strip()
            body = (parts[index + 1] if index + 1 < len(parts) else '').strip()
            chunk_text = f'{article}{body}'.strip()
            if not chunk_text:
                continue

            seen_keys[article] = seen_keys.get(article, 0) + 1
            clause_key = article if seen_keys[article] == 1 else f'{article}-{seen_keys[article]}'
            order = len(chunks) + 1
            chunks.append(TextChunk(
                clause_key=clause_key,
                title=article,
                text=chunk_text,
                order=order,
                article_number=article,
                chapter=prefix[:100] if order == 1 else '',
            ))
        return chunks
