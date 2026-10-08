"""Privacy-minimizing, cached adapter for student profile context."""

from __future__ import annotations

import logging

from ai_assistant.cache_services import profile_cache_key, profile_ttl, safe_cache_get, safe_cache_set
from ai_assistant.performance import current_metrics

logger = logging.getLogger(__name__)


class StudentProfileContextAdapter:
    EMPTY = {}

    def build(self, user):
        user_id = getattr(user, "id", user)
        if not user_id:
            return {}
        key = profile_cache_key(user_id)
        cached = safe_cache_get(key)
        if isinstance(cached, dict):
            metrics = current_metrics()
            if metrics:
                metrics.profile_cache_hit = True
            return cached
        try:
            from student_profiles.models import StudentProfile

            profile = StudentProfile.objects.select_related("preference", "persona").filter(user_id=user_id).first()
            if not profile:
                safe_cache_set(key, {}, profile_ttl())
                return {}
            result = {
                "learningGoals": str(profile.learning_goals or "")[:1000],
                "selfAssessedSkills": profile.self_assessed_skills if isinstance(profile.self_assessed_skills, dict) else {},
                "onboardingCompleted": bool(profile.onboarding_completed),
            }
            preference = getattr(profile, "preference", None)
            if preference:
                result["learningPreference"] = {
                    "preferredPace": preference.preferred_pace,
                    "preferredModality": list(preference.preferred_modality or [])[:8],
                    "prefersDiagrams": bool(preference.prefers_diagrams),
                    "prefersCodeExamples": bool(preference.prefers_code_examples),
                    "dailyStudyHours": float(preference.daily_study_hours or 0),
                    "difficultyBias": float(preference.difficulty_bias or 0),
                }
            persona = getattr(profile, "persona", None)
            if persona:
                result["learningPersona"] = {
                    "label": str(persona.persona_label or "")[:100],
                    "confidence": float(persona.confidence_score or 0),
                    "traits": persona.persona_traits if isinstance(persona.persona_traits, dict) else {},
                    "recommendedAgentRoster": list(persona.recommended_agent_roster or [])[:8],
                }
            safe_cache_set(key, result, profile_ttl())
            return result
        except Exception as exc:
            logger.warning("student_profile_context_fallback", extra={
                "event": "student_profile_context_fallback", "user_id": str(user_id),
                "error_type": type(exc).__name__,
            })
            return {}

