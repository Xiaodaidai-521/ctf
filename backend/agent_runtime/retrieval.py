import logging
from typing import Any, Dict, List, Optional

from django.conf import settings

from .tool_registry import LearningToolRegistry


logger = logging.getLogger(__name__)


class LearningRetrievalService:
    """Build learning context from existing platform data."""

    def __init__(
        self,
        *,
        tool_registry: Optional[LearningToolRegistry] = None,
        knowledge_service=None,
    ):
        self.tool_registry = tool_registry or LearningToolRegistry()
        self._knowledge_service = knowledge_service

    def retrieve(self, *, user, query: str) -> Dict[str, Any]:
        used_tools = []
        tool_docs = []

        for tool_name in self.tool_registry.available_learning_tools():
            result = self.tool_registry.run(tool_name, user=user, query=query)
            used_tools.append({
                'name': tool_name,
                'status': result.get('status', 'unknown'),
                'item_count': len(result.get('items', [])),
                'error': result.get('error', ''),
            })
            tool_docs.extend(self._documents_from_tool(tool_name, result.get('items', [])))

        semantic_docs = self._semantic_documents(query=query, user=user)

        # Select which docs enter the context BEFORE numbering, reserving a quota
        # for semantic docs. This keeps source references, verifier evidence and
        # the actual prompt consistent (semantic docs are no longer appended past
        # the context cap and silently dropped).
        retrieved_docs = self._select_context_docs(tool_docs, semantic_docs)
        for index, doc in enumerate(retrieved_docs, start=1):
            doc['source_ref'] = f'S{index}'

        return {
            'used_tools': used_tools,
            'retrieved_docs': retrieved_docs,
            'knowledge_context': self._build_context(retrieved_docs),
        }

    def _select_context_docs(self, tool_docs, semantic_docs):
        """Cap total docs while guaranteeing a slot quota for semantic docs."""
        limit = int(getattr(settings, 'AGENT_RUNTIME_CONTEXT_LIMIT', 12) or 12)
        if limit <= 0:
            return []
        if not semantic_docs:
            return list(tool_docs)[:limit]
        quota = min(
            len(semantic_docs),
            int(getattr(settings, 'AGENT_RUNTIME_SEMANTIC_TOP_K', 4) or 4),
            limit,
        )
        tool_slots = max(limit - quota, 0)
        selected = list(tool_docs)[:tool_slots] + list(semantic_docs)[:quota]
        if len(selected) < limit:
            # Backfill any unused semantic slots with remaining tool docs.
            selected += list(tool_docs)[tool_slots:][: limit - len(selected)]
        return selected[:limit]

    def _semantic_documents(self, *, query: str, user) -> List[Dict[str, Any]]:
        """Append teaching-safe semantic recall from the shared vector store.

        Opt-out via ``AGENT_RUNTIME_SEMANTIC_RETRIEVAL=false``. Any failure
        degrades to no semantic docs so the tool-based context still returns.
        """
        if not getattr(settings, 'AGENT_RUNTIME_SEMANTIC_RETRIEVAL', True):
            return []
        text = str(query or '').strip()
        if not text:
            return []
        top_k = int(getattr(settings, 'AGENT_RUNTIME_SEMANTIC_TOP_K', 4) or 4)
        try:
            items = self._get_knowledge_service().retrieve(
                query=text,
                top_k=top_k,
                user=user if getattr(user, 'is_authenticated', False) else None,
            )
        except Exception as exc:
            logger.warning(
                'agent_runtime_semantic_retrieval_failed',
                extra={
                    'event': 'agent_runtime_semantic_retrieval_failed',
                    'error_type': type(exc).__name__,
                },
            )
            return []
        documents = []
        for item in items:
            excerpt = item.get('summary') or self._safe_excerpt(item.get('text') or '', 280)
            documents.append({
                'source_type': item.get('source_type') or 'knowledge',
                'source_id': item.get('object_id'),
                'title': item.get('title') or 'Knowledge reference',
                'excerpt': excerpt,
                'metadata': item.get('metadata') or {},
            })
        return documents

    def _get_knowledge_service(self):
        if self._knowledge_service is None:
            from legal_kb.services.knowledge_retrieval_service import (
                SafeKnowledgeRetrievalService,
            )

            self._knowledge_service = SafeKnowledgeRetrievalService()
        return self._knowledge_service


    def _documents_from_tool(self, tool_name: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        builders = {
            'read_student_profile': self._profile_doc,
            'read_user_knowledge_state': self._knowledge_state_doc,
            'read_learning_path_modules': self._learning_path_doc,
        }
        builder = builders.get(tool_name)
        if builder is None:
            return []
        return [builder(item) for item in items]

    def _profile_doc(self, item: Dict[str, Any]) -> Dict[str, Any]:
        parts = [
            f"Learning goals: {item.get('learning_goals') or 'not set'}",
            f"Self assessed skills: {item.get('self_assessed_skills') or {}}",
            f"Preferred pace: {item.get('preferred_pace') or 'unknown'}",
            f"Preferred modality: {item.get('preferred_modality') or []}",
            f"Daily study hours: {item.get('daily_study_hours')}",
        ]
        return {
            'source_type': 'student_profile',
            'source_id': item.get('id'),
            'title': 'Student learning profile',
            'excerpt': '; '.join(parts),
            'metadata': item,
        }

    def _knowledge_state_doc(self, item: Dict[str, Any]) -> Dict[str, Any]:
        title = item.get('concept_name') or 'Knowledge concept'
        excerpt = (
            f"{title}: mastery {item.get('mastery_level')}, "
            f"recall {item.get('recall_probability')}, "
            f"lab attempts {item.get('lab_attempts')}, "
            f"lab successes {item.get('lab_successes')}. "
            f"Recommended intervention: {item.get('recommended_intervention') or 'none'}. "
            f"Description: {item.get('concept_description') or ''}"
        )
        return {
            'source_type': 'user_knowledge_state',
            'source_id': item.get('id'),
            'title': title,
            'excerpt': excerpt,
            'metadata': item,
        }

    def _learning_path_doc(self, item: Dict[str, Any]) -> Dict[str, Any]:
        title = item.get('title') or 'Learning module'
        excerpt = (
            f"{item.get('learning_path_title')}: {title}. "
            f"{item.get('description') or ''} "
            f"{self._safe_excerpt(item.get('content') or '', 280)}"
        )
        return {
            'source_type': 'learning_path',
            'source_id': item.get('id'),
            'title': title,
            'excerpt': excerpt,
            'metadata': item,
        }

    def _build_context(self, docs: List[Dict[str, Any]]) -> str:
        if not docs:
            return ''

        lines = ['Use the following platform learning context. Cite sources with [S1] style references:']
        for doc in docs:
            lines.append(
                f"[{doc.get('source_ref')}] {doc.get('title')} "
                f"({doc.get('source_type')}): {doc.get('excerpt')}"
            )
        return '\n'.join(lines)

    def _safe_excerpt(self, value: str, limit: int) -> str:
        text = ' '.join(str(value or '').split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + '...'
