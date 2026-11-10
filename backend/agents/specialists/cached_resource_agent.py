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
        sanitized = super()._sanitize_resource_list(resources)
        if not sanitized:
            return []
        resource_ids = [int(item["id"]) for item in sanitized if item.get("type") in {"document", "video", "report", "zip", "resource", "ai_resource"} and str(item.get("id", "")).isdigit()]
        article_ids = [int(item["id"]) for item in sanitized if item.get("type") == "article" and str(item.get("id", "")).isdigit()]
        challenge_ids = [int(item["id"]) for item in sanitized if item.get("type") == "challenge" and str(item.get("id", "")).isdigit()]
        visible_resources = set()
        visible_articles = set()
        visible_challenges = set()
        try:
            if resource_ids:
                from resources.models import Resource
                visible_resources = set(Resource.objects.filter(id__in=resource_ids, status="approved").values_list("id", flat=True))
            if article_ids:
                from articles.models import Article
                visible_articles = set(Article.objects.filter(id__in=article_ids, status="approved").values_list("id", flat=True))
            if challenge_ids:
                from challenges.models import Challenge
                visible_challenges = set(Challenge.objects.filter(id__in=challenge_ids, is_active=True).values_list("id", flat=True))
        except Exception as exc:
            logger.warning("resource_cache_visibility_fallback", extra={
                "event": "resource_cache_visibility_fallback", "error_type": type(exc).__name__,
            })
            return []
        result = []
        for item in sanitized:
            item_id = int(item["id"]) if str(item.get("id", "")).isdigit() else None
            item_type = item.get("type")
            if item_type == "article" and item_id in visible_articles:
                result.append(item)
            elif item_type == "challenge" and item_id in visible_challenges:
                result.append(item)
            elif item_type in {"document", "video", "report", "zip", "resource", "ai_resource"} and item_id in visible_resources:
                result.append(item)
        return result
