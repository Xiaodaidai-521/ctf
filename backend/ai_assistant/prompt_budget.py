"""Deterministic prompt budgeting without an extra LLM call."""

from __future__ import annotations

import json
from copy import deepcopy

from django.conf import settings


DEFAULT_BUDGETS = {
    "system_safety_chars": 5000,
    "teaching_context_chars": 6000,
    "history_chars": 5000,
    "rag_chars": 5000,
}

TASK_SECTIONS = {
    "question_answer": (),
    "knowledge_explanation": ("knowledgeContext", "resources", "studentProfile"),
    "learning_analysis": ("learningAnalysis", "knowledgeDiagnosis", "resources", "studentProfile"),
    "study_plan": ("learningAnalysis", "resources", "studyStrategy", "studentProfile"),
    "resource_recommendation": ("resources", "studentProfile"),
}


def budgets():
    configured = getattr(settings, "TUTOR_PROMPT_BUDGETS", {}) or {}
    return {key: max(64, int(configured.get(key, value))) for key, value in DEFAULT_BUDGETS.items()}


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _trim(value, limit):
    text = _json(value)
    return text if len(text) <= limit else text[:limit]


def _bounded_section(name, value):
    data = deepcopy(value) if isinstance(value, dict) else value
    if name == "resources" and isinstance(data, dict):
        items = data.get("resourceList") or data.get("resources") or []
        deduped = []
        seen = set()
        for item in items:
            key = str((item or {}).get("id") or (item or {}).get("title") or "")
            if key and key not in seen:
                seen.add(key)
                deduped.append(item)
        data = {"resourceList": deduped[:8]}
    if name in {"learningAnalysis", "knowledgeDiagnosis"} and isinstance(data, dict):
        for key in ("weakKnowledgePoints", "weak_points"):
            if isinstance(data.get(key), list):
                data[key] = data[key][:5]
    return data


def build_teaching_context_summary(context):
    if not isinstance(context, dict):
        return ""
    explicit = context.get("context_summary")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()[:budgets()["teaching_context_chars"]]
    teaching = context if context.get("schemaVersion") else context.get("teaching_context")
    if not isinstance(teaching, dict):
        specialist = context.get("specialist_context") or {}
        teaching = specialist.get("teachingContext")
    if not isinstance(teaching, dict) or not teaching:
        return ""
    task_type = teaching.get("taskType")
    if task_type is None:
        # Legacy callers predate task routing and expect all supplied sections.
        sections = ("learningAnalysis", "knowledgeDiagnosis", "knowledgeContext",
                    "resources", "studentProfile", "studyStrategy")
    else:
        sections = TASK_SECTIONS.get(task_type, TASK_SECTIONS["question_answer"])
    maximum = budgets()["teaching_context_chars"]
    selected = []
    remaining = maximum
    labels = {
        "learningAnalysis": "学生学习摘要", "knowledgeDiagnosis": "知识诊断",
        "knowledgeContext": "知识上下文", "resources": "推荐资源",
        "studentProfile": "学生画像", "studyStrategy": "学习策略",
    }
    for section in sections:
        value = _bounded_section(section, teaching.get(section))
        if value in (None, "", [], {}):
            continue
        # Resources are intentionally added last by TASK_SECTIONS order where possible;
        # truncation therefore drops low-priority tail content before core analysis.
        rendered = f"- {labels[section]}\n{_trim(value, max(0, remaining - 32))}"
        if remaining <= 32:
            break
        selected.append(rendered[:remaining])
        remaining -= len(selected[-1]) + 2
    return "\n\n".join(selected)[:maximum]


def trim_history(history):
    if not isinstance(history, list):
        return []
    limit = budgets()["history_chars"]
    result = []
    used = 0
    for message in reversed(history[-8:]):
        content = str((message or {}).get("content") or "")
        if used + len(content) > limit:
            content = content[-max(0, limit - used):]
        result.append({"role": (message or {}).get("role"), "content": content})
        used += len(content)
        if used >= limit:
            break
    return list(reversed(result))
