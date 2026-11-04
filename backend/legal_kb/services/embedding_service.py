"""Configured semantic embeddings; non-semantic local hashing is opt-in only."""

import hashlib
import json
import logging
import math
import os
from typing import Iterable, List

from django.conf import settings


logger = logging.getLogger(__name__)


class EmbeddingUnavailableError(RuntimeError):
    """A safe, content-free provider/configuration error suitable for logs."""


class EmbeddingService:
    """Generate one canonical vector for both JSON and optional pgvector storage.

    Initialization is lazy: lexical-only and task-scoped consumers need no API
    configuration. Calling embed_many without a provider raises, never hashes.
    """

    STORAGE_VERSION = 'canonical-vector-v2'

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
        self.dimension = int(dimension if dimension is not None else getattr(settings, 'EMBEDDING_DIMENSION', default_dimension))
        if self.provider == 'local':
            self.model, self.dimension = 'local-hash-v1', 128
        configured_batch_size = int(getattr(settings, 'EMBEDDING_BATCH_SIZE', 10) or 10)
        # Keep batches conservative across OpenAI-compatible embedding providers.
        self.batch_size = max(1, min(configured_batch_size, defaults.get('max_batch_size', 10)))

    @property
    def uses_remote_provider(self) -> bool:
        return self.provider in self.REMOTE_PROVIDER_DEFAULTS and bool(self.api_key)

    @property
    def index_version(self) -> str:
        """Fingerprint vector space, not credentials or mutable source metadata.

        Chunking revision is recorded separately; re-embedding old chunks must
        not pretend that they have been re-chunked from the original document.
        """
        identity = {
            'format': self.STORAGE_VERSION,
            'provider': 'volcano' if self.provider == 'ark' else self.provider,
            'endpoint': self.base_url.rstrip('/') if self.provider != 'local' else '',
            'model': self.model,
            'dimension': self.dimension,
            'revision': str(getattr(settings, 'EMBEDDING_INDEX_REVISION', '') or
                            os.environ.get('EMBEDDING_INDEX_REVISION', '')),
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def validate_configuration(self):
        if self.provider == 'local':
            return
        if not self.uses_remote_provider or not self.model or self.dimension <= 0:
            raise EmbeddingUnavailableError(
                'Embedding provider is not configured. Set EMBEDDING_PROVIDER and credentials; '
                'EMBEDDING_PROVIDER=local explicitly enables non-semantic development hashing.'
            )

    def storage_fields(self, vector):
        """Validate and describe the same vector in both storage representations."""
        from django.db import connection

        self.validate_configuration()
        normalized = normalize_vector(vector, self.dimension)
        return {
            'embedding': normalized,
            'embedding_vector': normalized if connection.vendor == 'postgresql' and self.dimension == 1024 else None,
            'embedding_model': self.model,
            'embedding_dimension': self.dimension,
            'index_version': self.index_version,
        }

    def matches_index(self, item) -> bool:
        return (
            item.index_version == self.index_version
            and item.embedding_model == self.model
            and item.embedding_dimension == self.dimension
            and valid_vector(item.embedding, self.dimension)
        )

    def compatible_queryset(self, queryset):
        return queryset.filter(
            index_version=self.index_version,
            embedding_model=self.model,
            embedding_dimension=self.dimension,
        )

    def _local_embed_text(self, text: str) -> List[float]:
        vector = [0.0] * 128
        for index, char in enumerate(text or ''):
            bucket = (ord(char) + index) % len(vector)
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_local_text(self, text: str) -> List[float]:
        """Explicit legacy/local utility; never used as an automatic fallback."""
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
        if sorted(item.index for item in response.data) != list(range(len(texts))):
            raise ValueError('Embedding response indexes are incomplete or duplicated')
        vectors = [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(texts) or any(len(vector) != self.dimension for vector in vectors):
            raise ValueError(f'{self.provider} returned an unexpected embedding shape')
        return vectors

    def embed_text(self, text: str) -> List[float]:
        """Return the configured vector or raise a sanitized provider error."""
        return self.embed_many([text])[0]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        """Return embeddings in batches accepted by the configured provider."""
        values = [str(text or '') for text in texts]
        if not values:
            return []
        try:
            self.validate_configuration()
            if self.provider == 'local':
                logger.warning('Non-semantic local hashing explicitly enabled; not suitable for production recall.')
                return [self._local_embed_text(text) for text in values]
            vectors = []
            for start in range(0, len(values), self.batch_size):
                batch = values[start:start + self.batch_size]
                result = self._remote_embed_many(batch)
                if len(result) != len(batch):
                    raise ValueError('Unexpected embedding count')
                vectors.extend(normalize_vector(vector, self.dimension) for vector in result)
            return vectors
        except EmbeddingUnavailableError:
            logger.error('Embeddings disabled: provider configuration is missing or invalid.')
            raise
        except Exception:
            # SDK exceptions can include request text, credentials and URLs.
            logger.error('Embedding request failed; no local fallback was used.')
            raise EmbeddingUnavailableError('Embedding request failed; check provider configuration and availability.') from None


def valid_vector(vector, dimension):
    return (
        isinstance(vector, (list, tuple)) and len(vector) == dimension
        and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                for value in vector)
    )


def normalize_vector(vector, dimension):
    if not valid_vector(vector, dimension):
        raise EmbeddingUnavailableError('Embedding has invalid dimension or non-finite values.')
    norm = math.hypot(*vector)
    if not math.isfinite(norm):
        raise EmbeddingUnavailableError('Embedding has invalid magnitude.')
    return [value / norm for value in vector] if norm else list(vector)


def cosine_similarity(left: List[float], right: List[float]) -> float:
    """Compute true cosine for portable vectors, rejecting malformed legacy data."""
    if not left or not valid_vector(left, len(left)) or not valid_vector(right, len(left)):
        return 0.0
    left_norm, right_norm = math.hypot(*left), math.hypot(*right)
    if not left_norm or not right_norm or not math.isfinite(left_norm * right_norm):
        return 0.0
    return max(-1.0, min(1.0, sum((a / left_norm) * (b / right_norm) for a, b in zip(left, right))))