"""Self-contained document ingestion pipeline for the shared RAG store.

Design goals (see docs/agent-rag-analysis-and-plan.md section 7-8):
- Low coupling: the pipeline core depends only on the Protocols in
  ``interfaces.py``. Every third-party parser/library lives in ``adapters/``
  and is imported lazily, so a missing optional dependency only disables that
  one format instead of breaking the whole pipeline.
- Single store: embeddings are written into the existing
  ``legal_kb.LegalKnowledgeEmbedding`` table under ``source_type='document'``;
  no parallel vector store is introduced.
"""
