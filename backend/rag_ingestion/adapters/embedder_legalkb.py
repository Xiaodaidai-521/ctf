"""Embedder adapter wrapping the existing ``legal_kb`` EmbeddingService."""

from typing import List

from ..interfaces import Chunk, EmbeddedChunk


class LegalKbEmbedder:
    """Produce both the semantic vector and the portable local vector."""

    def __init__(self, embedding_service):
        self.embedding_service = embedding_service

    def embed(self, chunks: List[Chunk]) -> List[EmbeddedChunk]:
        if not chunks:
            return []
        texts = [chunk.text for chunk in chunks]
        # A configured remote provider fails closed; local mode is deterministic,
        # not a semantic model or a fallback for a failed provider call.
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
                vector_space=self.embedding_service.vector_space,
                retrieval_mode=self.embedding_service.retrieval_mode,
            ))
        return embedded
