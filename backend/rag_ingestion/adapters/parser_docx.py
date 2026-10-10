"""Word .docx parser: python-docx if present, else a zipfile XML fallback."""

import io
import re
import zipfile
from typing import Set

from ..interfaces import ParsedDocument

_XML_PARA_RE = re.compile(r'<w:p\b[^>]*>.*?</w:p>', re.S)
_XML_TEXT_RE = re.compile(r'<w:t\b[^>]*>(.*?)</w:t>', re.S)
_XML_TAG_RE = re.compile(r'<[^>]+>')


class DocxParser:
    """Extract text from .docx without requiring a heavy dependency."""

    name = 'docx'
    EXTENSIONS: Set[str] = {'.docx'}

    def supports(self, *, filename: str, mime: str) -> bool:
        lowered = (filename or '').lower()
        if any(lowered.endswith(ext) for ext in self.EXTENSIONS):
            return True
        return 'wordprocessingml' in (mime or '')

    def parse(self, data: bytes, *, filename: str, mime: str) -> ParsedDocument:
        # python-docx only reads body paragraphs (misses tables/headers/footers).
        # If it yields nothing usable, fall back to the zipfile XML scan which
        # recovers all <w:t> runs (tables included).
        text = self._with_python_docx(data) or ''
        if not text.strip():
            text = self._with_zipfile(data) or ''
        return ParsedDocument(text=text, metadata={'parser': self.name})

    def _with_python_docx(self, data: bytes):
        try:
            import docx  # python-docx exposes docx.Document
        except Exception:
            return None
        try:
            document = docx.Document(io.BytesIO(data))
        except Exception:
            return None
        paragraphs = [p.text for p in getattr(document, 'paragraphs', [])]
        return '\n'.join(part for part in paragraphs if part is not None)

    def _with_zipfile(self, data: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                xml = archive.read('word/document.xml').decode('utf-8', errors='ignore')
        except Exception:
            return ''
        paragraphs = []
        for para in _XML_PARA_RE.findall(xml):
            texts = _XML_TEXT_RE.findall(para)
            line = ''.join(_XML_TAG_RE.sub('', fragment) for fragment in texts)
            if line.strip():
                paragraphs.append(line)
        return '\n'.join(paragraphs)
