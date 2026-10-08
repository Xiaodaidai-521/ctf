"""Structured learning-state analysis agent.

This agent prepares JSON-compatible data only. It does not call an LLM and
does not generate final user-facing prose.
"""

from __future__ import annotations

import logging

from datetime import timedelta
from typing import Dict

from django.db.models import Avg, Count, Sum
from django.utils import timezone



logger = logging.getLogger(__name__)

class LearningAnalysisAgent:
    """Analyze a student's recent learning state from existing data."""

    DEFAULT_RESULT = {
        "learningTime": 0,
        "studyDays": 0,
        "completionRate": 0,
        "accuracyRate": 0,
        "trend": "unknown",
        "riskLevel": "unknown",
    }

    def analyze(self, student_id: int) -> Dict:
        try:
            if not student_id:
                return dict(self.DEFAULT_RESULT)

            learning_time, study_days, trend = self._learning_activity(student_id)
            completion_rate = self._completion_rate(student_id)
            accuracy_rate = self._accuracy_rate(student_id)
            risk_level = self._risk_level(
                learning_time=learning_time,
                study_days=study_days,
                completion_rate=completion_rate,
                accuracy_rate=accuracy_rate,
                trend=trend,
            )

            return {
                "learningTime": learning_time,
                "studyDays": study_days,
                "completionRate": completion_rate,
                "accuracyRate": accuracy_rate,
                "trend": trend,
                "riskLevel": risk_level,
            }
        except Exception as exc:
            logger.warning("learning_analysis_agent_fallback", extra={"event": "learning_analysis_agent_fallback", "error_type": type(exc).__name__})
            return dict(self.DEFAULT_RESULT)

    def _learning_activity(self, student_id: int):
        from learning_analytics.models import DailyLearningStat
        from learning_paths.models import UserKnowledgeState
        from submissions.models import Submission

        today = timezone.localdate()
        start = today - timedelta(days=29)
        stats = list(
            DailyLearningStat.objects.filter(
                user_id=student_id,
                stat_date__gte=start,
            ).order_by("stat_date")
        )

        if stats:
            learning_time = int(sum(item.effective_learning_seconds for item in stats))
            study_days = sum(1 for item in stats if item.effective_learning_seconds > 0)
            recent = sum(item.effective_learning_seconds for item in stats[-7:])
            previous = sum(item.effective_learning_seconds for item in stats[-14:-7])
            return learning_time, study_days, self._trend(recent, previous)

        aggregate = UserKnowledgeState.objects.filter(user_id=student_id).aggregate(
            learning_time=Sum("total_time_spent"),
        )
        learning_time = int(aggregate.get("learning_time") or 0)
        study_days = (
            Submission.objects.filter(user_id=student_id)
            .dates("created_at", "day")
            .count()
        )
        return learning_time, study_days, "unknown"

    def _completion_rate(self, student_id: int) -> float:
        from learning_paths.models import UserKnowledgeState, UserPathProgress

        progress = UserPathProgress.objects.filter(user_id=student_id).aggregate(
            value=Avg("progress_percentage"),
        )["value"]
        if progress is not None:
            return round(float(progress), 2)

        mastery = UserKnowledgeState.objects.filter(user_id=student_id).aggregate(
            value=Avg("mastery_level"),
        )["value"]
        if mastery is not None:
            return round(float(mastery) * 100, 2)
        return 0

    def _accuracy_rate(self, student_id: int) -> float:
        from submissions.models import Submission

        aggregate = Submission.objects.filter(user_id=student_id).aggregate(
            total=Count("id"),
            correct=Count("id", filter=None),
        )
        total = aggregate.get("total") or 0
        if not total:
            return 0
        correct = Submission.objects.filter(user_id=student_id, is_correct=True).count()
        return round(correct / total * 100, 2)

    @staticmethod
    def _trend(recent: int, previous: int) -> str:
        if recent <= 0 and previous <= 0:
            return "unknown"
        if previous <= 0:
            return "improving" if recent > 0 else "unknown"
        delta = (recent - previous) / max(previous, 1)
        if delta > 0.15:
            return "improving"
        if delta < -0.15:
            return "declining"
        return "stable"

    @staticmethod
    def _risk_level(
        *,
        learning_time: int,
        study_days: int,
        completion_rate: float,
        accuracy_rate: float,
        trend: str,
    ) -> str:
        if not any([learning_time, study_days, completion_rate, accuracy_rate]):
            return "unknown"
        if completion_rate < 30 or accuracy_rate < 40 or (trend == "declining" and study_days <= 1):
            return "high"
        if completion_rate < 60 or accuracy_rate < 60 or trend == "declining":
            return "medium"
        return "low"

