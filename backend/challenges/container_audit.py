"""Helpers for tamper-evident audit records around challenge containers."""

import uuid

from django.db import transaction
from django.utils import timezone

from audit.models import AuditEvent
from audit.services import AuditLedgerService


FAILURE_ACTIONS = {'start_failed', 'stop_failed'}
AUDIT_SCHEMA_VERSION = '2'


def build_container_audit_payload(
    *,
    action,
    result,
    user=None,
    challenge=None,
    container=None,
    image='',
    port=None,
    network='',
    cpu_limit=None,
    memory_limit='',
    access_url='',
    error_message='',
    extra=None,
    operation_id='',
    correlation_id='',
):
    """Build the canonical payload shared by AuditEvent and ledger entries."""
    challenge = challenge or getattr(container, 'challenge', None)
    user = user or getattr(container, 'user', None)
    image = image or getattr(challenge, 'docker_image', '') or ''
    port = port if port is not None else getattr(container, 'port', None)
    operation_id = operation_id or str(uuid.uuid4())
    container_instance_id = getattr(container, 'id', None)
    return {
        'schema_version': AUDIT_SCHEMA_VERSION,
        'event_schema_version': AUDIT_SCHEMA_VERSION,
        'event_source': 'application',
        'operation_id': operation_id,
        'correlation_id': correlation_id or (
            f'container:{container_instance_id}' if container_instance_id else operation_id
        ),
        'container_instance_id': container_instance_id,
        'docker_container_id': getattr(container, 'container_id', ''),
        'challenge_id': getattr(challenge, 'id', None),
        'user_id': getattr(user, 'id', None),
        'action': action,
        'result': result,
        'user': {
            'id': getattr(user, 'id', None),
            'username': getattr(user, 'username', ''),
        },
        'challenge': {
            'id': getattr(challenge, 'id', None),
            'title': getattr(challenge, 'title', ''),
        },
        'container': {
            'id': container_instance_id,
            'container_id': getattr(container, 'container_id', ''),
            'name': getattr(container, 'docker_container_name', ''),
            'status': getattr(container, 'status', ''),
            'expires_at': getattr(getattr(container, 'expires_at', None), 'isoformat', lambda: None)(),
        },
        'image': image,
        'port': port,
        'network': network or '',
        'cpu_limit': cpu_limit,
        'memory_limit': memory_limit or '',
        'access_url': access_url or getattr(container, 'access_url', '') or '',
        'error_message': str(error_message or ''),
        'timestamp': timezone.now().isoformat(),
        'extra': extra or {},
    }


@transaction.atomic
def record_container_audit(
    *,
    action,
    result='success',
    user=None,
    challenge=None,
    container=None,
    image='',
    port=None,
    network='',
    cpu_limit=None,
    memory_limit='',
    access_url='',
    error_message='',
    extra=None,
    operation_id='',
    correlation_id='',
):
    """Write a container AuditEvent and hash-chain ledger entry atomically."""
    payload = build_container_audit_payload(
        action=action,
        result=result,
        user=user,
        challenge=challenge,
        container=container,
        image=image,
        port=port,
        network=network,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        access_url=access_url,
        error_message=error_message,
        extra=extra,
        operation_id=operation_id,
        correlation_id=correlation_id,
    )
    level = 'ERROR' if action in FAILURE_ACTIONS or result == 'failed' else 'INFO'
    if result == 'warning':
        level = 'WARNING'
    event = AuditEvent.log(
        category='container',
        level=level,
        user=user or getattr(container, 'user', None),
        summary=f'Container audit: {action} {result}',
        detail=payload,
    )
    ledger = AuditLedgerService.append_entry(
        event_category='container',
        object_type='challenges.ChallengeContainer',
        object_id=getattr(container, 'id', '') or payload['container']['container_id'] or '',
        actor=user or getattr(container, 'user', None),
        payload={**payload, 'audit_event_id': event.id},
    )
    return event, ledger


@transaction.atomic
def record_flag_submission_audit(*, submission, container=None):
    """Link a redacted flag submission summary into the evidence chain."""
    result = 'correct' if submission.is_correct else 'incorrect'
    payload = build_container_audit_payload(
        action='flag_submitted',
        result=result,
        user=submission.user,
        challenge=submission.challenge,
        container=container,
        image=getattr(submission.challenge, 'docker_image', '') or '',
        port=getattr(container, 'port', None),
        access_url=getattr(container, 'access_url', '') or '',
        extra={
            'submission_id': submission.id,
            'is_correct': submission.is_correct,
            'ip_recorded': bool(submission.ip_address),
        },
    )
    event = AuditEvent.log(
        category='flag_submit',
        level='INFO' if submission.is_correct else 'WARNING',
        user=submission.user,
        summary=f'Flag submission: {result}',
        detail=payload,
    )
    ledger = AuditLedgerService.append_entry(
        event_category='flag_submit',
        object_type='submissions.Submission',
        object_id=submission.id,
        actor=submission.user,
        payload={**payload, 'audit_event_id': event.id},
    )
    return event, ledger
