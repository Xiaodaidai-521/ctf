"""Explicit field-crypto boundary; historical Fernet migration is not enabled.

No environment or framework signing key is read here. B must inject CryptoPort,
an independent data key reference and limits; callers supply trusted object
context. Existing Fernet values remain untouched until an approved migration.
"""
from data_security.contracts import (
    BoundedPayload, CipherEnvelope, ContractViolation, CryptoPort, KeyPurpose,
    KeyReference, Limits, MediaType, ObjectContext, PayloadKind, ProtectionError,
)
from data_security.contracts.schema import canonical_bytes


class EncryptionError(Exception):
    """Fixed, non-sensitive failure code; never contains plaintext or key material."""


_binding: tuple[CryptoPort, KeyReference, Limits] | None = None
_FORMAT = 'ds-field.v1:'


def bind_field_crypto(crypto: CryptoPort | None, *, key_ref: KeyReference | None = None,
                      limits: Limits | None = None):
    """Called only by explicit composition; None closes the unused legacy facade."""
    global _binding
    if crypto is None:
        _binding = None
        return
    if not isinstance(key_ref, KeyReference) or key_ref.purpose is not KeyPurpose.DATA:
        raise EncryptionError('FIELD_DATA_KEY_REQUIRED')
    if not isinstance(limits, Limits):
        raise EncryptionError('FIELD_LIMITS_REQUIRED')
    _binding = (crypto, key_ref, limits)


def encrypt_field(plaintext: str, *, object_context: ObjectContext | None = None) -> str:
    if _binding is None:
        raise EncryptionError('FIELD_CRYPTO_NOT_BOUND')
    if object_context is None:
        raise EncryptionError('FIELD_OBJECT_CONTEXT_REQUIRED')
    crypto, key_ref, limits = _binding
    try:
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA,
            kind=PayloadKind.TEXT, media_type=MediaType.TEXT, text=plaintext,
            tree=None, binary=None, limits=limits)
    except ContractViolation as error:
        raise EncryptionError(error.code.value) from None
    envelope = crypto.seal(payload, object_context, key_ref)
    if isinstance(envelope, ProtectionError):
        raise EncryptionError(envelope.code.value)
    return _FORMAT + canonical_bytes(envelope).decode('utf-8')


def decrypt_field(ciphertext: str, *, object_context: ObjectContext | None = None) -> str:
    if _binding is None:
        raise EncryptionError('FIELD_CRYPTO_NOT_BOUND')
    if object_context is None:
        raise EncryptionError('FIELD_OBJECT_CONTEXT_REQUIRED')
    if not ciphertext.startswith(_FORMAT):
        raise EncryptionError('FIELD_FORMAT_MIGRATION_REQUIRED')
    crypto, key_ref, _ = _binding
    try:
        envelope = CipherEnvelope.from_json(ciphertext[len(_FORMAT):].encode('utf-8'))
    except (ContractViolation, UnicodeError):
        raise EncryptionError('FIELD_CIPHERTEXT_INVALID') from None
    payload = crypto.open(envelope, object_context, key_ref)
    if isinstance(payload, ProtectionError):
        raise EncryptionError(payload.code.value)
    if payload.kind is not PayloadKind.TEXT:
        raise EncryptionError('FIELD_PAYLOAD_TYPE_INVALID')
    return payload.text
