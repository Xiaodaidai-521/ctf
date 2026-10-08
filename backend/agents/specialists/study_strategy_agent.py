"""Deterministic structured study-strategy agent."""

from __future__ import annotations


class StudyStrategyAgent:
    DEFAULT_RESULT = {
        "goal": "", "priorityKnowledgePoints": [], "steps": [], "dailyMinutes": 45,
        "estimatedDays": 7, "reviewIntervals": [1, 3, 7], "successCriteria": [],
    }

    def build(self, *, query="", learning_analysis=None, resources=None):
        analysis = learning_analysis if isinstance(learning_analysis, dict) else {}
        resource_data = resources if isinstance(resources, dict) else {}
        weak = list(analysis.get("weakKnowledgePoints") or [])[:5]
        priority = [str(item.get("name") or item)[:100] if isinstance(item, dict) else str(item)[:100] for item in weak]
        resource_list = list(resource_data.get("resourceList") or resource_data.get("resources") or [])[:8]
        risk = analysis.get("riskLevel")
        daily_minutes = 60 if risk == "high" else 45
        days = 14 if len(priority) >= 4 else 7
        steps = [
            {"order": 1, "action": "review_prerequisites"},
            {"order": 2, "action": "learn_priority_knowledge", "knowledgePoints": priority},
            {"order": 3, "action": "guided_practice", "resourceIds": [str(item.get("id") or "") for item in resource_list if isinstance(item, dict)]},
            {"order": 4, "action": "spaced_review", "intervals": [1, 3, 7]},
        ]
        return {
            "goal": str(query or "巩固当前学习目标")[:300],
            "priorityKnowledgePoints": priority,
            "steps": steps,
            "dailyMinutes": daily_minutes,
            "estimatedDays": days,
            "reviewIntervals": [1, 3, 7],
            "successCriteria": ["完成计划中的练习", "复测正确率达到 80%", "能够独立解释关键步骤"],
        }
