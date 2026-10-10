"""Parser registry: choose a parser by filename/MIME, with graceful fallback.

Default priority keeps dependency-free parsers first; the optional markitdown
fallback only wins for formats the built-in parsers do not claim (and only when
markitdown is installed).
"""

import logging
from typing import List, Optional

from django.conf import settings
from django.utils.module_loading import import_string

from .interfaces import DocumentParser

logger = logging.getLogger(__name__)

DEFAULT_PARSER_PATHS = [
    'rag_ingestion.adapters.parser_plain.PlainTextParser',
    'rag_ingestion.adapters.parser_docx.DocxParser',
    'rag_ingestion.adapters.parser_pdf.PdfParser',
    'rag_ingestion.adapters.parser_markitdown.MarkItDownParser',
]


def get_parsers() -> List[DocumentParser]:
    """Instantiate the configured parsers, skipping any that fail to import."""
    paths = getattr(settings, 'RAG_INGESTION_PARSERS', None) or DEFAULT_PARSER_PATHS
    parsers: List[DocumentParser] = []
    for path in paths:
        try:
            parsers.append(import_string(path)())
        except Exception as exc:
            logger.warning(
                'rag_ingestion_parser_load_failed',
                extra={'event': 'rag_ingestion_parser_load_failed',
                       'parser': path, 'error_type': type(exc).__name__},
            )
    return parsers


def select_parser(filename: str, mime: str = '', *, parsers=None) -> Optional[DocumentParser]:
    """Return the first parser that claims the given file, or None."""
    for parser in (parsers if parsers is not None else get_parsers()):
        try:
            if parser.supports(filename=filename, mime=mime):
                return parser
        except Exception:
            continue
    return None
