"""Minimal CryptoPort. No storage, historical format guessing, or public reveal."""
from dataclasses import replace

from data_security.contracts import (BoundedPayload, ContractViolation, Environment,
    KeyPurpose, KeyReference, KeyResolverPort, KeyStatus, Limits, ObjectContext, PayloadKind,
    ProtectionError, ReasonCode, SecretMaterial)
from data_security.contracts.crypto import BINARY_CIPHER_FORMAT
from data_security.contracts.schema import MAX_BYTES, canonical_bytes, reference, require
from data_security.core import crypto


class CryptoService:
    def __init__(self, *, keys: KeyResolverPort, service_identity: str, random_bytes,
                 environment: Environment, limits: Limits, retained_data_keys=()):
        reference(service_identity)
        require(type(environment) is Environment and environment is not Environment.PRODUCTION,
                ReasonCode.AUTHORIZATION_DENIED)
        require(type(limits) is Limits and callable(random_bytes), ReasonCode.INVALID_TYPE)
        self.keys, self.service_identity, self.random_bytes = keys, service_identity, random_bytes
        self.environment, self.limits = environment, limits
        require(type(retained_data_keys) is tuple and len(retained_data_keys) <= 64
                and all(type(key) is KeyReference and key.purpose is KeyPurpose.DATA
                        and key.status is KeyStatus.READ_ONLY for key in retained_data_keys)
                and len({key.key_ref for key in retained_data_keys}) == len(retained_data_keys),
                ReasonCode.KEY_UNAVAILABLE)
        self.retained_data_keys = {key.key_ref: key for key in retained_data_keys}

    def _material(self, key, context, purpose, *, writing):
        require(type(context) is ObjectContext and context.environment is self.environment,
                ReasonCode.AUTHORIZATION_DENIED)
        require(type(key) is KeyReference and key.purpose is purpose and key.status is not KeyStatus.RETIRED and
                (not writing or key.status is KeyStatus.ACTIVE), ReasonCode.KEY_UNAVAILABLE)
        material = self.keys.resolve(key, purpose, self.service_identity)
        if type(material) is ProtectionError:
            raise ContractViolation(material.code)
        require(type(material) is SecretMaterial, ReasonCode.KEY_UNAVAILABLE)
        root = bytes(material.borrow(purpose))
        require(len(root) == 32, ReasonCode.KEY_UNAVAILABLE)
        return root

    def _error(self, code):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='crypto/service')

    def _encode(self, data):
        require(type(data) is BoundedPayload, ReasonCode.INVALID_TYPE)
        # Revalidate to the stricter service boundary, preserving the embedded
        # limits on successful decoding. Framing keeps empty/null/types distinct.
        replace(data, limits=self.limits)
        encoded = canonical_bytes(data, include_payload=True)
        require(len(encoded) <= min(MAX_BYTES, self.limits.max_bytes), ReasonCode.LIMIT_EXCEEDED)
        return encoded

    def seal(self, data, object_context, key_ref):
        try:
            format_version = crypto.FORMAT_VERSION
            if type(data) is BoundedPayload and data.kind is PayloadKind.BINARY:
                replace(data, limits=self.limits)
                # One AEAD message, not chunked encryption. Only the raw file
                # consumes max_bytes; the typed header has its own 4 KiB bound.
                header = canonical_bytes(replace(data, binary=b''), include_payload=True)
                require(len(header) + 4 <= 4096, ReasonCode.LIMIT_EXCEEDED)
                encoded = len(header).to_bytes(4, 'big') + header + data.binary
                format_version = BINARY_CIPHER_FORMAT
            else:
                encoded = self._encode(data)
            root = self._material(key_ref, object_context, KeyPurpose.DATA, writing=True)
            salt, nonce = self.random_bytes(16), self.random_bytes(12)
            return crypto.seal(encoded, object_context, key_ref, root, salt=salt, nonce=nonce,
                               format_version=format_version)
        except ContractViolation as exc:
            return self._error(exc.code)
        except Exception:
            return self._error(ReasonCode.KEY_UNAVAILABLE)

    def open(self, envelope, object_context, key_ref):
        try:
            # The envelope's signed identity stays unchanged. Only an explicitly
            # retained reference can select the current read-only manifest entry.
            retained = self.retained_data_keys.get(key_ref.key_ref) if type(key_ref) is KeyReference else None
            if retained is not None:
                require(key_ref.status is not KeyStatus.RETIRED and key_ref.purpose is retained.purpose
                        and key_ref.version == retained.version, ReasonCode.KEY_UNAVAILABLE)
                key_ref = retained
            root = self._material(key_ref, object_context, KeyPurpose.DATA, writing=False)
            data = crypto.open_envelope(envelope, object_context, key_ref, root)
            if envelope.format_version == BINARY_CIPHER_FORMAT:
                header_size = int.from_bytes(data[:4], 'big')
                require(0 < header_size <= 4092 and 4 + header_size <= len(data),
                        ReasonCode.CIPHERTEXT_INVALID)
                header = BoundedPayload.from_json(data[4:4 + header_size])
                require(header.kind is PayloadKind.BINARY and header.binary == b'', ReasonCode.CIPHERTEXT_INVALID)
                payload = replace(header, binary=data[4 + header_size:])
                replace(payload, limits=self.limits)
            else:
                require(len(data) <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
                payload = BoundedPayload.from_json(data)
                self._encode(payload)
            return payload
        except ContractViolation as exc:
            return self._error(exc.code)
        except Exception:
            return self._error(ReasonCode.CIPHERTEXT_INVALID)

    def blind_index(self, data, object_context, key_ref):
        try:
            root = self._material(key_ref, object_context, KeyPurpose.INDEX, writing=True)
            self._encode(data)  # Limits validate input; they are not value identity.
            identity = data.to_wire(include_payload=True)
            del identity['limits']
            encoded = canonical_bytes({'version': 'typed-value.v1', 'payload': identity})
            return crypto.scoped_hmac(encoded, root, key_ref,
                environment=object_context.environment, domain=object_context.project_ref, scope=object_context.field_ref)
        except ContractViolation as exc:
            return self._error(exc.code)
        except Exception:
            return self._error(ReasonCode.KEY_UNAVAILABLE)

    def verify_authentication(self, metadata, authentication, object_context, key_ref):
        """Verify with active or retained read-only material, without exposing a MAC."""
        try:
            require(type(metadata) is bytes and len(metadata) <= self.limits.max_bytes,
                    ReasonCode.LIMIT_EXCEEDED)
            require(type(authentication) is bytes and len(authentication) == 32,
                    ReasonCode.INVALID_VALUE)
            root = self._material(key_ref, object_context, KeyPurpose.AUDIT, writing=False)
            expected = crypto.scoped_hmac(metadata, root, key_ref, environment=object_context.environment,
                                          domain=object_context.project_ref, scope=object_context.field_ref)
            return crypto.compare_authentication(expected, authentication)
        except ContractViolation as exc:
            return self._error(exc.code)
        except Exception:
            return self._error(ReasonCode.KEY_UNAVAILABLE)

    def authenticate(self, metadata, object_context, key_ref):
        """Internal MAC without an audit callback, avoiding audit recursion."""
        try:
            root = self._material(key_ref, object_context, KeyPurpose.AUDIT, writing=True)
            require(type(metadata) is bytes and len(metadata) <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
            return crypto.scoped_hmac(metadata, root, key_ref, environment=object_context.environment,
                domain=object_context.project_ref, scope=object_context.field_ref)
        except ContractViolation as exc:
            return self._error(exc.code)
        except Exception:
            return self._error(ReasonCode.KEY_UNAVAILABLE)
