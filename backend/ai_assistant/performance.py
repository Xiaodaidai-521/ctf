"""Request-local tutoring performance metrics and privacy-safe logging."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import logging
import time
import uuid

from django.conf import settings


logger = logging.getLogger("tutor.performance")
_current_metrics = ContextVar("tutor_performance_metrics", default=None)


def _nullable_add(current, value):
    if value is None:
        return current
    return int(value) if current is None else int(current) + int(value)


@dataclass
class TutorPerformanceMetrics:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: object = None
    user_id_hash: str = ""
    task_type: str = "question_answer"
    required_agents: list = field(default_factory=list)
    total_duration_ms: float = 0
    router_duration_ms: float = 0
    agent_metrics: dict = field(default_factory=dict)
    rag_duration_ms: float = 0
    llm_duration_ms: float = 0
    llm_call_count: int = 0
    rag_call_count: int = 0
    prompt_tokens: object = None
    completion_tokens: object = None
    total_tokens: object = None
    profile_cache_hit: bool = False
    diagnosis_cache_hit: bool = False
    resource_cache_hit: bool = False
    fallback_used: bool = False
    status: str = "success"
    _started: float = field(default_factory=time.monotonic, repr=False)

    @classmethod
    def create(cls, *, user_id=None, conversation_id=None):
        salt = "tutor-metrics-v1"
        digest = hashlib.sha256(f"{salt}:{user_id or ''}".encode()).hexdigest()[:20]
        return cls(conversation_id=conversation_id, user_id_hash=digest)

    def record_llm(self, *, duration_ms, usage=None):
        self.llm_call_count += 1
        self.llm_duration_ms += float(duration_ms or 0)
        usage = usage if isinstance(usage, dict) else {}
        self.prompt_tokens = _nullable_add(
            self.prompt_tokens, usage.get("prompt_tokens", usage.get("input_tokens"))
        )
        self.completion_tokens = _nullable_add(
            self.completion_tokens, usage.get("completion_tokens", usage.get("output_tokens"))
        )
        if self.prompt_tokens is not None or self.completion_tokens is not None:
            self.total_tokens = int(self.prompt_tokens or 0) + int(self.completion_tokens or 0)

    def record_rag(self, duration_ms=0):
        self.rag_call_count += 1
        self.rag_duration_ms += float(duration_ms or 0)

    def as_dict(self, *, finalize=False):
        if finalize:
            self.total_duration_ms = round((time.monotonic() - self._started) * 1000, 2)
        return {
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "user_id_hash": self.user_id_hash,
            "task_type": self.task_type,
            "required_agents": list(self.required_agents),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "router_duration_ms": round(self.router_duration_ms, 2),
            "agent_metrics": dict(self.agent_metrics),
            "rag_duration_ms": round(self.rag_duration_ms, 2),
            "llm_duration_ms": round(self.llm_duration_ms, 2),
            "llm_call_count": self.llm_call_count,
            "rag_call_count": self.rag_call_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "profile_cache_hit": self.profile_cache_hit,
            "diagnosis_cache_hit": self.diagnosis_cache_hit,
            "resource_cache_hit": self.resource_cache_hit,
            "fallback_used": self.fallback_used,
            "status": self.status,
        }


def activate_metrics(metrics):
    if not getattr(settings, "TUTOR_METRICS_ENABLED", True):
        _current_metrics.set(None)
        return None
    _current_metrics.set(metrics)
    return metrics


def current_metrics():
    return _current_metrics.get()


def log_metrics(metrics, *, status=None):
    if not getattr(settings, "TUTOR_METRICS_ENABLED", True):
        return
    try:
        if status:
            metrics.status = status
        logger.info("tutor_request_performance", extra={"event": "tutor_request_performance", "metrics": metrics.as_dict(finalize=True)})
    except Exception as exc:
        logger.warning("tutor_performance_log_failure", extra={"event": "tutor_performance_log_failure", "error_type": type(exc).__name__})
