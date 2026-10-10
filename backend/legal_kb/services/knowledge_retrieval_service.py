"""Leak-safe semantic knowledge retrieval shared by learning agents.

This is a thin facade over :class:`LegalRetrievalService`. It keeps a single
vector store / embedding entry point (no parallel RAG stack) while enforcing a
teaching-safe source allowlist: challenge solution text is never exposed to the
learner-facing agents, so only concepts, approved articles/resources and legal
clauses are returned by default.
"""

from typing import Dict, List, Optional

from django.conf import settings

from .retrieval_service import LegalRetrievalService


# Challenge chunks can embed solution material, so they stay out of the
# learner-facing allowlist by default (same policy as the tutoring loop).
DEFAULT_SAFE_SOURCE_TYPES = (
    'knowledge_concept',
    'article',
    'resource',
    'legal_clause',
)


class SafeKnowledgeRetrievalService:
    """Return normalized, teaching-safe knowledge items via semantic retrieval."""

    def __init__(
        self,
        retrieval_service: Optional[LegalRetrievalService] = None,
        safe_source_types=None,
    ):
        self.retrieval_service = retrieval_service or LegalRetrievalService()
        configured = safe_source_types or getattr(
            settings, 'KNOWLEDGE_RAG_SAFE_SOURCE_TYPES', None
        )
        self.safe_source_types = tuple(configured or DEFAULT_SAFE_SOURCE_TYPES)

    def retrieve(
        self,
        *,
        query: str,
        top_k: int = 8,
        user=None,
        extra_filters: Optional[Dict] = None,
    ) -> List[Dict]:
        """Return normalized knowledge items, or an empty list when query is blank."""
        text = str(query or '').strip()
        if not text:
            return []
        filters = {'source_type': list(self.safe_source_types)}
        if extra_filters:
            filters.update(extra_filters)
        matches = self.retrieval_service.retrieve(
            query=text,
            top_k=top_k,
            filters=filters,
            user=user,
        )
        return [self._normalize(match) for match in matches]

    def _normalize(self, match: Dict) -> Dict:
        source_type = match.get('source_type') or ''
        text = match.get('text') or ''
        metadata = match.get('metadata') or {}
        return {
            'source_type': source_type,
            'source_id': match.get('object_id'),
            'object_id': match.get('object_id'),
            'title': match.get('title') or '未命名资料',
            'summary': self._excerpt(text, 260),
            'text': text,
            'category': self._category(source_type, metadata),
            'score': match.get('score', 0),
            'rrf_score': match.get('rrf_score', 0),
            'url': self._entry_url(source_type, match.get('object_id'), metadata),
            'metadata': metadata,
            'retrieval': 'semantic',
        }

    def _category(self, source_type: str, metadata: Dict) -> str:
        if source_type == 'knowledge_concept':
            return str(metadata.get('concept_type') or '知识概念')
        return str(metadata.get('category_name') or metadata.get('category') or '')

    def _entry_url(self, source_type: str, object_id, metadata: Dict) -> str:
        if metadata.get('url'):
            return str(metadata['url'])
        if source_type == 'article':
            return f'/community/article/{object_id}'
        if source_type == 'resource':
            return f'/resources?highlight_resource={object_id}&resource={object_id}'
        return ''

    @staticmethod
    def _excerpt(text: str, limit: int) -> str:
        value = ' '.join(str(text or '').split())
        if len(value) <= limit:
            return value
        return value[: limit - 3].rstrip() + '...'
