"""Text normalization/cleaning before chunking."""

import re


_MULTI_BLANKLINE = re.compile(r'\n{3,}')
_TRAILING_WS = re.compile(r'[ \t]+(\n)')


def clean_text(text: str) -> str:
    """Normalize whitespace while keeping heading/paragraph structure."""
    if not text:
        return ''
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    normalized = _TRAILING_WS.sub(r'\1', normalized)
    normalized = _MULTI_BLANKLINE.sub('\n\n', normalized)
    return normalized.strip()
