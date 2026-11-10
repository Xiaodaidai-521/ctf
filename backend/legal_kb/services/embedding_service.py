"""Explicit protected remote embeddings or deterministic local development vectors."""

import math
from ai_providers import get_manager
from typing import Iterable, List

from django.conf import settings


class EmbeddingService:
    """Generate embeddings for legal knowledge chunks.

    Remote providers use the injected, protected official-provider handle.
    Local mode uses deterministic vectors, not a local model. A configured
    remote provider fails closed; it never silently falls back to local mode.
    """

    VISION_MODEL = 'doubao-embedding-vision-251215'
    LOCAL_VECTOR_SPACE = 'local/local-hash-v1/128/raw-v1'
    REMOTE_PROVIDER_DEFAULTS = {
        'qwen': {
            'model': 'text-embedding-v3',
            'dimension': 1024,
            'max_batch_size': 10,
        },
        'volcano': {
            'model': VISION_MODEL,
            'dimension': 1024,
            'max_batch_size': 10,
        },
    }

    def __init__(self, dimension: int = None, model: str = None):
        self.provider = str(getattr(settings, 'EMBEDDING_PROVIDER', '') or '').strip().lower()
        self.provider = {'dashscope': 'qwen', 'ark': 'volcano'}.get(self.provider, self.provider)
        if self.provider and self.provider not in self.REMOTE_PROVIDER_DEFAULTS:
            raise RuntimeError('EMBEDDING_PROVIDER_DISABLED')
        defaults = self.REMOTE_PROVIDER_DEFAULTS.get(self.provider, {})
        self._handle = get_manager().get_provider(self.provider)
        configured_model = model or getattr(settings, 'EMBEDDING_MODEL', 'local-hash-v1')
        self.model = configured_model
        if self.provider in self.REMOTE_PROVIDER_DEFAULTS and self.model == 'local-hash-v1':
            self.model = defaults['model']
        default_dimension = defaults.get('dimension', 128)
        self.dimension = int(dimension or getattr(settings, 'EMBEDDING_DIMENSION', default_dimension))
        if dimension is None and self.provider in self.REMOTE_PROVIDER_DEFAULTS and self.dimension == 128:
            self.dimension = defaults['dimension']
        if self.uses_vision and self.dimension != 1024:
            raise RuntimeError('EMBEDDING_DIMENSION_REQUIRES_APPROVAL')
        configured_batch_size = int(getattr(settings, 'EMBEDDING_BATCH_SIZE', 10) or 10)
        # Keep batches conservative across OpenAI-compatible embedding providers.
        self.batch_size = max(1, min(configured_batch_size, defaults.get('max_batch_size', 10)))

    @property
    def uses_remote_provider(self) -> bool:
        return self.provider in self.REMOTE_PROVIDER_DEFAULTS

    @property
    def uses_vision(self) -> bool:
        return self.provider == 'volcano' and self.model == self.VISION_MODEL

    @property
    def vector_space(self) -> str:
        # raw-v1 deliberately adds no query/corpus instruction on either side.
        if not self.uses_remote_provider:
            return self.LOCAL_VECTOR_SPACE
        return f'{self.provider}/{self.model}/{self.dimension}/raw-v1'

    @property
    def retrieval_mode(self) -> str:
        return 'semantic' if self.uses_remote_provider else 'deterministic'

    def _local_embed_text(self, text: str) -> List[float]:
        vector = [0.0] * 128
        for index, char in enumerate(text or ''):
            bucket = (ord(char) + index) % len(vector)
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_local_text(self, text: str) -> List[float]:
        """Return portable deterministic vectors, never a remote-error fallback."""
        return self._local_embed_text(text)

    def _remote_embed_many(self, texts: List[str]) -> List[List[float]]:
        if self._handle is None:
            raise RuntimeError('EMBEDDING_NOT_CONFIGURED')
        if self.uses_vision:
            responses = [self._handle.embed([{'type': 'text', 'text': text}],
                         model=self.model, dimensions=1024) for text in texts]
            expected = 1
        else:
            responses = [self._handle.embed(texts, model=self.model)]
            expected = len(texts)
        if any(len(response.vectors) != expected or
               any(len(vector) != self.dimension for vector in response.vectors) for response in responses):
            raise ValueError('EMBEDDING_SHAPE_INVALID')
        return [list(vector) for response in responses for vector in response.vectors]

    def embed_text(self, text: str) -> List[float]:
        """Return the configured vector type; remote failures propagate."""
        return self.embed_many([text])[0]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        """Return embeddings in batches accepted by the configured provider."""
        values = [str(text or '') for text in texts]
        if not values:
            return []
        if not self.uses_remote_provider:
            return [self._local_embed_text(text) for text in values]

        vectors = []
        for start in range(0, len(values), self.batch_size):
            vectors.extend(self._remote_embed_many(values[start:start + self.batch_size]))
        return vectors


def cosine_similarity(left: List[float], right: List[float]) -> float:
    """Compute cosine similarity for two vectors."""
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))