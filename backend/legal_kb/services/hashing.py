"""Hash helpers for legal knowledge sources."""

import hashlib


def sha256_text(value: str) -> str:
    """Return SHA-256 hex digest for text."""
    return hashlib.sha256((value or '').encode('utf-8')).hexdigest()
