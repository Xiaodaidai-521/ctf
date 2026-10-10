"""Legal knowledge retrieval service."""

import logging
import re
import time
from typing import Dict, List, Optional

from django.conf import settings
from django.db import connection
from django.db.models import Q

from ..models import LegalKnowledgeEmbedding, LegalRetrievalLog
from .embedding_service import EmbeddingService, cosine_similarity
from .visibility import apply_embedding_visibility


logger = logging.getLogger(__name__)


class LegalRetrievalService:
    """Retrieve legal knowledge chunks using vector similarity fallback."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or EmbeddingService()

    def retrieve(self, *, query: str, top_k: int = 8, filters: Optional[Dict] = None, user=None) -> List[Dict]:
        """Return top chunks via hybrid (vector + lexical) RRF fusion, and log the query."""
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

        # Enforce uploaded-document visibility at the shared query layer so that
        # teacher-facing RAG cannot surface staff-only documents. Non-document
        # rows are unaffected; anonymous/internal callers fail closed.
        queryset = apply_embedding_visibility(queryset, user)

        results = None
        if connection.vendor == 'postgresql' and len(query_embedding) == 1024:
            try:
                results = self._retrieve_with_pgvector(query, query_embedding, queryset, top_k)
            except Exception as exc:
                # Keep the portable JSON + lexical path available during a
                # partial deployment or when pgvector has not been rebuilt yet.
                logger.warning('pgvector retrieval unavailable; using fallback: %s', exc)
                results = None
        if not results:
            results = self._retrieve_portable(query, query_embedding, queryset, top_k)

        return self._record_results(
            query=query,
            top_k=top_k,
            filters=filters,
            results=results,
            started=started,
            user=user,
        )

    def _retrieve_with_pgvector(self, query, query_embedding, queryset, top_k):
        """Use the pgvector ANN index for recall, then fuse with a lexical arm."""
        from pgvector.django import CosineDistance

        pool_size = max(top_k * 4, 40)
        vector_items = list(
            queryset.exclude(embedding_vector__isnull=True)
            .annotate(distance=CosineDistance('embedding_vector', query_embedding))
            .order_by('distance')[:pool_size]
        )
        if not vector_items:
            return None
        vector_scores = {item.id: max(0.0, 1 - float(item.distance)) for item in vector_items}
        lexical_items = self._lexical_candidate_pool(queryset, query, pool_size)
        candidates = self._dedupe_by_id(vector_items + lexical_items)
        return self._fuse(
            query=query,
            query_embedding=query_embedding,
            items=candidates,
            top_k=top_k,
            vector_scores=vector_scores,
            apply_threshold=False,
        )

    def _retrieve_portable(self, query, query_embedding, queryset, top_k):
        """Portable JSON + lexical path for SQLite/offline or pgvector fallback.

        The stored JSON ``embedding`` is always the 128-dim local vector, so the
        query must also be embedded locally here. (On PostgreSQL ``retrieve``
        builds a 1024-dim remote query vector for ANN; reusing it against the
        128-dim JSON vectors would mismatch and zero every vector score, silently
        degrading this fallback to lexical-only.)
        """
        local_query_embedding = self.embedding_service.embed_local_text(query)
        pool_items = list(queryset[:1000])
        return self._fuse(
            query=query,
            query_embedding=local_query_embedding,
            items=pool_items,
            top_k=top_k,
            vector_scores=None,
            apply_threshold=True,
        )

    def _lexical_candidate_pool(self, queryset, query, limit):
        """Fetch a bounded lexical candidate set so strong keyword hits survive."""
        tokens = sorted(
            {token for token in self._tokenize(query) if len(token) >= 3},
            key=len,
            reverse=True,
        )[:6]
        if not tokens:
            return []
        condition = Q()
        for token in tokens:
            condition |= Q(title__icontains=token) | Q(text__icontains=token)
        return list(queryset.filter(condition)[:limit])

    def _fuse(self, *, query, query_embedding, items, top_k, vector_scores=None, apply_threshold=False):
        """Fuse vector and lexical rankings with Reciprocal Rank Fusion (RRF)."""
        if not items:
            return []
        rrf_k = int(getattr(settings, 'LEGAL_KB_RRF_K', 60))

        scored = []
        for item in items:
            if vector_scores is not None and item.id in vector_scores:
                vector_score = vector_scores[item.id]
            else:
                vector_score = cosine_similarity(query_embedding, item.embedding)
            lexical_score = self._lexical_similarity(query, f'{item.title} {item.text}')
            scored.append({'item': item, 'vector': vector_score, 'lexical': lexical_score})

        vector_rank = self._rank_map(scored, 'vector')
        lexical_rank = self._rank_map(scored, 'lexical')
        for row in scored:
            item_id = row['item'].id
            fused = 0.0
            if item_id in vector_rank:
                fused += 1.0 / (rrf_k + vector_rank[item_id])
            if item_id in lexical_rank:
                fused += 1.0 / (rrf_k + lexical_rank[item_id])
            row['fused'] = fused
            row['display'] = round(max(row['vector'], row['lexical']), 6)
        scored.sort(key=lambda row: (row['fused'], row['display']), reverse=True)

        threshold = float(getattr(settings, 'LEGAL_KB_SCORE_THRESHOLD', 0.35)) if apply_threshold else 0.0
        results = []
        for row in scored:
            if row['display'] < threshold:
                continue
            item = row['item']
            results.append({
                'id': item.id,
                'source_type': item.source_type,
                'object_id': item.object_id,
                'title': item.title,
                'text': item.text,
                'score': row['display'],
                'rrf_score': round(row['fused'], 6),
                'metadata': item.metadata,
            })
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def _rank_map(scored, key):
        """Map item id -> 0-based rank, including only items with positive signal."""
        ranked = sorted(
            (row for row in scored if row[key] > 0),
            key=lambda row: row[key],
            reverse=True,
        )
        return {row['item'].id: rank for rank, row in enumerate(ranked)}

    @staticmethod
    def _dedupe_by_id(items):
        seen = set()
        unique = []
        for item in items:
            if item.id in seen:
                continue
            seen.add(item.id)
            unique.append(item)
        return unique

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
