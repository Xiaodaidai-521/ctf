"""Single public compatibility adapter for tutoring responses."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import date, datetime

from django.utils import timezone

INTERNAL_KEYS = {
    "workflowId", "workflow_id", "agentContext", "agent_context", "system_prompt",
    "internal_prompt", "teaching_context", "specialist_context",
}

RESOURCE_CENTER_TYPES = {
    "resource", "document", "video", "report", "zip", "course", "textbook", "ai_resource",
}
RESOURCE_CONTAINER_KEYS = {
    "studentId", "knowledgePoint", "cacheHit", "studentLevel", "noMatchedResource",
    "query", "mode",
}


def _safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else 0
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items() if str(key) not in INTERNAL_KEYS}
    if isinstance(value, (list, tuple, set)):
        return [_safe(item) for item in value]
    return str(value)


def _answer(payload, responses):
    for key in ("content", "answer"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    candidates = [item for item in responses if isinstance(item, Mapping) and item.get("content")]
    for agent_id in ("xiaohei", "tutor"):
        for item in reversed(candidates):
            if item.get("agent_id") == agent_id:
                return str(item["content"])
    return str(candidates[-1]["content"]) if candidates else ""


def _safe_entry(entry):
    value = str(entry or "").strip()
    if not value:
        return ""
    if re.match(r"^[A-Za-z]:[\\/]", value) or "\\" in value:
        return ""
    if value.startswith(("/var/", "/home/", "/usr/", "/opt/", "/tmp/")):
        return ""
    if value.startswith("/") or value.startswith(("http://", "https://")):
        return value[:240]
    return ""


def _resource_location(resource_type, label, title):
    if label:
        return f"资源中心 / {label} / {title}"
    if resource_type == "article":
        return f"社区 / 文章 / {title}"
    if resource_type == "challenge":
        return f"题库 / 题目 / {title}"
    return f"资源中心 / {title}"


def _public_resource_item(item):
    if not isinstance(item, Mapping):
        return None
    title = str(item.get("title") or "").strip()[:120]
    entry = _safe_entry(item.get("entry") or item.get("url") or "")
    if not title or not entry:
        return None
    resource_type = str(
        item.get("type") or item.get("resource_type") or item.get("source_type") or "resource"
    ).strip().lower() or "resource"
    label = str(item.get("ai_generated_label") or "").strip()
    if not label and resource_type in RESOURCE_CENTER_TYPES and entry.startswith("/resources"):
        label = "AI多模态生成"
    location = str(item.get("location") or "").strip() or _resource_location(resource_type, label, title)
    return {
        "id": str(item.get("id") or item.get("object_id") or item.get("resource_id") or ""),
        "title": title,
        "type": resource_type,
        "entry": entry,
        "summary": str(item.get("summary") or item.get("description") or item.get("text") or "")[:260],
        "ai_generated_label": label,
        "location": location,
    }


def _public_resource_list(resources):
    if not isinstance(resources, list):
        return []
    public_items = []
    seen = set()
    for item in resources:
        normalized = _public_resource_item(item)
        if not normalized:
            continue
        key = (normalized["type"], normalized["id"] or normalized["entry"])
        if key in seen:
            continue
        seen.add(key)
        public_items.append(normalized)
        if len(public_items) >= 8:
            break
    return public_items


def _select_resource_data(payload, specialist):
    candidates = []
    if isinstance(specialist, Mapping):
        candidates.extend([specialist.get("resources"), specialist.get("resourcePreparation")])
    candidates.extend([payload.get("resourcePreparation"), payload.get("resources")])
    if "resourceList" in payload:
        candidates.append(payload)
    for candidate in candidates:
        if isinstance(candidate, Mapping) and any(
            key in candidate for key in ("resourceList", "resources", "noMatchedResource")
        ):
            return candidate
    return None


def _raw_resource_items(resource_data):
    if not isinstance(resource_data, Mapping):
        return []
    raw_items = resource_data.get("resourceList")
    if not isinstance(raw_items, list):
        raw_items = resource_data.get("resources")
    return raw_items if isinstance(raw_items, list) else []


def _public_resource_container(resource_data, resources, no_matched):
    container = {
        str(key): resource_data.get(key)
        for key in RESOURCE_CONTAINER_KEYS
        if key in resource_data
    }
    container["resourceList"] = resources
    container["resources"] = resources
    container["noMatchedResource"] = bool(no_matched)
    return container


def build_compatible_chat_response(
    payload=None, *, responses=None, conversation_id=None, challenge_info=None,
    specialist_result=None, metadata=None, include_empty=False,
):
    """Preserve legacy payload while adding the canonical compatibility envelope."""
    payload = dict(payload or {})
    responses = list(responses if responses is not None else payload.get("responses") or [])
    specialist = specialist_result if isinstance(specialist_result, Mapping) else {}
    answer = _answer(payload, responses)

    resource_data = _select_resource_data(payload, specialist)
    resources = _public_resource_list(_raw_resource_items(resource_data)) if resource_data else []
    no_matched_resource = bool(resource_data.get("noMatchedResource", not resources)) if resource_data else False

    standard = {
        "content": answer,
        "answer": answer,
        "role": "assistant",
        "timestamp": payload["timestamp"] if "timestamp" in payload else timezone.now().isoformat(),
        "conversation_id": conversation_id if conversation_id is not None else payload.get("conversation_id"),
        "responses": responses,
        "challenge_info": challenge_info if challenge_info is not None else payload.get("challenge_info"),
        "learningAnalysis": specialist.get("learningAnalysis") or {},
        "knowledgeDiagnosis": specialist.get("knowledgeDiagnosis") or {},
        "studyStrategy": specialist.get("studyStrategy") or {},
        "recommendations": payload.get("recommendations") or [],
        "metadata": metadata or payload.get("metadata") or {},
    }
    if resource_data is not None:
        standard["resources"] = resources
        standard["resourceList"] = resources
        standard["noMatchedResource"] = no_matched_resource

    result = _safe(payload)
    if resource_data is not None and isinstance(result.get("resourcePreparation"), Mapping):
        result["resourcePreparation"] = _safe(
            _public_resource_container(resource_data, resources, no_matched_resource)
        )
    result.update(_safe(standard))
    for key in INTERNAL_KEYS:
        result.pop(key, None)
    if not include_empty:
        optional = {
            "resources", "resourceList", "learningAnalysis", "knowledgeDiagnosis",
            "studyStrategy", "recommendations", "metadata", "noMatchedResource",
        }
        result = {
            key: value
            for key, value in result.items()
            if key not in optional or value not in ({}, [], False)
        }
    return result