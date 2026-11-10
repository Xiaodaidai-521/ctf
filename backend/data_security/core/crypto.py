"""Versioned, bounded primitives. Keys, salt and nonce are always explicit."""
import hmac
import hashlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from data_security.contracts import (CipherEnvelope, ContractViolation, Environment,
    KeyPurpose, KeyReference, KeyStatus, ObjectContext, ReasonCode, canonical_bytes)
from data_security.contracts.crypto import BINARY_CIPHER_FORMAT
from data_security.contracts.schema import MAX_BYTES, MAX_CRYPTO_FRAME_BYTES, reference, require

FORMAT_VERSION = 'aes-256-gcm-hkdf-sha256.v1'


def hkdf_sha256(key, salt, info, *, length=32):
    require(type(key) is bytes and bool(key), ReasonCode.KEY_UNAVAILABLE)
    require(type(salt) is bytes and type(info) is bytes, ReasonCode.INVALID_TYPE)
    require(type(length) is int and 0 < length <= 255 * 32, ReasonCode.LIMIT_EXCEEDED)
    require(max(len(key), len(salt), len(info)) <= 65536, ReasonCode.LIMIT_EXCEEDED)
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(key)


def hmac_sha256(key, data):
    require(type(key) is bytes and bool(key), ReasonCode.KEY_UNAVAILABLE)
    require(type(data) is bytes and len(data) <= MAX_BYTES, ReasonCode.LIMIT_EXCEEDED)
    return hmac.new(key, data, hashlib.sha256).digest()


def compare_authentication(expected, supplied):
    require(type(expected) is bytes and type(supplied) is bytes, ReasonCode.INVALID_TYPE)
    return hmac.compare_digest(expected, supplied)


def _aead_inputs(key, nonce, data, aad, *, opening, max_bytes):
    require(type(key) is bytes and len(key) == 32, ReasonCode.KEY_UNAVAILABLE)
    require(type(nonce) is bytes and len(nonce) == 12, ReasonCode.CIPHERTEXT_INVALID)
    require(type(max_bytes) is int and 0 < max_bytes <= MAX_CRYPTO_FRAME_BYTES, ReasonCode.LIMIT_EXCEEDED)
    require(type(data) is bytes and (16 if opening else 0) <= len(data) <= max_bytes + (16 if opening else 0),
            ReasonCode.CIPHERTEXT_INVALID if opening else ReasonCode.LIMIT_EXCEEDED)
    require(type(aad) is bytes and len(aad) <= 65536, ReasonCode.INVALID_VALUE)


def aes_gcm_seal(key, nonce, data, aad, *, max_bytes=MAX_BYTES):
    _aead_inputs(key, nonce, data, aad, opening=False, max_bytes=max_bytes)
    return AESGCM(key).encrypt(nonce, data, aad)


def aes_gcm_open(key, nonce, data, aad, *, max_bytes=MAX_BYTES):
    _aead_inputs(key, nonce, data, aad, opening=True, max_bytes=max_bytes)
    try:
        return AESGCM(key).decrypt(nonce, data, aad)
    except InvalidTag:
        raise ContractViolation(ReasonCode.CIPHERTEXT_INVALID) from None


def _binding(context, key, format_version=FORMAT_VERSION):
    require(type(context) is ObjectContext and type(key) is KeyReference, ReasonCode.INVALID_TYPE)
    require(format_version in (FORMAT_VERSION, BINARY_CIPHER_FORMAT), ReasonCode.UNKNOWN_SCHEMA)
    # Lifecycle status and the current authorization receipt are not encryption
    # identity: a read-only key or a renewed grant must still read the same object.
    return dict(project=context.project_ref, environment=context.environment.value,
        object_uuid=context.object_uuid, object_version=context.object_version,
        field=context.field_ref, format=format_version, key_ref=key.key_ref,
        key_version=key.version, purpose=key.purpose.value)


def _data_key(root_key, salt, context, key, format_version=FORMAT_VERSION):
    require(type(root_key) is bytes and len(root_key) == 32, ReasonCode.KEY_UNAVAILABLE)
    require(key.purpose is KeyPurpose.DATA and key.status is not KeyStatus.RETIRED,
            ReasonCode.KEY_UNAVAILABLE)
    require(type(salt) is bytes and len(salt) == 16, ReasonCode.CIPHERTEXT_INVALID)
    return hkdf_sha256(root_key, salt, canonical_bytes({
        'domain': 'ds.data-key.v1', **_binding(context, key, format_version)}))


def seal(data, context, key, root_key, *, salt, nonce, format_version=FORMAT_VERSION):
    require(type(key) is KeyReference and key.status is KeyStatus.ACTIVE, ReasonCode.KEY_UNAVAILABLE)
    derived = _data_key(root_key, salt, context, key, format_version)
    maximum = MAX_CRYPTO_FRAME_BYTES if format_version == BINARY_CIPHER_FORMAT else MAX_BYTES
    ciphertext = aes_gcm_seal(derived, nonce, data,
        canonical_bytes({'domain': 'ds.aad.v1', **_binding(context, key, format_version)}), max_bytes=maximum)
    return CipherEnvelope(schema_version=CipherEnvelope.SCHEMA, format_version=format_version,
        key=key, kdf_salt=salt, nonce=nonce, ciphertext_and_tag=ciphertext)


def open_envelope(envelope, context, key, root_key):
    require(type(envelope) is CipherEnvelope and type(key) is KeyReference, ReasonCode.CIPHERTEXT_INVALID)
    require((envelope.key.key_ref, envelope.key.version, envelope.key.purpose) ==
            (key.key_ref, key.version, key.purpose), ReasonCode.CIPHERTEXT_INVALID)
    derived = _data_key(root_key, envelope.kdf_salt, context, key, envelope.format_version)
    maximum = MAX_CRYPTO_FRAME_BYTES if envelope.format_version == BINARY_CIPHER_FORMAT else MAX_BYTES
    return aes_gcm_open(derived, envelope.nonce, envelope.ciphertext_and_tag,
        canonical_bytes({'domain': 'ds.aad.v1', **_binding(context, key, envelope.format_version)}), max_bytes=maximum)


def scoped_hmac(data, root_key, key, *, environment, domain, scope):
    require(type(root_key) is bytes and len(root_key) == 32, ReasonCode.KEY_UNAVAILABLE)
    require(type(key) is KeyReference and key.status is not KeyStatus.RETIRED and
            key.purpose in (KeyPurpose.LINK, KeyPurpose.PSEUDONYM, KeyPurpose.INDEX, KeyPurpose.AUDIT),
            ReasonCode.KEY_UNAVAILABLE)
    require(type(environment) is Environment, ReasonCode.INVALID_TYPE)
    reference(domain)
    reference(scope)
    info = canonical_bytes(dict(domain='ds.stable-key.v1', environment=environment.value,
        data_domain=domain, scope=scope, purpose=key.purpose.value,
        key_ref=key.key_ref, key_version=key.version))
    derived = hkdf_sha256(root_key, b'ds.stable-salt.v1', info)
    return hmac_sha256(derived, data)
