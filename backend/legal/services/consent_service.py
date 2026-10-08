"""Protocol publishing and consent evidence services."""

import hashlib
from typing import Any, Dict, Optional

from django.db import transaction
from django.utils import timezone

from audit.models import AuditEvent
from audit.services import AuditLedgerService

from ..models import LegalProtocol, LegalProtocolVersion, UserConsentRecord


def compute_content_hash(content: str) -> str:
    """Return SHA-256 hash for protocol content."""
    return hashlib.sha256((content or '').encode('utf-8')).hexdigest()


class ConsentService:
    """Service for protocol version publishing and user consent recording."""

    @staticmethod
    @transaction.atomic
    def publish_protocol_version(
        *,
        protocol: LegalProtocol,
        version: str,
        title: str,
        content: str,
        actor=None,
        source_url: str = '',
        effective_at=None,
    ) -> LegalProtocolVersion:
        """Create or update a protocol version and mark it as published."""
        protocol_version, _ = LegalProtocolVersion.objects.update_or_create(
            protocol=protocol,
            version=version,
            defaults={
                'title': title,
                'content': content,
                'content_hash': compute_content_hash(content),
                'source_url': source_url,
                'effective_at': effective_at,
                'published_at': timezone.now(),
                'is_published': True,
                'created_by': actor if getattr(actor, 'is_authenticated', True) else None,
            },
        )
        AuditEvent.log(
            category='admin_action',
            summary=f'Published protocol {protocol.key} v{version}',
            user=actor,
            detail={'protocol_id': protocol.id, 'version_id': protocol_version.id},
        )
        AuditLedgerService.append_entry(
            event_category='consent_sign',
            object_type='legal.LegalProtocolVersion',
            object_id=protocol_version.id,
            actor=actor,
            payload={
                'action': 'publish_protocol_version',
                'protocol_id': protocol.id,
                'protocol_key': protocol.key,
                'version': version,
                'content_hash': protocol_version.content_hash,
            },
        )
        return protocol_version

    @staticmethod
    @transaction.atomic
    def sign_protocol(
        *,
        user,
        protocol_version: LegalProtocolVersion,
        consent_method: str = 'clickwrap',
        evidence: Optional[Dict[str, Any]] = None,
        request=None,
    ) -> UserConsentRecord:
        """Record user consent and attach a hash-chain ledger entry."""
        evidence = evidence or {}
        if request:
            evidence.setdefault('path', request.path)
            evidence.setdefault('method', request.method)

        consent, _ = UserConsentRecord.objects.get_or_create(
            user=user,
            protocol_version=protocol_version,
            defaults={
                'consent_method': consent_method,
                'evidence': evidence,
                'ip_address': AuditEvent._get_client_ip(request) if request else None,
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500] if request else '',
            },
        )
        if not consent.ledger_entry_id:
            ledger_entry = AuditLedgerService.append_entry(
                event_category='consent_sign',
                object_type='legal.UserConsentRecord',
                object_id=consent.id,
                actor=user,
                payload={
                    'user_id': user.id,
                    'protocol_version_id': protocol_version.id,
                    'protocol_key': protocol_version.protocol.key,
                    'version': protocol_version.version,
                    'content_hash': protocol_version.content_hash,
                    'consent_method': consent.consent_method,
                    'evidence': consent.evidence,
                },
            )
            consent.ledger_entry = ledger_entry
            consent.save(update_fields=['ledger_entry'])

        AuditEvent.log(
            category='consent_sign',
            summary=f'User signed protocol {protocol_version.protocol.key} v{protocol_version.version}',
            user=user,
            request=request,
            detail={
                'consent_id': consent.id,
                'protocol_version_id': protocol_version.id,
            },
        )
        return consent
