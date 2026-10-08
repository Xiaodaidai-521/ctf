"""Structured teaching context for internal agent coordination.

TeachingContext is intentionally prompt-neutral in this stage. It collects
structured data for metadata/internal context without changing legacy response
generation or API response shapes.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import math
import json
import re
from typing import Any, Dict, Mapping, Optional


SCHEMA_VERSION = "1.1"
EXTENSION_SECTIONS = (
    "exam",
    "wrongQuestion",
    "teacherFeedback",
    "teacherInstruction",
)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_conversation_history() -> Dict[str, Any]:
    return {
        "recentMessages": [],
        "summary": "",
    }


def _default_extensions() -> Dict[str, Any]:
    return {section: {} for section in EXTENSION_SECTIONS}


def _json_safe(value: Any) -> Any:
    """Return a JSON-serializable representation without leaking Python objects."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else 0
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
            if key is not None
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    safe_value = _json_safe(value)
    return safe_value if isinstance(safe_value, dict) else {}


def _conversation_history(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return _default_conversation_history()

    recent_messages = value.get("recentMessages", [])
    if not isinstance(recent_messages, (list, tuple)):
        recent_messages = []

    summary = value.get("summary", "")
    return {
        "recentMessages": _json_safe(list(recent_messages)),
        "summary": str(summary or ""),
    }


def _extensions(value: Any) -> Dict[str, Any]:
    extensions = _default_extensions()
    if isinstance(value, Mapping):
        for section, section_value in value.items():
            if isinstance(section_value, Mapping):
                extensions[str(section)] = _dict_or_empty(section_value)
    return extensions


@dataclass(frozen=True)
class TeachingContext:
    """Canonical JSON-compatible teaching context.

    The public representation intentionally uses the schema's camelCase keys.
    """

    schemaVersion: str = SCHEMA_VERSION
    studentId: str = ""
    question: str = ""
    taskType: str = ""
    learningAnalysis: Dict[str, Any] = field(default_factory=dict)
    knowledgeDiagnosis: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)
    conversationHistory: Dict[str, Any] = field(default_factory=_default_conversation_history)
    extensions: Dict[str, Any] = field(default_factory=_default_extensions)
    timestamp: str = field(default_factory=_utc_timestamp)

    @classmethod
    def empty(cls) -> "TeachingContext":
        return cls()

    @classmethod
    def from_dict(cls, payload: Optional[Mapping[str, Any]]) -> "TeachingContext":
        if not isinstance(payload, Mapping):
            return cls.empty()
        return cls(
            schemaVersion=str(payload.get("schemaVersion") or SCHEMA_VERSION),
            studentId=str(payload.get("studentId") or ""),
            question=str(payload.get("question") or ""),
            taskType=str(payload.get("taskType") or ""),
            learningAnalysis=_dict_or_empty(payload.get("learningAnalysis")),
            knowledgeDiagnosis=_dict_or_empty(payload.get("knowledgeDiagnosis")),
            resources=_dict_or_empty(payload.get("resources")),
            conversationHistory=_conversation_history(payload.get("conversationHistory")),
            extensions=_extensions(payload.get("extensions")),
            timestamp=str(payload.get("timestamp") or _utc_timestamp()),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schemaVersion": str(self.schemaVersion or SCHEMA_VERSION),
            "studentId": str(self.studentId or ""),
            "question": str(self.question or ""),
            "taskType": str(self.taskType or ""),
            "learningAnalysis": _dict_or_empty(self.learningAnalysis),
            "knowledgeDiagnosis": _dict_or_empty(self.knowledgeDiagnosis),
            "resources": _dict_or_empty(self.resources),
            "conversationHistory": _conversation_history(self.conversationHistory),
            "extensions": _extensions(self.extensions),
            "timestamp": str(self.timestamp or _utc_timestamp()),
        }

    def to_internal_context(self) -> Dict[str, Any]:
        """Return the context payload consumed by future response chains."""
        return {
            "teaching_context": self.to_dict(),
        }


