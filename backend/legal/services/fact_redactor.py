"""Allowlist-based redaction for facts sent to legal analysis."""

import re

from django.conf import settings

REDACTION_VERSION = 'v1'
TOKEN_PATTERN = re.compile(
    r'(?i)(authorization|token|password|secret|cookie)\s*[:=]\s*[^\s,;]+',
)
FLAG_PATTERN = re.compile(r'(?i)flag\s*\{[^}]{1,500}\}')


def redact_manual_notes(value: str) -> str:
    """Remove common secrets and enforce the configured input bound."""
    limit = int(getattr(settings, 'LEGAL_FACT_MAX_MANUAL_CHARS', 4000))
    text = (value or '')[:limit]
    text = TOKEN_PATTERN.sub(r'\1=[REDACTED]', text)
    return FLAG_PATTERN.sub('flag{[REDACTED]}', text).strip()


def safe_container_event(detail: dict) -> dict:
    """Return only fields required to derive an exercise fact snapshot."""
    detail = detail or {}
    container = detail.get('container') or {}
    challenge = detail.get('challenge') or {}
    return {
        'event_schema_version': str(
            detail.get('event_schema_version') or detail.get('schema_version') or '1'
        ),
        'operation_id': str(detail.get('operation_id') or ''),
        'correlation_id': str(detail.get('correlation_id') or ''),
        'container_instance_id': detail.get('container_instance_id') or container.get('id'),
        'challenge_id': detail.get('challenge_id') or challenge.get('id'),
        'action': str(detail.get('action') or ''),
        'result': str(detail.get('result') or ''),
        'image': str(detail.get('image') or '')[:300],
        'network': str(detail.get('network') or '')[:120],
        'cpu_limit': detail.get('cpu_limit'),
        'memory_limit': str(detail.get('memory_limit') or '')[:80],
        'timestamp': str(detail.get('timestamp') or ''),
    }
