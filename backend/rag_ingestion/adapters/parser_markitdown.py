"""Generic fallback parser via Microsoft markitdown (MIT), imported lazily.

markitdown converts many formats (docx, pptx, xlsx, pdf, html, ...) to
Markdown. It is optional: when it is not installed this adapter simply reports
that it cannot handle the file, and the registry moves on.
"""

import os
import tempfile
from typing import Set

from ..interfaces import ParsedDocument


class MarkItDownParser:
    name = 'markitdown'
    # Broad fallback coverage; only used when markitdown is installed.
    EXTENSIONS: Set[str] = {
        '.docx', '.pptx', '.xlsx', '.xls', '.pdf', '.html', '.htm', '.csv', '.epub',
    }

    def __init__(self):
        self._available = None

    def _is_available(self) -> bool:
        if self._available is None:
            try:
                import markitdown  # noqa: F401
                self._available = True
            except Exception:
                self._available = False
        return self._available

    def supports(self, *, filename: str, mime: str) -> bool:
        if not self._is_available():
            return False
        lowered = (filename or '').lower()
        return any(lowered.endswith(ext) for ext in self.EXTENSIONS)

    def parse(self, data: bytes, *, filename: str, mime: str) -> ParsedDocument:
        from markitdown import MarkItDown

        suffix = ''
        lowered = (filename or '').lower()
        if '.' in lowered:
            suffix = lowered[lowered.rfind('.'):]

        # Write and CLOSE the temp file before converting. markitdown reopens the
        # file by path; on Windows a still-open handle would raise PermissionError
        # (flush() alone does not release the lock). delete=False + manual cleanup
        # keeps this cross-platform.
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temp_path = handle.name
        try:
            handle.write(data)
            handle.close()
            result = MarkItDown().convert(temp_path)
            text = getattr(result, 'text_content', '') or ''
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        return ParsedDocument(text=text, metadata={'parser': self.name})

