"""Django-cache adapters for tutoring profile and diagnosis data."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)
PROFILE_VERSION = "v1"
DIAGNOSIS_VERSION = "v1"


def profile_cache_key(student_id):
    return f"tutor:profile:{PROFILE_VERSION}:student:{int(student_id)}"


def diagnosis_cache_key(student_id, diagnosis_version=DIAGNOSIS_VERSION):
    return f"tutor:diagnosis:{diagnosis_version}:student:{int(student_id)}"


def safe_cache_get(key):
    try:
        return cache.get(key)
    except Exception as exc:
        logger.warning("tutor_cache_get_failure", extra={"event": "tutor_cache_get_failure", "cache_key_prefix": key.split(":student:")[0], "error_type": type(exc).__name__})
        return None


def safe_cache_set(key, value, timeout):
    try:
        cache.set(key, value, timeout=timeout)
    except Exception as exc:
        logger.warning("tutor_cache_set_failure", extra={"event": "tutor_cache_set_failure", "cache_key_prefix": key.split(":student:")[0], "error_type": type(exc).__name__})


def safe_cache_delete(key):
    try:
        cache.delete(key)
    except Exception as exc:
        logger.warning("tutor_cache_delete_failure", extra={"event": "tutor_cache_delete_failure", "cache_key_prefix": key.split(":student:")[0], "error_type": type(exc).__name__})


def invalidate_profile(student_id):
    if student_id:
        safe_cache_delete(profile_cache_key(student_id))


def invalidate_diagnosis(student_id):
    if student_id:
        safe_cache_delete(diagnosis_cache_key(student_id))


def profile_ttl():
    return min(900, max(300, int(getattr(settings, "TUTOR_PROFILE_CACHE_TTL", 600))))


def diagnosis_ttl():
    return min(600, max(180, int(getattr(settings, "TUTOR_DIAGNOSIS_CACHE_TTL", 300))))

