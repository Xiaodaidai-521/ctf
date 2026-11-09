"""User-scoped structured learning observations and bounded historical memory.

Writes accept only catalog concepts and controlled error-category codes. Reads use
bounded generic JSON rather than inventing schemas for existing preference/fact
records; metadata, sensitive fields and flag-shaped strings are never recalled.
There is deliberately no free-text remember tool.
"""

import json
import logging
import math
import re

from agent_runtime.memory import UserMemoryStore
from agent_runtime.models import UserMemory
from learning_paths.models import KnowledgeConcept, UserKnowledgeState

from .models import KnowledgeObservation

logger = logging.getLogger(__name__)

MEMORY_TYPES = {"learning_insight", "preference", "fact"}
MAX_MEMORIES = 8
MAX_MEMORY_CHARS = 2000
MAX_STRING_CHARS = 200
SENSITIVE_KEYS = {
    "password", "passwordhash", "token", "accesstoken", "refreshtoken", "secret",
    "apikey", "email", "phone", "phonenumber", "mobile", "systemprompt",
    "workflowid", "agentcontext", "flag", "flags", "answer", "answers",
    "expectedanswer", "correctanswer", "credentials", "authorization", "cookie",
    "privatekey", "metadata", "userid", "user", "question", "questiontext",
    "challenge", "challengetext", "challengeinfo", "challengecontext", "challengepayload",
    "challengedescription", "rawchallenge", "payload", "diagnosis", "rawdiagnosis",
    "conversation", "conversationhistory", "history", "recentmessages", "messages",
    "summary", "rawtext", "rawquestion",
}
FLAG_PATTERN = re.compile(r"(?:[a-z0-9_-]*(?:flag|ctf)|htb)\s*\{[^}]*\}", re.I)
# Category names emitted by KnowledgeDiagnosisAgent, plus explicit common aliases.
ERROR_PATTERNS = {
    "web": "web", "web安全": "web", "web security": "web",
    "crypto": "crypto", "cryptography": "crypto", "密码学": "crypto",
    "pwn": "pwn", "binary exploitation": "pwn", "二进制利用": "pwn",
    "reverse": "reverse", "reverse engineering": "reverse", "逆向": "reverse",
    "misc": "misc", "miscellaneous": "misc", "杂项": "misc",
    "forensics": "forensics", "digital forensics": "forensics", "取证": "forensics",
    "compliance": "compliance", "合规": "compliance",
}


def _safe_key(value):
    return (
        isinstance(value, str) and bool(value.strip()) and len(value) <= MAX_STRING_CHARS
        and re.sub(r"[^a-z0-9]", "", value.casefold()) not in SENSITIVE_KEYS
        and not FLAG_PATTERN.search(value)
    )


def _bounded_value(value, depth=0):
    if depth > 4:
        return None
    if isinstance(value, str):
        if FLAG_PATTERN.search(value):
            return None
        return " ".join(value.split())[:MAX_STRING_CHARS]
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:16]:
            if _safe_key(key):
                safe = _bounded_value(item, depth + 1)
                if safe is not None:
                    result[key] = safe
        return result or None
    if isinstance(value, list):
        return [safe for item in value[:8] if (safe := _bounded_value(item, depth + 1)) is not None] or None
    return None


def bounded_memories(value):
    """Return at most eight records and 2000 serialized characters, without metadata."""
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:MAX_MEMORIES]:
        if not isinstance(item, dict):
            continue
        memory_type = item.get("memory_type")
        memory_key = item.get("memory_key")
        if not isinstance(memory_type, str) or memory_type not in MEMORY_TYPES or not _safe_key(memory_key):
            continue
        if not isinstance(item.get("memory_value"), dict):
            continue
        memory_value = _bounded_value(item["memory_value"])
        if not memory_value:
            continue
        record = {"memory_type": memory_type, "memory_key": memory_key, "memory_value": memory_value}
        if len(json.dumps(result + [record], ensure_ascii=False)) <= MAX_MEMORY_CHARS:
            result.append(record)
    return result


def recall_memories(*, user, memory_type=None, memory_key=None, fallback_reasons=None):
    """Read only the server-selected user's allowed historical memory types."""
    if not getattr(user, 'pk', None):
        return []
    if memory_type is not None and (not isinstance(memory_type, str) or memory_type not in MEMORY_TYPES):
        return []
    if memory_key is not None and not _safe_key(memory_key):
        return []
    try:
        rows = UserMemory.objects.filter(user=user, memory_type__in=MEMORY_TYPES)
        if memory_type is not None:
            rows = rows.filter(memory_type=memory_type)
        if memory_key is not None:
            rows = rows.filter(memory_key=memory_key)
        return bounded_memories(list(rows.order_by("-updated_at", "-id").values(
            "memory_type", "memory_key", "memory_value",
        )[:MAX_MEMORIES]))
    except Exception as exc:
        logger.warning("memory_recall_failed", extra={"error_type": type(exc).__name__})
        if fallback_reasons is not None:
            fallback_reasons.append("memory_recall_failed")
        return []


