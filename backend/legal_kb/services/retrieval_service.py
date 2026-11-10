"""Legal knowledge retrieval service."""

import logging
import re
import time
from typing import Dict, List, Optional

from django.conf import settings
from django.db import connection
from django.db.models import Q

from data_security.adapters.django.rag import protect_rag, protect_rag_fields
from rag_ingestion.registry import get_embedding_service

from ..models import LegalKnowledgeEmbedding, LegalRetrievalLog
from .embedding_service import EmbeddingService, cosine_similarity
from .visibility import apply_embedding_visibility


logger = logging.getLogger(__name__)


class LegalRetrievalService:
    """Retrieve legal knowledge chunks using vector similarity fallback."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service if embedding_service is not None else get_embedding_service()

    def retrieve(self, *, query: str, top_k: int = 8, filters: Optional[Dict] = None, user=None) -> List[Dict]:
        """Return hybrid RRF results and log the protected query."""
        _, results = self.retrieve_groups(query=query, groups=[filters or {}], top_k=top_k, user=user)
        return results[0]

    def retrieve_groups(self, *, query: str, groups: List[Dict], top_k: int = 8, user=None) -> tuple[str, List[List[Dict]]]:
        """Share one protected query vector across independently scoped result groups."""
        started = time.perf_counter()
        query = protect_rag(query, object_ref='rag/query', object_version='v1', outlet='embedding')
        query_embedding = (
            self.embedding_service.embed_text(query)
            if connection.vendor == 'postgresql'
            else self.embedding_service.embed_local_text(query)
        )
        grouped = []
        for filters in groups:
            queryset = LegalKnowledgeEmbedding.objects.all()
            source_type = filters.get('source_type')
            if source_type:
                if isinstance(source_type, (list, tuple, set)):
                    queryset = queryset.filter(source_type__in=source_type)
                else:
                    queryset = queryset.filter(source_type=source_type)
            if filters.get('object_id') is not None:
                queryset = queryset.filter(object_id=filters['object_id'])
            if filters.get('challenge_id') is not None:
                from django.contrib.contenttypes.models import ContentType
                from ai_assistant.models import ChallengeKnowledgePack
                from challenges.models import Challenge

                challenge_id = filters['challenge_id']
                packs = ChallengeKnowledgePack.objects.filter(challenge_id=challenge_id).values('pk')
                queryset = queryset.filter(
                    Q(content_type=ContentType.objects.get_for_model(Challenge), object_id=challenge_id) |
                    Q(content_type=ContentType.objects.get_for_model(ChallengeKnowledgePack), object_id__in=packs))

            # Uploaded-document visibility stays at the shared query layer;
            # anonymous/internal callers cannot see document rows.
            queryset = apply_embedding_visibility(queryset, user)
            results = None
            if connection.vendor == 'postgresql' and len(query_embedding) == 1024:
                try:
                    results = self._retrieve_with_pgvector(query, query_embedding, queryset, top_k)
                except Exception as exc:
                    # Preserve the portable local-vector path without claiming
                    # that it is the remote model's semantic result.
                    logger.warning('pgvector_retrieval_unavailable',
                                   extra={'error_type': type(exc).__name__})
            if not results:
                results = self._retrieve_portable(query, query_embedding, queryset, top_k)
            grouped.append(self._record_results(query=query, top_k=top_k, filters=filters,
                results=results, started=started, user=user))
        return query, grouped

    def _retrieve_with_pgvector(self, query, query_embedding, queryset, top_k):
        """Use the pgvector ANN index for recall, then fuse with a lexical arm."""
        from pgvector.django import CosineDistance

        pool_size = max(top_k * 4, 40)
        vector_queryset = queryset.exclude(embedding_vector__isnull=True)
        vector_space = getattr(self.embedding_service, 'vector_space', '')
        if vector_space:
            vector_queryset = vector_queryset.filter(metadata__vector_space=vector_space)
        vector_items = list(
            vector_queryset.annotate(distance=CosineDistance('embedding_vector', query_embedding))
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

        declared_space = getattr(self.embedding_service, 'vector_space', '')
        scored = []
        for item in items:
            if vector_scores is not None:
                vector_score = vector_scores.get(item.id, 0.0)
                space = declared_space if item.id in vector_scores else ''
                mode = getattr(self.embedding_service, 'retrieval_mode', 'unknown') if space else 'unknown'
            elif declared_space and (item.embedding_model != 'local-hash-v1' or
                                     item.embedding_dimension != 128):
                vector_score, mode, space = 0.0, 'lexical', ''
            else:
                vector_score = cosine_similarity(query_embedding, item.embedding)
                mode = 'deterministic' if declared_space else 'unknown'
                space = EmbeddingService.LOCAL_VECTOR_SPACE if declared_space else ''
            lexical_score = self._lexical_similarity(query, f'{item.title} {item.text}')
            if vector_score <= 0 and lexical_score > 0:
                mode, space = 'lexical', ''
            scored.append({'item': item, 'vector': vector_score, 'lexical': lexical_score,
                           'retrieval': mode, 'vector_space': space})

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
                'retrieval': row['retrieval'],
                'vector_space': row['vector_space'],
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
        results = [protect_rag_fields(item, text_fields=('text',),
                   object_ref=f'rag/retrieval/{item["id"]}', object_version='v1') for item in results]
        filters = protect_rag(filters, object_ref='rag/query-filters', object_version='v1', outlet='rag')
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
