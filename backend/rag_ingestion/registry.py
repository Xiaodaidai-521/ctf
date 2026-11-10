"""Injected ingestion factories; defaults are composed only at application startup."""

from typing import List, Optional

from .interfaces import DocumentParser


_parser_factory = None
_pipeline_factory = None
_embedding_factory = None


def bind_ingestion(*, parser_factory, pipeline_factory, embedding_factory):
    global _parser_factory, _pipeline_factory, _embedding_factory
    _parser_factory, _pipeline_factory = parser_factory, pipeline_factory
    _embedding_factory = embedding_factory


def get_parsers() -> List[DocumentParser]:
    if _parser_factory is None:
        raise RuntimeError('RAG_NOT_CONFIGURED')
    return _parser_factory()


def get_embedding_service(**options):
    if _embedding_factory is None:
        raise RuntimeError('RAG_NOT_CONFIGURED')
    return _embedding_factory(**options)


def get_pipeline(**ports):
    if _pipeline_factory is None:
        raise RuntimeError('RAG_NOT_CONFIGURED')
    return _pipeline_factory(**ports)


def select_parser(filename: str, mime: str = '', *, parsers=None) -> Optional[DocumentParser]:
    """Return the first parser that claims the given file, or None."""
    for parser in (parsers if parsers is not None else get_parsers()):
        try:
            if parser.supports(filename=filename, mime=mime):
                return parser
        except Exception:
            continue
    return None
