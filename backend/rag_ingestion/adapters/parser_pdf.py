"""PDF parser: pdfplumber (MIT) preferred, PyMuPDF (AGPL) optional fallback.

Note on licensing: PyMuPDF is AGPL-3.0. It is only used if already installed
and is imported lazily, so the default install stays MIT/Apache-only.
"""

import io
from typing import Set

from ..interfaces import ParsedDocument


class PdfParser:
    name = 'pdf'
    EXTENSIONS: Set[str] = {'.pdf'}

    def supports(self, *, filename: str, mime: str) -> bool:
        lowered = (filename or '').lower()
        return lowered.endswith('.pdf') or 'pdf' in (mime or '')

    def parse(self, data: bytes, *, filename: str, mime: str) -> ParsedDocument:
        text = self._with_pdfplumber(data)
        if text is None:
            text = self._with_pymupdf(data)
        if text is None:
            raise RuntimeError(
                'No PDF parser available. Install pdfplumber (MIT) to enable PDF ingestion.'
            )
        return ParsedDocument(text=text, metadata={'parser': self.name})

    def _with_pdfplumber(self, data: bytes):
        try:
            import pdfplumber
        except Exception:
            return None
        try:
            pages = []
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for index, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text() or ''
                    if page_text.strip():
                        pages.append(f'[page {index}]\n{page_text}')
            text = '\n\n'.join(pages)
            return text or None  # empty -> let the next parser try
        except Exception:
            return None  # corrupt/encrypted PDF -> fall through to pymupdf

    def _with_pymupdf(self, data: bytes):
        try:
            import fitz  # PyMuPDF
        except Exception:
            return None
        try:
            pages = []
            with fitz.open(stream=data, filetype='pdf') as doc:
                for index, page in enumerate(doc, start=1):
                    page_text = page.get_text() or ''
                    if page_text.strip():
                        pages.append(f'[page {index}]\n{page_text}')
            text = '\n\n'.join(pages)
            return text or None
        except Exception:
            return None
