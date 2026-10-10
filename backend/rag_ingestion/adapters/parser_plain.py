"""Plain-text / Markdown / HTML parser (no mandatory third-party deps)."""

import re
from typing import Set

from ..interfaces import ParsedDocument

_TAG_RE = re.compile(r'<[^>]+>')
_SCRIPT_STYLE_RE = re.compile(r'<(script|style)[^>]*>.*?</\1>', re.I | re.S)


class PlainTextParser:
    """Decode text-like formats; strip HTML tags when needed."""

    name = 'plain'
    EXTENSIONS: Set[str] = {'.md', '.markdown', '.txt', '.text', '.html', '.htm', '.csv', '.log', '.json'}
    HTML_EXTENSIONS: Set[str] = {'.html', '.htm'}

    def supports(self, *, filename: str, mime: str) -> bool:
        lowered = (filename or '').lower()
        if any(lowered.endswith(ext) for ext in self.EXTENSIONS):
            return True
        return (mime or '').startswith('text/')

    def parse(self, data: bytes, *, filename: str, mime: str) -> ParsedDocument:
        text = self._decode(data)
        lowered = (filename or '').lower()
        is_html = any(lowered.endswith(ext) for ext in self.HTML_EXTENSIONS) or 'html' in (mime or '')
        if is_html:
            text = self._html_to_text(text)
        return ParsedDocument(text=text, metadata={'parser': self.name})

    def _decode(self, data: bytes) -> str:
        for encoding in ('utf-8-sig', 'utf-8', 'gb18030', 'latin-1'):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode('utf-8', errors='ignore')

    def _html_to_text(self, html: str) -> str:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style']):
                tag.decompose()
            return soup.get_text('\n')
        except Exception:
            stripped = _SCRIPT_STYLE_RE.sub(' ', html)
            return _TAG_RE.sub(' ', stripped)
