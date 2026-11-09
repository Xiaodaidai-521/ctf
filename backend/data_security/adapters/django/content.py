"""Explicit pre-truncation content boundary; no policy, key or model discovery."""
from collections.abc import Callable


class ContentProtectionError(RuntimeError):
    """A bound protection failure must not enter a legacy raw-content fallback."""


class ProtectedText(str):
    """Internal text already protected at the current content boundary."""

    def __getitem__(self, key):
        return ProtectedText(super().__getitem__(key))


_protect: Callable[[str], str] | None = None


def bind_content_protection(protect_text: Callable[[str], str] | None):
    global _protect
    _protect = protect_text


def content_protection_enabled() -> bool:
    return _protect is not None


def protect_text(value: str) -> str:
    """Keep the unbound baseline; bound failures always return a fixed error."""
    if _protect is None or isinstance(value, ProtectedText):
        return value
    try:
        result = _protect(value)
    except Exception:
        raise ContentProtectionError('CONTENT_PROTECTION_FAILED') from None
    if not isinstance(result, str):
        raise ContentProtectionError('CONTENT_PROTECTION_FAILED')
    return ProtectedText(result)
