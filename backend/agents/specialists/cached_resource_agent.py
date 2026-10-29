"""Versioned TTL/cache-safety adapter for the existing ResourceAgent."""

from __future__ import annotations

from collections import OrderedDict
import logging
import threading
import time

from django.conf import settings
from django.utils import timezone

from ai_assistant.performance import current_metrics
from .resource_agent import ResourceAgent as LegacyResourceAgent


logger = logging.getLogger(__name__)
_locks_guard = threading.Lock()
_key_locks = OrderedDict()


def _lock_for(key):
    with _locks_guard:
        lock = _key_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _key_locks[key] = lock
            while len(_key_locks) > 512:
                _key_locks.popitem(last=False)
        else:
            _key_locks.move_to_end(key)
        return lock


class ResourceAgent(LegacyResourceAgent):
    """Preserve retrieval/ranking while adding versioning, TTL and safety checks."""

    def _versioned_point(self, knowledge_point):
        kb = str(getattr(settings, "TUTOR_KNOWLEDGE_BASE_VERSION", "v1"))[:20]
        algorithm = str(getattr(settings, "TUTOR_RESOURCE_ALGORITHM_VERSION", "v2"))[:20]
        return f"kb:{kb}|algo:{algorithm}|{knowledge_point}"[:160]

    def prepare(self, **kwargs):
        student_id = self._coerce_student_id(kwargs.get("student_id"))
        question = kwargs.get("knowledge_point") or kwargs.get("question") or kwargs.get("query") or ""
        point = self._normalize_knowledge_point(question)
        lock = _lock_for((student_id, self._versioned_point(point)))
        with lock:
            return super().prepare(**kwargs)

    def _get_cache(self, student_id, knowledge_point):
        if not getattr(settings, "TUTOR_RESOURCE_CACHE_ENABLED", True):
            return None
        cache = super()._get_cache(student_id, self._versioned_point(knowledge_point))
        if cache is None:
            return None
        populated = bool(cache.resourceList)
        ttl = int(getattr(settings, "TUTOR_RESOURCE_CACHE_TTL", 900) if populated else getattr(settings, "TUTOR_RESOURCE_EMPTY_CACHE_TTL", 90))
        if (timezone.now() - cache.updatedTime).total_seconds() <= max(15, ttl):
            return cache
        try:
            cache.delete()
        except Exception as exc:
            logger.warning("resource_cache_expiry_delete_failure", extra={
                "event": "resource_cache_expiry_delete_failure", "error_type": type(exc).__name__,
            })
        return None

    def _write_cache(self, student_id, knowledge_point, resources, student_level):
        if not getattr(settings, "TUTOR_RESOURCE_CACHE_ENABLED", True):
            return None
        return super()._write_cache(student_id, self._versioned_point(knowledge_point), resources, student_level)

    def _retrieve_vector_resources(self, query):
        started = time.monotonic()
        try:
            return super()._retrieve_vector_resources(query)
        finally:
            metrics = current_metrics()
            if metrics:
                metrics.record_rag((time.monotonic() - started) * 1000)

    def _sanitize_resource_list(self, resources):
        # The base implementation rehydrates IDs and excludes registered materials
        # on every cache hit; neither cached prose nor old visibility is reused.
        return super()._sanitize_resource_list(resources)
