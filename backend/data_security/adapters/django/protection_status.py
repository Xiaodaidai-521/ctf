"""Read-only public projections. Never grant access, migrate, or expose envelopes."""
from django.db import DatabaseError

from data_security.adapters.persistence import fields
from data_security.contracts import BoundedPayload, ContractViolation, ProtectionError


def field_status(instance, name):
    """Authenticate the named stored field; a model-wide state is insufficient."""
    result = {'storage': 'unknown', 'present': None}
    if name not in getattr(instance, 'encrypted_fields', ()):
        return result
    if instance._state.adding:
        return result
    if instance.security_state == 'legacy-v0':
        return {'storage': 'legacy', 'present': bool(getattr(instance, name))}
    if name in getattr(instance, '_security_dirty', ()):
        return result
    if fields._adapter is None or instance.security_state != 'sealed-v1':
        return result
    try:
        if getattr(instance, name) not in ('', {}):
            return result
        value = fields._adapter.read(instance, name)
        return {'storage': 'encrypted' if value else 'empty', 'present': bool(value)}
    except (ContractViolation, RuntimeError, ValueError, TypeError, KeyError):
        return result


def protection_for(instance):
    return {name: field_status(instance, name) for name in getattr(instance, 'encrypted_fields', ())}


def summarize(statuses):
    """The caller supplies the complete authorized collection, never a page."""
    counts = {'encrypted': 0, 'legacy': 0, 'unknown': 0, 'empty': 0}
    for item in statuses:
        state = item.get('storage', 'unknown')
        counts[state if state in counts else 'unknown'] += 1
    total = sum(counts.values())
    if counts['unknown']:
        state = 'unknown'
    elif counts['encrypted'] and not counts['legacy']:
        state = 'encrypted'
    elif counts['encrypted'] and counts['legacy']:
        state = 'partial'
    elif counts['legacy']:
        state = 'legacy'
    else:
        state = 'empty'
    return {'storage': state, 'total': total, **counts}


def conversation_protection(conversation):
    messages = list(conversation.messages.all())
    return {name: summarize(field_status(message, name) for message in messages)
            for name in ('content', 'metadata')}


class ProtectionSerializerMixin:
    def to_representation(self, instance):
        result = super().to_representation(instance)
        result['protection'] = protection_for(instance)
        return result


def private_file_status(owner, references):
    """Verify through the existing store after the owner authenticates its metadata."""
    if owner is None or isinstance(owner, ProtectionError) or isinstance(references, ProtectionError):
        return {}
    result = {}
    for name, context, stored in references:
        result[name] = {'storage': 'unknown', 'present': True}
        try:
            if owner.read_download is not None:
                payload = owner.read_download(stored, context)
                if isinstance(payload, BoundedPayload):
                    result[name]['storage'] = 'encrypted'
        except (ContractViolation, DatabaseError, OSError, RuntimeError, ValueError, TypeError, KeyError):
            pass
    return result
