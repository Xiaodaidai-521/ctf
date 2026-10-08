"""Structured knowledge retrieval agent reusing the existing knowledge packs/RAG."""

from __future__ import annotations

import logging
from collections.abc import Mapping

logger = logging.getLogger(__name__)


class KnowledgeAgent:
    DEFAULT_RESULT = {
        "knowledgePoint": "", "definition": "", "prerequisites": [], "keyPoints": [],
        "commonMistakes": [], "retrievalContext": [], "sources": [],
    }

    def analyze(self, *, query="", challenge_info=None, knowledge_point=""):
        if not str(query or knowledge_point or "").strip():
            return dict(self.DEFAULT_RESULT)
        try:
            from ai_assistant.service import MultiAgentChatService

            package = MultiAgentChatService().build_knowledge_context(
                str(query or knowledge_point), challenge_info, "category", 8,
            )
            items = [item for item in package.get("items", []) if isinstance(item, Mapping)][:8]
            point = str(knowledge_point or (challenge_info or {}).get("title") or query)[:120]
            definition = ""
            key_points = []
            prerequisites = []
            mistakes = []
            context = []
            sources = []
            for item in items:
                text = str(item.get("summary") or item.get("text") or item.get("content") or "")[:800]
                title = str(item.get("title") or item.get("source") or "")[:160]
                if not definition and text:
                    definition = text[:500]
                if title:
                    key_points.append(title)
                metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
                prerequisites.extend(list(metadata.get("prerequisites") or [])[:5])
                mistakes.extend(list(metadata.get("common_mistakes") or [])[:5])
                context.append({"title": title, "text": text, "score": item.get("score", 0)})
                sources.append({
                    "id": str(item.get("id") or item.get("object_id") or ""),
                    "title": title,
                    "type": str(item.get("source_type") or item.get("type") or "knowledge_pack"),
                })
            return {
                "knowledgePoint": point,
                "definition": definition,
                "prerequisites": prerequisites[:8],
                "keyPoints": key_points[:8],
                "commonMistakes": mistakes[:8],
                "retrievalContext": context,
                "sources": sources,
            }
        except Exception as exc:
            logger.warning(
                "knowledge_agent_fallback",
                extra={"event": "knowledge_agent_fallback", "error_type": type(exc).__name__},
            )
            return dict(self.DEFAULT_RESULT)

