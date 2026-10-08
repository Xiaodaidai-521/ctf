"""Side-effect-free deterministic router for tutoring requests."""

from __future__ import annotations

import logging
import re

from agents.task_plan import (
    KNOWLEDGE_EXPLANATION,
    LEARNING_ANALYSIS,
    QUESTION_ANSWER,
    RESOURCE_RECOMMENDATION,
    STUDY_PLAN,
    execution_plan_for,
)

logger = logging.getLogger(__name__)


class TutorAgentRouter:
    QUESTION_ANSWER = QUESTION_ANSWER
    LEARNING_ANALYSIS = LEARNING_ANALYSIS
    KNOWLEDGE_EXPLANATION = KNOWLEDGE_EXPLANATION
    STUDY_PLAN = STUDY_PLAN
    RESOURCE_RECOMMENDATION = RESOURCE_RECOMMENDATION

    KEYWORDS = {
        LEARNING_ANALYSIS: (
            "成绩下降", "成绩分析", "学习进度", "学习分析", "掌握情况", "薄弱点",
            "学情", "诊断", "learning progress", "learning analysis", "score drop",
        ),
        KNOWLEDGE_EXPLANATION: (
            "解释", "讲解", "什么是", "是什么", "原理", "知识点",
            "explain", "what is", "definition", "how does",
        ),
        STUDY_PLAN: (
            "学习计划", "制定计划", "学习规划", "学习路线", "学习路径", "复习计划",
            "study plan", "roadmap", "learning plan", "schedule",
        ),
        RESOURCE_RECOMMENDATION: (
            "推荐相关资源", "推荐资源", "推荐资料", "相关资源", "学习资源", "找资源",
            "recommend resources", "resource recommendation", "learning resources",
        ),
    }
    PRIORITY = (STUDY_PLAN, LEARNING_ANALYSIS, RESOURCE_RECOMMENDATION, KNOWLEDGE_EXPLANATION)
    RESOURCE_INTENT_TERMS = (
        "资源", "资料", "文档", "材料", "课件", "讲义", "推荐", "找", "有没有",
        "resource", "resources", "material", "materials", "document", "documents",
    )

    @classmethod
    def fallback_result(cls):
        return {
            "taskType": cls.QUESTION_ANSWER,
            "requiredAgents": execution_plan_for(cls.QUESTION_ANSWER),
            "matchedRules": [],
            "fallback": True,
        }

    def route(self, question):
        try:
            text = re.sub(r"\s+", " ", str(question or "").strip().lower())
            if not text:
                return self.fallback_result()
            matches = {
                task_type: [keyword for keyword in keywords if keyword.lower() in text]
                for task_type, keywords in self.KEYWORDS.items()
            }
            resource_intent = [term for term in self.RESOURCE_INTENT_TERMS if term.lower() in text]
            if resource_intent and not matches[RESOURCE_RECOMMENDATION]:
                matches[RESOURCE_RECOMMENDATION] = resource_intent[:2]
            best_task = self.QUESTION_ANSWER
            best_score = 0
            for task_type in self.PRIORITY:
                score = len(matches[task_type])
                if score > best_score:
                    best_task, best_score = task_type, score
            if best_score == 0:
                return self.fallback_result()
            return {
                "taskType": best_task,
                "requiredAgents": execution_plan_for(best_task),
                "matchedRules": matches[best_task],
                "fallback": False,
            }
        except (TypeError, ValueError, re.error) as exc:
            logger.warning(
                "tutor_router_fallback",
                extra={"event": "tutor_router_fallback", "error_type": type(exc).__name__},
            )
            return self.fallback_result()