class TeachingContextBuilder:
    """Build TeachingContext from task/capability/section data.

    Builder methods accept structured data only. Natural-language final answers
    should stay out of this object and remain in the legacy response chain.
    """

    SECTION_ALIASES = {
        "learningAnalysis": "learningAnalysis",
        "learning_analysis": "learningAnalysis",
        "knowledgeDiagnosis": "knowledgeDiagnosis",
        "knowledge_diagnosis": "knowledgeDiagnosis",
        "resources": "resources",
        "resourcePreparation": "resources",
        "resource_preparation": "resources",
    }

    def __init__(self, base: Optional[Mapping[str, Any] | TeachingContext] = None):
        if isinstance(base, TeachingContext):
            self._data = base.to_dict()
        elif isinstance(base, Mapping):
            self._data = TeachingContext.from_dict(base).to_dict()
        else:
            self._data = TeachingContext.empty().to_dict()

    def with_student(self, student_id: Any) -> "TeachingContextBuilder":
        self._data["studentId"] = "" if student_id is None else str(student_id)
        return self

    def with_question(self, question: Any) -> "TeachingContextBuilder":
        self._data["question"] = "" if question is None else str(question)
        return self

    def with_task_type(self, task_type: Any) -> "TeachingContextBuilder":
        self._data["taskType"] = "" if task_type is None else str(task_type)
        return self

    def with_learning_analysis(self, data: Optional[Mapping[str, Any]]) -> "TeachingContextBuilder":
        return self.with_section("learningAnalysis", data)

    def with_knowledge_diagnosis(self, data: Optional[Mapping[str, Any]]) -> "TeachingContextBuilder":
        return self.with_section("knowledgeDiagnosis", data)

    def with_resources(self, data: Optional[Mapping[str, Any]]) -> "TeachingContextBuilder":
        return self.with_section("resources", data)

    def with_conversation_history(
        self,
        *,
        recent_messages: Optional[list] = None,
        summary: str = "",
    ) -> "TeachingContextBuilder":
        self._data["conversationHistory"] = _conversation_history({
            "recentMessages": recent_messages or [],
            "summary": summary,
        })
        return self

    def with_section(self, section: str, data: Optional[Mapping[str, Any]]) -> "TeachingContextBuilder":
        canonical = self.SECTION_ALIASES.get(str(section), str(section))
        if canonical in {"learningAnalysis", "knowledgeDiagnosis", "resources"}:
            self._data[canonical] = _dict_or_empty(data)
        else:
            self.with_extension(canonical, data)
        return self

    def with_extension(self, section: str, data: Optional[Mapping[str, Any]]) -> "TeachingContextBuilder":
        extensions = _extensions(self._data.get("extensions"))
        extensions[str(section)] = _dict_or_empty(data)
        self._data["extensions"] = extensions
        return self

    def with_specialist_results(self, results: Optional[Mapping[str, Any]]) -> "TeachingContextBuilder":
        if not isinstance(results, Mapping):
            return self
        for section, data in results.items():
            self.with_section(str(section), data if isinstance(data, Mapping) else None)
        return self

    def build(self) -> TeachingContext:
        data = deepcopy(self._data)
        data["timestamp"] = data.get("timestamp") or _utc_timestamp()
        return TeachingContext.from_dict(data)

    def build_dict(self) -> Dict[str, Any]:
        return self.build().to_dict()

    def build_internal_context(self) -> Dict[str, Any]:
        return self.build().to_internal_context()


# Canonical bounded schema 1.1 builder used by TutorRequestOrchestrator.
MAX_RECENT_MESSAGES = 8
MAX_MESSAGE_CHARS = 500
MAX_RAG_CHARS = 6000
MAX_RESOURCES = 8
MAX_WEAK_POINTS = 5
SENSITIVE_KEYS = {
    "password", "password_hash", "token", "access_token", "refresh_token", "secret",
    "api_key", "apikey", "email", "phone", "phone_number", "mobile", "system_prompt",
    "workflowid", "workflow_id", "agentcontext", "agent_context",
}


def _safe(value, depth=0):
    if depth > 8:
        return ""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else 0
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _safe(item, depth + 1)
            for key, item in value.items()
            if str(key).lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe(item, depth + 1) for item in value]
    return str(value)


def _mapping(value):
    result = _safe(value)
    return result if isinstance(result, dict) else {}


def _clip_text(value, limit):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _history(value):
    if not isinstance(value, (list, tuple)):
        return {"recentMessages": [], "summary": ""}
    recent = []
    for item in value[-MAX_RECENT_MESSAGES:]:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "")
        if role not in {"user", "assistant", "system"}:
            role = "assistant"
        recent.append({"role": role, "content": _clip_text(item.get("content"), MAX_MESSAGE_CHARS)})
    return {"recentMessages": recent, "summary": ""}


def _clip_resources(value):
    data = _mapping(value)
    for key in ("resourceList", "resources", "items"):
        if isinstance(data.get(key), list):
            data[key] = data[key][:MAX_RESOURCES]
    return data


def _clip_diagnosis(value):
    data = _mapping(value)
    if isinstance(data.get("weakKnowledgePoints"), list):
        data["weakKnowledgePoints"] = data["weakKnowledgePoints"][:MAX_WEAK_POINTS]
    return data


def _clip_knowledge(value):
    data = _mapping(value)
    if isinstance(data.get("retrievalContext"), list):
        clipped = []
        remaining = MAX_RAG_CHARS
        for item in data["retrievalContext"]:
            safe_item = _safe(item)
            raw = json.dumps(safe_item, ensure_ascii=False)
            if remaining <= 0:
                break
            if len(raw) > remaining:
                safe_item = {"text": raw[:remaining]}
            clipped.append(safe_item)
            remaining -= min(len(raw), remaining)
        data["retrievalContext"] = clipped
    return data


class SharedTeachingContextBuilder:
    def build(
        self, *, student_id="", question="", task_type="", student_profile=None,
        learning_analysis=None, knowledge_diagnosis=None, knowledge_context=None,
        resources=None, study_strategy=None, conversation_history=None, extensions=None,
    ):
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "studentId": str(student_id or ""),
            "question": _clip_text(question, 4000),
            "taskType": str(task_type or ""),
            "studentProfile": _mapping(student_profile),
            "learningAnalysis": _mapping(learning_analysis),
            "knowledgeDiagnosis": _clip_diagnosis(knowledge_diagnosis),
            "knowledgeContext": _clip_knowledge(knowledge_context),
            "resources": _clip_resources(resources),
            "studyStrategy": _mapping(study_strategy),
            "conversationHistory": _history(conversation_history),
            "extensions": _mapping(extensions),
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        return _safe(payload)

