"""Sentence-aware overlapping windows with stable legal article citations."""

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
    """Keep complete text, bounded tails and legal article identities."""

    VERSION = 'sentence-overlap-v3'
    TEACHING_MAX_CHARS = 800
    TEACHING_OVERLAP = 100
    LEGAL_MAX_CHARS = 1200
    LEGAL_OVERLAP = 160
    MIN_TAIL = 120

    @classmethod
    def tail_tolerance(cls, max_chars):
        return cls.MIN_TAIL - 1 if max_chars >= cls.MIN_TAIL else 0

    ARTICLE_PATTERN = re.compile(r'(?m)^(第[零〇一二三四五六七八九十百千万0-9０-９]+条)')
    INLINE_ARTICLE_PATTERN = re.compile(r'(?:^|(?<=[。！？!?]))(第[零〇一二三四五六七八九十百千万0-9０-９]+条)')
    SENTENCE = re.compile(r'[。！？!?；;]+[”’"\']*|\.(?=\s|$)')
    COMMA = re.compile(r'[，、,]')

    @staticmethod
    def validate_window(max_chars, overlap):
        if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
            raise ValueError('Window must be positive and overlap smaller than the window.')

    @classmethod
    def _windows(cls, text, max_chars, overlap):
        cls.validate_window(max_chars, overlap)
        start, previous_end = 0, 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if len(text) - end <= cls.tail_tolerance(max_chars):
                end = len(text)
            elif end < len(text):
                minimum = max(previous_end + 1, start + overlap + 1)
                for pattern in (cls.SENTENCE, cls.COMMA):
                    boundaries = [match.end() for match in pattern.finditer(text, start, end)
                                  if match.end() >= minimum]
                    if boundaries:
                        end = boundaries[-1]
                        break
                if len(text) - end <= cls.tail_tolerance(max_chars) and len(text) - start <= max_chars + cls.tail_tolerance(max_chars):
                    end = len(text)
            yield text[start:end]
            if end == len(text):
                break
            previous_end = end
            start = end - overlap

    @classmethod
    def split_legal_text(cls, text: str, max_chars: int = LEGAL_MAX_CHARS,
                         overlap: int = LEGAL_OVERLAP) -> List[TextChunk]:
        """Split text by Chinese article markers, falling back to fixed windows."""
        cls.validate_window(max_chars, overlap)
        clean_text = (text or '').strip()
        if not clean_text:
            return []

        parts = cls.ARTICLE_PATTERN.split(clean_text)
        if len(parts) <= 3:
            inline = cls.INLINE_ARTICLE_PATTERN.split(clean_text)
            if len(inline) > len(parts):
                parts = inline
        if len(parts) < 3:
            return cls.split_plain_text(clean_text, max_chars=max_chars, overlap=overlap)
        return cls._chunks_from_article_parts(parts, max_chars, overlap)

    @classmethod
    def split_plain_text(cls, text: str, max_chars: int = TEACHING_MAX_CHARS,
                         overlap: int = TEACHING_OVERLAP) -> List[TextChunk]:
        """Split non-legal platform content without interpreting article markers."""
        cls.validate_window(max_chars, overlap)
        clean_text = (text or '').strip()
        return [TextChunk(f'chunk-{order}', f'Chunk {order}', chunk, order)
                for order, chunk in enumerate(cls._windows(clean_text, max_chars, overlap), 1)]

    @classmethod
    def _chunks_from_article_parts(cls, parts: List[str], max_chars=LEGAL_MAX_CHARS,
                                  overlap=LEGAL_OVERLAP) -> List[TextChunk]:
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
            for part, window in enumerate(cls._windows(chunk_text, max_chars, overlap), 1):
                key = clause_key if part == 1 else f'{clause_key}-part-{part}'
                chunks.append(TextChunk(key, article, window, len(chunks) + 1, article, prefix[:100]))
        return chunks
