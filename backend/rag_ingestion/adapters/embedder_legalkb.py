"""Embedder adapter wrapping the existing ``legal_kb`` EmbeddingService."""

from typing import List

from ..interfaces import Chunk, EmbeddedChunk


class LegalKbEmbedder:
    """Produce both the semantic vector and the portable local vector."""

    def __init__(self, embedding_service=None):
        if embedding_service is None:
            from legal_kb.services.embedding_service import EmbeddingService

            embedding_service = EmbeddingService()
        self.embedding_service = embedding_service

    def embed(self, chunks: List[Chunk]) -> List[EmbeddedChunk]:
        if not chunks:
            return []
        texts = [chunk.text for chunk in chunks]
        # embed_many returns remote semantic vectors when configured, else the
        # deterministic local vector (never raises; it self-degrades).
        semantic_vectors = self.embedding_service.embed_many(texts)
        model = self.embedding_service.model
        embedded = []
        for chunk, vector in zip(chunks, semantic_vectors):
            local_vector = self.embedding_service.embed_local_text(chunk.text)
            embedded.append(EmbeddedChunk(
                chunk=chunk,
                vector=list(vector),
                local_vector=local_vector,
                model=model,
                dimension=len(vector),
            ))
        return embedded
