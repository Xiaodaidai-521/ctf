"""Data-lab compatibility entry points for the shared frozen M6 handoff."""
from skill_review.services.handoff import dispatch_result, ingest_fact, retry_module1_notice
from skill_review.services import events  # Existing failure-injection and audit owner.

__all__ = ['dispatch_result', 'ingest_fact', 'retry_module1_notice']