def update_learning_memory(*, user, diagnosis, fallback_reasons=None):
    """Persist validated diagnosis facts and merge measured weaknesses before observations.

    Observation scores use each point's 0..100 scale; hits count score changes
    after the first observation. Error counts are cumulative high-water marks.
    """
    original = diagnosis if isinstance(diagnosis, dict) else {}
    if not getattr(user, 'pk', None):
        return original
    try:
        points = original.get("weakKnowledgePoints", [])
        concepts = {}
        mapped = {}
        current = []
        current_by_concept = {}
        if isinstance(points, list) and points:
            for concept in KnowledgeConcept.objects.only("id", "name", "slug"):
                for label in (concept.name, concept.slug):
                    concepts[" ".join(label.split()).casefold()] = concept
            for point in points[:5]:
                concept = None
                if isinstance(point, dict):
                    label = point.get("name") or point.get("slug")
                    if isinstance(label, str):
                        concept = concepts.get(" ".join(label.split()).casefold())
                current.append((concept.id if concept else None, point))
                if concept is None:
                    continue
                current_by_concept.setdefault(concept.id, point)
                score = point.get("mastery", point.get("masteryScore"))
                if isinstance(score, bool) or not isinstance(score, (int, float)):
                    continue
                if not math.isfinite(score) or not 0 <= score <= 100:
                    continue
                mapped.setdefault(concept.id, (concept, float(score)))

        # Evaluate both historical reads before this round can write observations.
        states = UserKnowledgeState.objects.filter(user=user)
        measured = list(states.filter(mastery_level__lt=0.75).select_related("concept")
                        .order_by("mastery_level", "-updated_at", "concept_id")[:5])
        observations = list(KnowledgeObservation.objects.filter(user=user, score__lt=75).exclude(
            concept_id__in=states.values("concept_id"),
        ).exclude(concept_id__in=current_by_concept).select_related("concept")
            .order_by("score", "-updated_at", "concept_id")[:5])

        for concept, score in mapped.values():
            observation, created = KnowledgeObservation.objects.get_or_create(
                user=user, concept=concept, defaults={"score": score, "hits": 1},
            )
            if not created and observation.score != score:
                observation.score = score
                observation.hits += 1
                observation.save(update_fields=["score", "hits", "updated_at"])

        patterns = original.get("errorPattern", [])
        if isinstance(patterns, list):
            store = UserMemoryStore(user=user)
            for item in patterns[:5]:
                if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                    continue
                pattern = ERROR_PATTERNS.get(" ".join(item["type"].split()).casefold())
                count = item.get("count")
                if pattern is None or type(count) is not int or count <= 0:
                    continue
                key = f"error_pattern:{pattern}"
                previous = store.recall(memory_type="learning_insight", memory_key=key)
                previous_value = previous["memory_value"] if previous else {}
                previous_count = previous_value.get("count") if isinstance(previous_value, dict) else None
                if type(previous_count) is int:
                    count = max(count, previous_count)
                # The producer supplies category counts, not category/concept links.
                value = {"pattern": pattern, "count": count}
                if value != previous_value:
                    store.remember(
                        memory_type="learning_insight", memory_key=key, memory_value=value,
                    )

        if not measured and not observations:
            return original
        weak = []
        seen = set()
        for state in measured:
            point = current_by_concept.get(state.concept_id, {
                "id": state.concept_id, "name": state.concept.name,
            })
            weak.append({**point, "mastery": round(float(state.mastery_level) * 100, 2)})
            seen.add(state.concept_id)
        # Current entries keep their fields, even when they cannot be persisted.
        for concept_id, point in current:
            if len(weak) == 5:
                break
            if (concept_id is not None and concept_id in seen) or point in weak:
                continue
            weak.append(point)
            if concept_id is not None:
                seen.add(concept_id)
        for item in observations:
            if len(weak) == 5:
                break
            weak.append({"id": item.concept_id, "name": item.concept.name, "mastery": item.score})
        if weak == original.get("weakKnowledgePoints"):
            return original
        return {**original, "weakKnowledgePoints": weak}
    except Exception as exc:
        logger.warning("memory_update_failed", extra={"error_type": type(exc).__name__})
        if fallback_reasons is not None:
            fallback_reasons.append("memory_update_failed")
        return original


def run_memory_tool(name, *, user, memory_type=None, memory_key=None):
    """Explicit structured recall/forget only; natural-language queries never reach here."""
    if name == "recall_memories":
        reasons = []
        items = recall_memories(user=user, memory_type=memory_type, memory_key=memory_key,
                                fallback_reasons=reasons)
        if reasons:
            return {"status": "error", "items": [], "error": reasons[0]}
        return {"status": "success" if items else "empty", "items": items}
    if name != "forget_memory":
        return {"status": "error", "items": [], "error": "Unknown memory tool"}
    if not isinstance(memory_type, str) or memory_type not in MEMORY_TYPES or not _safe_key(memory_key):
        return {"status": "error", "items": [], "error": "Explicit memory_type and memory_key are required"}
    try:
        deleted = UserMemoryStore(user=user).forget(memory_type=memory_type, memory_key=memory_key)
        return {"status": "success", "items": [], "deleted": deleted}
    except Exception as exc:
        logger.warning("memory_forget_failed", extra={"error_type": type(exc).__name__})
        return {"status": "error", "items": [], "error": "memory_forget_failed"}
