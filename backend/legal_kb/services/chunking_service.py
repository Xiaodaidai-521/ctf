"""Clause-aware text chunking for legal documents."""

import re
from dataclasses import dataclass
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
    """Split legal text into clause-like chunks with conservative fallbacks."""

    ARTICLE_PATTERN = re.compile(r'(?m)^(第[零〇一二三四五六七八九十百千万0-9０-９]+条)')
    INLINE_ARTICLE_PATTERN = re.compile(r'(第[零〇一二三四五六七八九十百千万0-9０-９]+条)')

    @classmethod
    def split_legal_text(cls, text: str, max_chars: int = 1200) -> List[TextChunk]:
        """Split text by Chinese article markers, falling back to fixed windows."""
        clean_text = (text or '').strip()
        if not clean_text:
            return []

        parts = cls.ARTICLE_PATTERN.split(clean_text)
        chunks: List[TextChunk] = []
        chunks = cls._chunks_from_article_parts(parts)
        if len(chunks) > 1:
            return chunks

        parts = cls.INLINE_ARTICLE_PATTERN.split(clean_text)
        chunks = cls._chunks_from_article_parts(parts)
        if chunks:
            return chunks

        chunks = []
        for order, start in enumerate(range(0, len(clean_text), max_chars), start=1):
            chunk_text = clean_text[start:start + max_chars].strip()
            if chunk_text:
                chunks.append(TextChunk(
                    clause_key=f'chunk-{order}',
                    title=f'Chunk {order}',
                    text=chunk_text,
                    order=order,
                ))
        return chunks

    @classmethod
    def split_plain_text(cls, text: str, max_chars: int = 1200) -> List[TextChunk]:
        """Split non-legal platform content without interpreting article markers."""
        clean_text = (text or '').strip()
        if not clean_text:
            return []

        chunks = []
        for order, start in enumerate(range(0, len(clean_text), max_chars), start=1):
            chunk_text = clean_text[start:start + max_chars].strip()
            if chunk_text:
                chunks.append(TextChunk(
                    clause_key=f'chunk-{order}',
                    title=f'Chunk {order}',
                    text=chunk_text,
                    order=order,
                ))
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
