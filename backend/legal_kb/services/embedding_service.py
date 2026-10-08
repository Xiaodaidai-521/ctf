"""Embedding service with remote providers and a deterministic local fallback."""

import logging
import math
import os
from typing import Iterable, List

from django.conf import settings


logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings for legal knowledge chunks.

    Remote providers use OpenAI-compatible embeddings endpoints when configured.
    The deterministic local vector keeps development, tests, and failed remote
    requests usable without network credentials.
    """

    REMOTE_PROVIDER_DEFAULTS = {
        'dashscope': {
            'api_key_env': 'QWEN_API_KEY',
            'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'model': 'text-embedding-v3',
            'dimension': 1024,
            'max_batch_size': 10,
        },
        'volcano': {
            'api_key_env': 'ARK_API_KEY',
            'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
            'model': 'doubao-embedding-text-240515',
            'dimension': 1024,
            'max_batch_size': 10,
        },
        'ark': {
            'api_key_env': 'ARK_API_KEY',
            'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
            'model': 'doubao-embedding-text-240515',
            'dimension': 1024,
            'max_batch_size': 10,
        },
    }

    def __init__(self, dimension: int = None, model: str = None):
        self.provider = str(getattr(settings, 'EMBEDDING_PROVIDER', '') or '').strip().lower()
        defaults = self.REMOTE_PROVIDER_DEFAULTS.get(self.provider, {})
        self.api_key = (
            str(getattr(settings, 'EMBEDDING_API_KEY', '') or '').strip()
            or os.environ.get(defaults.get('api_key_env', ''), '').strip()
        )
        self.base_url = (
            str(getattr(settings, 'EMBEDDING_BASE_URL', '') or '').strip()
            or defaults.get('base_url', '')
        )
        configured_model = model or getattr(settings, 'EMBEDDING_MODEL', 'local-hash-v1')
        self.model = configured_model
        if self.provider in self.REMOTE_PROVIDER_DEFAULTS and self.model == 'local-hash-v1':
            self.model = defaults['model']
        default_dimension = defaults.get('dimension', 128)
        self.dimension = int(dimension or getattr(settings, 'EMBEDDING_DIMENSION', default_dimension))
        if self.provider in self.REMOTE_PROVIDER_DEFAULTS and self.dimension == 128:
            self.dimension = defaults['dimension']
        configured_batch_size = int(getattr(settings, 'EMBEDDING_BATCH_SIZE', 10) or 10)
        # Keep batches conservative across OpenAI-compatible embedding providers.
        self.batch_size = max(1, min(configured_batch_size, defaults.get('max_batch_size', 10)))

    @property
    def uses_remote_provider(self) -> bool:
        return self.provider in self.REMOTE_PROVIDER_DEFAULTS and bool(self.api_key)

    def _local_embed_text(self, text: str) -> List[float]:
        vector = [0.0] * 128
        for index, char in enumerate(text or ''):
            bucket = (ord(char) + index) % len(vector)
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_local_text(self, text: str) -> List[float]:
        """Return the stable 128-dimensional vector used by SQLite fallback."""
        return self._local_embed_text(text)

    def _remote_client(self):
        from openai import OpenAI

        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=20.0,
            max_retries=1,
        )

    def _remote_embed_many(self, texts: List[str]) -> List[List[float]]:
        request = {
            'model': self.model,
            'input': texts,
            'encoding_format': 'float',
        }
        if self.dimension:
            request['dimensions'] = self.dimension
        response = self._remote_client().embeddings.create(**request)
        vectors = [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(texts) or any(len(vector) != self.dimension for vector in vectors):
            raise ValueError(f'{self.provider} returned an unexpected embedding shape')
        return vectors

    def embed_text(self, text: str) -> List[float]:
        """Return a remote semantic vector when available, otherwise local hash."""
        return self.embed_many([text])[0]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        """Return embeddings in batches accepted by the configured provider."""
        values = [str(text or '') for text in texts]
        if not values:
            return []
        if not self.uses_remote_provider:
            return [self._local_embed_text(text) for text in values]

        try:
            vectors = []
            for start in range(0, len(values), self.batch_size):
                vectors.extend(self._remote_embed_many(values[start:start + self.batch_size]))
            return vectors
        except Exception as exc:
            logger.warning('%s embeddings unavailable; using local fallback: %s', self.provider, exc)
            return [self._local_embed_text(text) for text in values]


def cosine_similarity(left: List[float], right: List[float]) -> float:
    """Compute cosine similarity for two vectors."""
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))