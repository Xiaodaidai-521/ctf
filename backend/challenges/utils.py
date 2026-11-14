"""Use the same exact flag comparison for exam and legacy lab checks."""
from hmac import compare_digest


def check_flag(submitted, expected):
    if not isinstance(submitted, str) or not isinstance(expected, str) or not expected.strip():
        return False
    return compare_digest(submitted.strip().encode('utf-8'), expected.strip().encode('utf-8'))
