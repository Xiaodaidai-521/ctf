"""Rekey owner fields in place; authenticated row state is the restart cursor."""
from django.db import DatabaseError, connection, transaction

from data_security.adapters.persistence import fields
from data_security.adapters.persistence.fields import ProtectedModel
from data_security.contracts import ContractViolation, ReasonCode
from data_security.contracts.schema import require


class FieldRotation:
    def __init__(self, *, models, storage):
        require(connection.vendor == 'postgresql' and storage is not None and fields._adapter is storage,
                ReasonCode.AUTHORIZATION_DENIED)
        self.models = tuple(model for model in models if model.encrypted_fields)
        self.storage = storage

    def run(self, *, limit=100):
        require(type(limit) is int and 1 <= limit <= 1000, ReasonCode.INVALID_VALUE)
        rotated, scanned = 0, 0
        for model in self.models:
            for pk, revision in model.objects.order_by('pk').values_list('pk', 'security_revision').iterator():
                if rotated == limit:
                    return {'scanned': scanned, 'rotated': rotated, 'stopped': False, 'has_more': True, 'failures': []}
                scanned += 1
                try:
                    with transaction.atomic():
                        obj = model.objects.select_for_update().get(pk=pk)
                        require(obj.security_state == 'sealed-v1' and obj.security_revision == revision,
                                ReasonCode.IDEMPOTENCY_CONFLICT)
                        changed = []
                        for name in model.encrypted_fields:
                            value = self.storage.read(obj, name)
                            key = obj.security_envelopes[name]['envelope']['key']
                            needs_key = (key['key_ref'], key['version']) != (
                                self.storage.data_key.key_ref, self.storage.data_key.version)
                            needs_index = name == 'email' and (
                                obj.email_index, obj.email_index_previous) != self.storage.email_indexes(obj, value)
                            if needs_key or needs_index:
                                setattr(obj, name, value)
                                changed.append(name)
                        if changed:
                            # Storage maintenance must not replay owner judging/score side effects.
                            ProtectedModel.save(obj, update_fields=changed)
                    if changed:
                        rotated += 1
                except (ContractViolation, RuntimeError, DatabaseError, model.DoesNotExist):
                    return {'scanned': scanned, 'rotated': rotated, 'stopped': True, 'has_more': True,
                            'failures': [{'model': model._meta.label_lower, 'pk': pk,
                                          'reason': 'FIELD_ROTATION_FAILED'}]}
        return {'scanned': scanned, 'rotated': rotated, 'stopped': False, 'has_more': False, 'failures': []}

    def finish(self):
        require(not self.storage.legacy_reads and len(self.storage.index_keys) == 1 and
                set(self.storage.read_keys) == {self.storage.data_key.key_ref}, ReasonCode.SOURCE_NOT_APPROVED)
        verified = 0
        with transaction.atomic():
            for model in self.models:
                for obj in model.objects.select_for_update().order_by('pk').iterator():
                    require(obj.security_state == 'sealed-v1', ReasonCode.SOURCE_NOT_APPROVED)
                    for name in model.encrypted_fields:
                        value = self.storage.read(obj, name)
                        key = obj.security_envelopes[name]['envelope']['key']
                        require((key['key_ref'], key['version']) == (
                            self.storage.data_key.key_ref, self.storage.data_key.version), ReasonCode.REPORT_MISMATCH)
                        require(getattr(obj, name) in ('', {}), ReasonCode.REPORT_MISMATCH)
                        if name == 'email':
                            require((obj.email_index, obj.email_index_previous) == self.storage.email_indexes(obj, value),
                                    ReasonCode.REPORT_MISMATCH)
                    verified += 1
        return {'verified_rows': verified, 'data_key': self.storage.data_key.key_ref,
                'index_key': self.storage.index_keys[0].key_ref, 'old_read_refs': 0, 'old_indexes': 0}
