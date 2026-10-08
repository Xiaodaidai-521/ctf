"""Structured knowledge diagnosis agent with short-lived student cache."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from django.db.models import Avg, Count

from ai_assistant.cache_services import diagnosis_cache_key, diagnosis_ttl, safe_cache_get, safe_cache_set
from ai_assistant.performance import current_metrics

logger = logging.getLogger(__name__)


class KnowledgeDiagnosisAgent:
    DEFAULT_RESULT = {"weakKnowledgePoints": [], "masteryScore": 0, "errorPattern": []}

    def analyze(self, *, student_id: int, query: str = "", challenge_id: Optional[int] = None) -> Dict:
        try:
            if not student_id:
                return dict(self.DEFAULT_RESULT)
            key = diagnosis_cache_key(student_id)
            cached = safe_cache_get(key)
            if isinstance(cached, dict):
                metrics = current_metrics()
                if metrics:
                    metrics.diagnosis_cache_hit = True
                return cached
            weak_points = self._weak_knowledge_points(student_id)
            mastery_score = self._mastery_score(student_id)
            error_pattern = self._error_pattern(student_id, challenge_id)
            if query and len(weak_points) < 3:
                weak_points.extend(self._retrieval_hints(query, challenge_id, 3 - len(weak_points)))
            result = {
                "weakKnowledgePoints": weak_points[:5],
                "masteryScore": mastery_score,
                "errorPattern": error_pattern[:5],
            }
            safe_cache_set(key, result, diagnosis_ttl())
            return result
        except Exception as exc:
            logger.warning("knowledge_diagnosis_agent_fallback", extra={
                "event": "knowledge_diagnosis_agent_fallback", "error_type": type(exc).__name__,
            })
            return dict(self.DEFAULT_RESULT)

    def _weak_knowledge_points(self, student_id):
        from learning_paths.models import UserKnowledgeState
        queryset = UserKnowledgeState.objects.filter(user_id=student_id).select_related("concept").order_by("mastery_level", "-updated_at")[:5]
        return [{"id": state.concept_id, "name": state.concept.name, "mastery": round(float(state.mastery_level) * 100, 2)} for state in queryset if state.mastery_level < 0.75]

    def _mastery_score(self, student_id):
        from learning_paths.models import UserKnowledgeState
        value = UserKnowledgeState.objects.filter(user_id=student_id).aggregate(value=Avg("mastery_level"))["value"]
        return round(float(value) * 100, 2) if value is not None else 0

    def _error_pattern(self, student_id, challenge_id):
        from submissions.models import Submission
        queryset = Submission.objects.filter(user_id=student_id, is_correct=False)
        if challenge_id:
            queryset = queryset.filter(challenge_id=challenge_id)
        rows = queryset.values("challenge__category__name").annotate(count=Count("id")).order_by("-count")[:5]
        return [{"type": row.get("challenge__category__name") or "unknown", "count": row.get("count") or 0} for row in rows]

    def _retrieval_hints(self, query, challenge_id, limit):
        if limit <= 0:
            return []
        try:
            from ai_assistant.service import MultiAgentChatService
            from challenges.models import Challenge
            challenge_info = None
            if challenge_id:
                challenge = Challenge.objects.select_related("category").filter(id=challenge_id, is_active=True).first()
                if challenge:
                    challenge_info = {
                        "id": challenge.id, "title": challenge.title,
                        "category": challenge.category.name if challenge.category else "",
                        "category_name": challenge.category.name if challenge.category else "",
                        "difficulty": challenge.difficulty, "description": challenge.description,
                    }
            package = MultiAgentChatService().build_knowledge_context(query, challenge_info, "category", limit)
            hints = []
            for item in package.get("items", [])[:limit]:
                title = item.get("title") or item.get("source") or ""
                if title:
                    hints.append({"id": item.get("id") or "", "name": str(title)[:80], "mastery": 0})
            return hints
        except Exception as exc:
            logger.warning("knowledge_diagnosis_agent_fallback", extra={
                "event": "knowledge_diagnosis_agent_fallback", "error_type": type(exc).__name__,
            })
            return []
