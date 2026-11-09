from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from .enums import Environment, KeyPurpose, KeyStatus, ReasonCode
from .schema import DTO, MAX_BYTES, reference, require


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class KeyReference(DTO):
    SCHEMA: ClassVar[str] = 'ds.key-reference.v1'
    key_ref: str
    purpose: KeyPurpose
    version: str
    status: KeyStatus

    def __post_init__(self):
        DTO.__post_init__(self)
        reference(self.key_ref)
        reference(self.version, maximum=32)
        require(self.key_ref.startswith(self.purpose.value + '/'))
        require(self.key_ref.split('/')[-1] == self.version)
        require(len(self.key_ref.split('/')) == (3 if self.purpose is KeyPurpose.PROVIDER else 2))


class SecretMaterial:
    """Internal adapter material, not a wire DTO or a promise of memory erasure."""
    __slots__ = ('_value', '_purpose')

    def __init__(self, value, purpose):
        require(type(value) is bytes and 0 < len(value) <= 65536, ReasonCode.INVALID_TYPE)
        require(type(purpose) is KeyPurpose, ReasonCode.INVALID_TYPE)
        object.__setattr__(self, '_value', value)
        object.__setattr__(self, '_purpose', purpose)

    def __setattr__(self, name, value):
        raise AttributeError('IMMUTABLE_SECRET_MATERIAL')

    def __repr__(self):
        return 'SecretMaterial(<redacted>)'

    def __reduce_ex__(self, protocol):
        raise TypeError('SECRET_SERIALIZATION_FORBIDDEN')

    def __copy__(self):
        raise TypeError('SECRET_COPY_FORBIDDEN')

    def __deepcopy__(self, memo):
        raise TypeError('SECRET_COPY_FORBIDDEN')

    def borrow(self, purpose):
        require(type(purpose) is KeyPurpose and purpose is self._purpose,
                ReasonCode.AUTHORIZATION_DENIED)
        return memoryview(self._value)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ObjectContext(DTO):
    SCHEMA: ClassVar[str] = 'ds.object-context.v1'
    SERVER_ONLY: ClassVar[bool] = True
    project_ref: str
    environment: Environment
    object_uuid: str
    object_version: str
    field_ref: str
    authorization_ref: str

    def __post_init__(self):
        DTO.__post_init__(self)
        for value in (self.project_ref, self.object_version, self.field_ref, self.authorization_ref):
            reference(value)
        try:
            require(str(UUID(self.object_uuid)) == self.object_uuid)
        except ValueError:
            require(False)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CipherEnvelope(DTO):
    SCHEMA: ClassVar[str] = 'ds.cipher-envelope.v1'
    format_version: str
    key: KeyReference
    kdf_salt: bytes
    nonce: bytes
    ciphertext_and_tag: bytes

    def __post_init__(self):
        DTO.__post_init__(self)
        require(self.format_version == 'aes-256-gcm-hkdf-sha256.v1', ReasonCode.UNKNOWN_SCHEMA)
        require(self.key.purpose is KeyPurpose.DATA)
        require(len(self.kdf_salt) == 16 and len(self.nonce) == 12, ReasonCode.CIPHERTEXT_INVALID)
        require(16 <= len(self.ciphertext_and_tag) <= MAX_BYTES + 16, ReasonCode.CIPHERTEXT_INVALID)
