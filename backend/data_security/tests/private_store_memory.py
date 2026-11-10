"""Single-threaded ciphertext store for port tests, not a durable filesystem."""
from dataclasses import replace
import hashlib
import re

from data_security.contracts import (
    CipherEnvelope, ContractViolation, Environment, ProtectionError, ReasonCode, StoredObject, content_hash,
)
from data_security.contracts.schema import MAX_WIRE_BYTES, canonical_bytes, require


class MemoryPrivateStore:
    def __init__(self, *, records, blobs, crypto, environment):
        require(type(environment) is Environment and environment is not Environment.PRODUCTION,
                ReasonCode.SOURCE_NOT_APPROVED)
        self.records, self.blobs = records, blobs
        self.crypto, self.environment = crypto, environment

    def write_candidate(self, envelope, context):
        return self._run('write', context, envelope=envelope)

    def verify(self, candidate, context):
        return self._run('verify', context, stored=candidate)

    def publish(self, candidate, context):
        return self._run('publish', context, stored=candidate)

    def read(self, stored, context):
        return self._run('read', context, stored=stored)

    def _read_blob(self, stored):
        encoded = self.blobs[stored.object_ref]
        require(len(encoded) == stored.size_bytes and len(encoded) <= MAX_WIRE_BYTES,
                ReasonCode.CIPHERTEXT_INVALID)
        require(hashlib.sha256(encoded).hexdigest() == stored.ciphertext_hash, ReasonCode.HASH_MISMATCH)
        return CipherEnvelope.from_json(encoded)

    def _run(self, operation, context, *, envelope=None, stored=None):
        try:
            require(context.environment is self.environment, ReasonCode.SOURCE_NOT_APPROVED)
            identity = content_hash(dict(project=context.project_ref, environment=context.environment,
                object_uuid=context.object_uuid, version=context.object_version, field=context.field_ref))
            if operation == 'write':
                require(type(envelope) is CipherEnvelope, ReasonCode.INVALID_TYPE)
                encoded = canonical_bytes(envelope)
                require(len(encoded) <= MAX_WIRE_BYTES, ReasonCode.LIMIT_EXCEEDED)
                digest = hashlib.sha256(encoded).hexdigest()
                ref = 'private/' + content_hash({'context': identity, 'ciphertext': digest})
                candidate = StoredObject(schema_version=StoredObject.SCHEMA, object_ref=ref,
                    version=context.object_version, ciphertext_hash=digest, size_bytes=len(encoded), state='candidate')
                if ref in self.blobs:
                    self._read_blob(candidate)
                else:
                    self.blobs[ref] = encoded
                self.records.setdefault(ref, (identity, candidate))
                return self.records[ref][1]
            require(type(stored) is StoredObject and
                    re.fullmatch(r'private/[0-9a-f]{64}', stored.object_ref) is not None,
                    ReasonCode.AUTHORIZATION_DENIED)
            require(stored.object_ref in self.records, ReasonCode.AUTHORIZATION_DENIED)
            bound, current = self.records[stored.object_ref]
            require((bound, current.version, current.ciphertext_hash, current.size_bytes) ==
                    (identity, stored.version, stored.ciphertext_hash, stored.size_bytes), ReasonCode.HASH_MISMATCH)
            if operation == 'publish':
                require(current.state in ('verified', 'published'), ReasonCode.AUTHORIZATION_DENIED)
                published = replace(current, state='published')
                self.records[stored.object_ref] = (bound, published)
                return published
            if operation == 'read':
                require(current.state == 'published', ReasonCode.AUTHORIZATION_DENIED)
            envelope = self._read_blob(current)
            if operation == 'read':
                return envelope
            opened = self.crypto.open(envelope, context, envelope.key)
            if isinstance(opened, ProtectionError):
                return opened
            if current.state == 'candidate':
                current = replace(current, state='verified')
                self.records[stored.object_ref] = (bound, current)
            return current
        except ContractViolation as error:
            code = error.code
        except KeyError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='private-store/operation')
