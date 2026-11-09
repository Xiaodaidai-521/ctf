"""Explicit owner-model storage adapter; no HTTP, key lookup, or implicit decryption."""
from datetime import datetime, timezone
from uuid import uuid4

from django.db import models, transaction

from data_security.contracts import (BASELINE_LIMITS, BoundedPayload, CipherEnvelope, Environment,
    FrozenJSON, MediaType, ObjectContext, PayloadKind, ProtectionError, ReasonCode)
from data_security.contracts.schema import require

_adapter = None


def bind_field_storage(adapter):
    global _adapter
    _adapter = adapter


def field_storage_enabled():
    return _adapter is not None


def protect_stored_value(value):
    return _adapter.protect_value(value) if _adapter is not None else value


class FieldStorage:
    def __init__(self, *, crypto, data_key, protect_value, index_keys=(), read_keys=(), legacy_reads=False,
                 index_deadline=None):
        require(index_deadline is None or type(index_deadline) is datetime and
                index_deadline.utcoffset() is not None, ReasonCode.INVALID_VALUE)
        require(len(index_keys) != 2 or index_deadline is not None, ReasonCode.INVALID_VALUE)
        self.crypto, self.data_key, self.protect_value = crypto, data_key, protect_value
        self.index_keys, self.legacy_reads = tuple(index_keys), legacy_reads
        self.index_deadline = index_deadline
        self.read_keys = {key.key_ref: key for key in (*read_keys, data_key)}

    def context(self, instance, name, version):
        return ObjectContext(schema_version=ObjectContext.SCHEMA, project_ref='ctf',
            environment=Environment.EVALUATION, object_uuid=str(instance.security_uuid),
            object_version='v' + str(version), field_ref=instance._meta.label_lower + '/' + name,
            authorization_ref='authorization/phase4-storage')

    def seal(self, instance, name, value, revision):
        json_field = isinstance(instance._meta.get_field(name), models.JSONField)
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA,
            kind=PayloadKind.JSON if json_field else PayloadKind.TEXT,
            media_type=MediaType.JSON if json_field else MediaType.TEXT,
            text=None if json_field else value, tree=FrozenJSON(value) if json_field else None,
            binary=None, limits=BASELINE_LIMITS)
        result = self.crypto.seal(payload, self.context(instance, name, revision), self.data_key)
        if type(result) is ProtectionError:
            raise RuntimeError(result.code.value)
        return {'revision': revision, 'envelope': result.to_wire()}

    def read(self, instance, name):
        require(name in instance.encrypted_fields, ReasonCode.AUTHORIZATION_DENIED)
        if instance.security_state == 'legacy-v0':
            require(self.legacy_reads, ReasonCode.UNSUPPORTED_FORMAT)
            return getattr(instance, name)
        require(instance.security_state == 'sealed-v1', ReasonCode.CIPHERTEXT_INVALID)
        entry = instance.security_envelopes.get(name)
        require(type(entry) is dict and set(entry) == {'revision', 'envelope'} and
                type(entry['revision']) is int and 0 < entry['revision'] <= instance.security_revision,
                ReasonCode.CIPHERTEXT_INVALID)
        envelope = CipherEnvelope.from_wire(entry['envelope'])
        key = self.read_keys.get(envelope.key.key_ref)
        require(key is not None, ReasonCode.KEY_UNAVAILABLE)
        result = self.crypto.open(envelope, self.context(instance, name, entry['revision']), key)
        if type(result) is ProtectionError:
            raise RuntimeError(result.code.value)
        return result.tree.to_value() if result.kind is PayloadKind.JSON else result.text

    def email_indexes(self, instance, normalized):
        require(len(self.index_keys) != 2 or datetime.now(timezone.utc) < self.index_deadline,
                ReasonCode.KEY_UNAVAILABLE)
        if not normalized:
            return ('', '')
        require(0 < len(self.index_keys) <= 2, ReasonCode.KEY_UNAVAILABLE)
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
            media_type=MediaType.TEXT, text=normalized, tree=None, binary=None, limits=BASELINE_LIMITS)
        results = []
        for key in self.index_keys:
            result = self.crypto.blind_index(payload, self.context(instance, 'email', 1), key)
            if type(result) is ProtectionError:
                raise RuntimeError(result.code.value)
            results.append(key.version + ':' + result.hex())
        return (results[0], results[1] if len(results) == 2 else '')


def normalize_email(value):
    value = value.strip()
    if not value:
        return ''
    local, separator, domain = value.rpartition('@')
    require(bool(separator and local and domain) and not any(character.isspace() for character in value),
            ReasonCode.INVALID_VALUE)
    return local + '@' + domain.lower()


