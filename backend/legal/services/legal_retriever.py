"""Retriever adapter for compliance analysis workflows."""

from typing import Dict, List, Optional

from django.conf import settings

from legal_kb.services.retrieval_service import LegalRetrievalService


class LegalRetriever:
    """Retrieve legal knowledge evidence for an analysis task."""

    def __init__(self, retrieval_service: Optional[LegalRetrievalService] = None):
        self.retrieval_service = retrieval_service or LegalRetrievalService()

    def retrieve_for_task(self, task, *, actor=None, top_k: Optional[int] = None) -> List[Dict]:
        """Return ranked legal evidence candidates for a task."""
        query = self._build_query(task)
        return self.retrieval_service.retrieve(
            query=query,
            top_k=top_k or getattr(settings, 'LEGAL_KB_TOP_K', 8),
            filters={},
            user=actor,
        )

    def _build_query(self, task) -> str:
        """Build a retrieval query from task fields."""
        parts = [
            task.title,
            task.source_type,
            task.input_text,
        ]
        return '\n'.join([part for part in parts if part]).strip() or task.title
