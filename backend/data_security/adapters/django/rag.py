"""Bound RAG output protection; the unbound legacy mode does not claim scanning."""
from rest_framework.exceptions import APIException

from data_security.contracts import Outlet
from .content import ContentProtectionError


class RagProtectionError(ContentProtectionError, APIException):
    """Bound failures propagate through legacy fallbacks and close HTTP exits."""
    status_code = 503
    default_detail = 'RAG_PROTECTION_FAILED'
    default_code = 'rag_protection_failed'

    def __init__(self, reason='RAG_PROTECTION_FAILED'):
        APIException.__init__(self, detail=reason)


_protect = None


def bind_rag_protection(protect):
    global _protect
    _protect = protect


def rag_protection_enabled():
    return _protect is not None


def protect_rag(value, *, object_ref, object_version, outlet='rag'):
    if _protect is None:
        return value
    try:
        return _protect(value, outlet=Outlet(outlet), object_ref=object_ref, object_version=object_version)
    except Exception:
        raise RagProtectionError('RAG_PROTECTION_FAILED') from None


def protect_rag_fields(value, *, text_fields=(), object_ref, object_version, outlet='api'):
    """Protect declared body fields as TEXT and the remaining metadata as JSON."""
    if _protect is None:
        return value
    result = protect_rag({name: item for name, item in value.items() if name not in text_fields},
                         object_ref=object_ref, object_version=object_version, outlet=outlet)
    for name in text_fields:
        if name in value:
            result[name] = protect_rag(value[name], object_ref=f'{object_ref}/{name}',
                                      object_version=object_version, outlet=outlet)
    return result


def protect_rag_response(value, *, object_ref='rag/response', outlet='api'):
    """Map chat bodies and known result containers onto the bound protection port."""
    if _protect is None:
        return value
    if not isinstance(value, dict):
        return protect_rag(value, object_ref=object_ref, object_version='v1', outlet=outlet)
    nested = ('responses', 'knowledge_items', 'sources', 'legal_sources', 'rag_sources',
              'resources', 'resourceList', 'resourcePreparation')
    result = protect_rag_fields(
        {name: item for name, item in value.items() if name not in nested},
        text_fields=('content', 'answer', 'summary', 'text', 'excerpt', 'context_text', 'description'),
        object_ref=object_ref, object_version='v1', outlet=outlet)
    for name in nested:
        if name in value:
            item = value[name]
            if isinstance(item, list):
                result[name] = [protect_rag_response(child, object_ref=f'{object_ref}/{name}',
                                                    outlet=outlet) for child in item]
            else:
                result[name] = protect_rag_response(item, object_ref=f'{object_ref}/{name}', outlet=outlet)
    return result