class ProtectedQuerySet(models.QuerySet):
    def exact_email(self, value):
        require(_adapter is not None and 'email' in self.model.encrypted_fields,
                ReasonCode.KEY_UNAVAILABLE)
        normalized = normalize_email(value)
        if not normalized:
            return self.none()
        indexes = [item for item in _adapter.email_indexes(self.model(), normalized) if item]
        candidates = self.filter(models.Q(email_index__in=indexes) |
                                 models.Q(email_index_previous__in=indexes))
        matched = [item.pk for item in candidates if _adapter.read(item, 'email') == normalized]
        return self.filter(pk__in=matched)

    def update(self, **kwargs):
        # Migration-state models use this manager too, but have no live field adapter.
        if _adapter is not None and hasattr(self.model, 'encrypted_fields'):
            protected = set(self.model.encrypted_fields) | set(self.model.redacted_fields) | set(self.model.minimized_fields)
            if protected.intersection(kwargs) or any(name.startswith('security_') for name in kwargs):
                raise RuntimeError('FIELD_UPDATE_REQUIRES_OBJECT_SAVE')
        return super().update(**kwargs)

    def bulk_create(self, objs, **kwargs):
        if _adapter is not None:
            raise RuntimeError('FIELD_BULK_CREATE_REQUIRES_OBJECT_SAVE')
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if _adapter is not None and set(fields).intersection((
                *self.model.encrypted_fields, *self.model.redacted_fields, *self.model.minimized_fields)):
            raise RuntimeError('FIELD_BULK_UPDATE_REQUIRES_OBJECT_SAVE')
        return super().bulk_update(objs, fields, **kwargs)


class ProtectedModel(models.Model):
    security_uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    security_revision = models.PositiveBigIntegerField(default=0, editable=False)
    security_state = models.CharField(max_length=16, default='legacy-v0', editable=False)
    security_envelopes = models.JSONField(default=dict, editable=False)
    encrypted_fields = ()
    redacted_fields = ()
    minimized_fields = {}
    objects = ProtectedQuerySet.as_manager()

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._security_dirty = set(kwargs).intersection(self.encrypted_fields)

    def __setattr__(self, name, value):
        if name in self.encrypted_fields and '_security_dirty' in self.__dict__:
            self._security_dirty.add(name)
        super().__setattr__(name, value)

    def refresh_from_db(self, using=None, fields=None, **kwargs):
        super().refresh_from_db(using=using, fields=fields, **kwargs)
        self._security_dirty.difference_update(self.encrypted_fields if fields is None else fields)

    def read_protected(self, name):
        require(name in self.encrypted_fields, ReasonCode.AUTHORIZATION_DENIED)
        if _adapter is None:
            require(self.security_state == 'legacy-v0', ReasonCode.KEY_UNAVAILABLE)
            return getattr(self, name)
        return _adapter.read(self, name)

    def display_protected(self, name):
        value = self.read_protected(name)
        return _adapter.protect_value(value) if _adapter is not None else value

    def save(self, *args, **kwargs):
        legacy_migration = kwargs.pop('_legacy_migration', False)
        if _adapter is None:
            require(self.security_state == 'legacy-v0', ReasonCode.KEY_UNAVAILABLE)
            return super().save(*args, **kwargs)
        # Existing plaintext is changed only by the backup-gated maintenance entry.
        require(self._state.adding or self.security_state != 'legacy-v0' or legacy_migration,
                ReasonCode.SOURCE_NOT_APPROVED)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and not update_fields:
            return
        with transaction.atomic(using=kwargs.get('using') or self._state.db):
            if not self._state.adding:
                current = type(self)._base_manager.select_for_update().values_list('security_revision', flat=True).get(pk=self.pk)
                require(current == self.security_revision, ReasonCode.IDEMPOTENCY_CONFLICT)
            revision = self.security_revision + 1
            migrating = self._state.adding or self.security_state == 'legacy-v0'
            selected = set(self.encrypted_fields) if migrating else self._security_dirty.copy()
            if update_fields is not None and not migrating:
                selected &= set(update_fields)
            envelopes = dict(self.security_envelopes)
            changed = set()
            for name in self.encrypted_fields:
                if name not in selected:
                    continue
                value = getattr(self, name)
                if name == 'email' and hasattr(self, 'email_index'):
                    value = normalize_email(value)
                    self.email_index, self.email_index_previous = _adapter.email_indexes(self, value)
                    changed.update(('email_index', 'email_index_previous'))
                envelopes[name] = _adapter.seal(self, name, value, revision)
                setattr(self, name, {} if isinstance(self._meta.get_field(name), models.JSONField) else '')
                changed.add(name)
            for name in self.redacted_fields:
                if update_fields is None or migrating or name in update_fields:
                    setattr(self, name, _adapter.protect_value(getattr(self, name)))
                    changed.add(name)
            for name, value in self.minimized_fields.items():
                setattr(self, name, value)
                changed.add(name)
            self.security_envelopes = envelopes
            self.security_revision, self.security_state = revision, 'sealed-v1'
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | changed | {
                    'security_envelopes', 'security_revision', 'security_state'}
            result = super().save(*args, **kwargs)
            self._security_dirty.clear()
            return result
