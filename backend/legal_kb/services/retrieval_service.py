"""Legal knowledge retrieval service."""

import logging
import re
import time
from typing import Dict, List, Optional

from django.conf import settings
from django.db import connection

from ..models import LegalKnowledgeEmbedding, LegalRetrievalLog
from .embedding_service import EmbeddingService, cosine_similarity


logger = logging.getLogger(__name__)


class LegalRetrievalService:
    """Retrieve legal knowledge chunks using vector similarity fallback."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or EmbeddingService()

    def retrieve(self, *, query: str, top_k: int = 8, filters: Optional[Dict] = None, user=None) -> List[Dict]:
        """Return top matching chunks and write a retrieval log."""
        started = time.perf_counter()
        filters = filters or {}
        query_embedding = (
            self.embedding_service.embed_text(query)
            if connection.vendor == 'postgresql'
            else self.embedding_service.embed_local_text(query)
        )
        queryset = LegalKnowledgeEmbedding.objects.all()
        source_type = filters.get('source_type')
        if source_type:
            if isinstance(source_type, (list, tuple, set)):
                queryset = queryset.filter(source_type__in=source_type)
            else:
                queryset = queryset.filter(source_type=source_type)

        if connection.vendor == 'postgresql' and len(query_embedding) == 1024:
            try:
                from pgvector.django import CosineDistance

                vector_items = list(
                    queryset.exclude(embedding_vector__isnull=True)
                    .annotate(distance=CosineDistance('embedding_vector', query_embedding))
                    .order_by('distance')[:top_k]
                )
                if vector_items:
                    results = [
                        {
                            'id': item.id,
                            'source_type': item.source_type,
                            'object_id': item.object_id,
                            'title': item.title,
                            'text': item.text,
                            'score': round(max(0.0, 1 - float(item.distance)), 6),
                            'metadata': item.metadata,
                        }
                        for item in vector_items
                    ]
                    return self._record_results(
                        query=query,
                        top_k=top_k,
                        filters=filters,
                        results=results,
                        started=started,
                        user=user,
                    )
            except Exception as exc:
                # Keep the portable JSON + lexical path available during a
                # partial deployment or when pgvector has not been rebuilt yet.
                logger.warning('pgvector retrieval unavailable; using fallback: %s', exc)

        scored = []
        for item in queryset[:1000]:
            vector_score = cosine_similarity(query_embedding, item.embedding)
            lexical_score = self._lexical_similarity(query, f'{item.title} {item.text}')
            score = max(vector_score, lexical_score)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        score_threshold = float(getattr(settings, 'LEGAL_KB_SCORE_THRESHOLD', 0.35))
        results = [
            {
                'id': item.id,
                'source_type': item.source_type,
                'object_id': item.object_id,
                'title': item.title,
                'text': item.text,
                'score': round(score, 6),
                'metadata': item.metadata,
            }
            for score, item in scored[:top_k]
            if score >= score_threshold
        ]
        return self._record_results(
            query=query,
            top_k=top_k,
            filters=filters,
            results=results,
            started=started,
            user=user,
        )

    def _record_results(self, *, query, top_k, filters, results, started, user):
        latency_ms = int((time.perf_counter() - started) * 1000)
        LegalRetrievalLog.objects.create(
            query=query,
            top_k=top_k,
            filters=filters,
            results=results,
            latency_ms=latency_ms,
            user=user if getattr(user, 'is_authenticated', True) else None,
        )
        return results

    def _lexical_similarity(self, query: str, text: str) -> float:
        """Return a small lexical relevance score for short Chinese audit queries."""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return 0
        text_tokens = self._tokenize(text)
        if not text_tokens:
            return 0
        overlap = query_tokens.intersection(text_tokens)
        if any(len(token) >= 4 for token in overlap):
            return 0.45
        if any(len(token) >= 3 for token in overlap):
            return 0.38
        if len(overlap) >= 2:
            return len(overlap) / max(min(len(query_tokens), len(text_tokens)), 1)
        return len(overlap) / max(len(query_tokens), 1)

    def _tokenize(self, text: str) -> set:
        value = (text or '').lower()
        tokens = set(re.findall(r'[a-z0-9_+#.-]{2,}', value))
        chinese_runs = re.findall(r'[\u4e00-\u9fff]{2,}', value)
        for run in chinese_runs:
            tokens.add(run)
            for size in range(2, min(6, len(run)) + 1):
                for index in range(len(run) - size + 1):
                    tokens.add(run[index:index + size])
        return tokens
