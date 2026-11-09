"""Closed, immutable wire types. Canonicalization is ds-json-v1, not RFC 8785."""
import base64
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
import hashlib
import json
import math
import re
from types import UnionType
from typing import ClassVar, Union, get_args, get_origin

from .enums import ReasonCode

MAX_BYTES = 20 * 1024 * 1024
MAX_WIRE_BYTES = 32 * 1024 * 1024
MAX_ITEMS = 100_000
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 10_000
MAX_JSON_FIELDS = 2_048
MAX_TEXT_CHARS = 65_536
MAX_JSON_BYTES = 1024 * 1024


class ContractViolation(ValueError):
    def __init__(self, code: ReasonCode):
        self.code = code
        super().__init__(code.value)


def require(condition, code=ReasonCode.INVALID_VALUE):
    if not condition:
        raise ContractViolation(code)


def reference(value, *, maximum=160):
    require(type(value) is str and 0 < len(value) <= maximum)
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]*', value) is not None)
    require('..' not in value and '//' not in value)


def digest(value):
    require(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None)


def utc(value):
    require(type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None)
    require(value.utcoffset().total_seconds() == 0)


def count(value, maximum=MAX_ITEMS):
    require(type(value) is int and 0 <= value <= maximum)


def _string(value):
    try:
        require(len(value.encode('utf-8')) <= MAX_WIRE_BYTES, ReasonCode.LIMIT_EXCEEDED)
    except UnicodeError:
        raise ContractViolation(ReasonCode.INVALID_VALUE) from None


class _Object(tuple):
    pass


class FrozenJSON:
    """Immutable closed JSON. Construction copies and bounds all descendant values."""
    __slots__ = ('_value', '_bytes')

    def __init__(self, value, *, max_depth=MAX_JSON_DEPTH, max_nodes=MAX_JSON_NODES,
                 max_fields=MAX_JSON_FIELDS, max_text_chars=MAX_TEXT_CHARS,
                 max_bytes=MAX_JSON_BYTES):
        for chosen, cap in ((max_depth, MAX_JSON_DEPTH), (max_nodes, MAX_JSON_NODES),
                            (max_fields, MAX_JSON_FIELDS), (max_text_chars, MAX_TEXT_CHARS),
                            (max_bytes, MAX_JSON_BYTES)):
            require(type(chosen) is int and 0 < chosen <= cap, ReasonCode.LIMIT_EXCEEDED)
        nodes = 0
        field_count = 0

        def freeze(item, depth):
            nonlocal nodes, field_count
            nodes += 1
            require(depth <= max_depth and nodes <= max_nodes, ReasonCode.LIMIT_EXCEEDED)
            if item is None or type(item) is bool:
                return item
            if type(item) is int:
                require(abs(item) <= 2**53 - 1)
                return item
            if type(item) is float:
                require(math.isfinite(item))
                return item
            if type(item) is str:
                _string(item)
                require(len(item) <= max_text_chars, ReasonCode.LIMIT_EXCEEDED)
                return item
            if type(item) is list:
                require(len(item) <= max_nodes, ReasonCode.LIMIT_EXCEEDED)
                return tuple(freeze(child, depth + 1) for child in item)
            if type(item) is dict:
                field_count += len(item)
                require(field_count <= max_fields, ReasonCode.LIMIT_EXCEEDED)
                for key in item:
                    require(type(key) is str and len(key) <= 256)
                    _string(key)
                return _Object((key, freeze(item[key], depth + 1)) for key in sorted(item))
            raise ContractViolation(ReasonCode.INVALID_TYPE)

        value = freeze(value, 0)
        encoded = _encode(_thaw(value))
        require(len(encoded) <= max_bytes, ReasonCode.LIMIT_EXCEEDED)
        object.__setattr__(self, '_value', value)
        object.__setattr__(self, '_bytes', encoded)

    def __setattr__(self, name, value):
        raise AttributeError('IMMUTABLE_JSON')

    def __repr__(self):
        return 'FrozenJSON(<redacted>)'

    def __eq__(self, other):
        return type(other) is FrozenJSON and self._bytes == other._bytes

    def __hash__(self):
        return hash(self._bytes)

    def __deepcopy__(self, memo):
        return self

    def to_value(self):
        return _thaw(self._value)


def _thaw(value):
    if type(value) is _Object:
        return {key: _thaw(item) for key, item in value}
    if type(value) is tuple:
        return [_thaw(item) for item in value]
    return value


def _encode(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                          allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ContractViolation(ReasonCode.INVALID_VALUE) from None


def primitive(value, *, include_payload=False):
    if isinstance(value, DTO):
        require(include_payload or not value.SENSITIVE, ReasonCode.SENSITIVE_SERIALIZATION_FORBIDDEN)
        return {field.name: primitive(getattr(value, field.name), include_payload=include_payload)
                for field in fields(value)}
    if type(value) is FrozenJSON:
        require(include_payload, ReasonCode.SENSITIVE_SERIALIZATION_FORBIDDEN)
        # The box distinguishes a JSON null root from an absent optional tree.
        return {'value': value.to_value()}
    if isinstance(value, Enum):
        return value.value
    if type(value) is datetime:
        utc(value)
        return value.isoformat(timespec='microseconds').replace('+00:00', 'Z')
    if type(value) is bytes:
        return base64.b64encode(value).decode('ascii')
    if type(value) is tuple:
        return [primitive(item, include_payload=include_payload) for item in value]
    if type(value) is dict:
        require(all(type(key) is str for key in value))
        return {key: primitive(item, include_payload=include_payload) for key, item in value.items()}
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float:
        require(math.isfinite(value))
        return value
    raise ContractViolation(ReasonCode.INVALID_TYPE)


def canonical_bytes(value, *, include_payload=False):
    return _encode(primitive(value, include_payload=include_payload))


def content_hash(value):
    """Metadata digest. Low-entropy original values must not become public evidence."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@lru_cache(maxsize=128)
def _annotations(cls):
    # All contract modules use evaluated source annotations, never forward strings.
    result = {}
    for base in reversed(cls.__mro__):
        result.update(base.__dict__.get('__annotations__', {}))
    require(all(type(value) is not str for value in result.values()), ReasonCode.INVALID_TYPE)
    return result


def _check(annotation, value):
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        for choice in get_args(annotation):
            try:
                _check(choice, value)
                return
            except ContractViolation:
                pass
        raise ContractViolation(ReasonCode.INVALID_TYPE)
    if origin is tuple:
        require(type(value) is tuple, ReasonCode.INVALID_TYPE)
        require(len(value) <= MAX_ITEMS, ReasonCode.LIMIT_EXCEEDED)
        item_types = get_args(annotation)
        if len(item_types) == 2 and item_types[1] is Ellipsis:
            for item in value:
                _check(item_types[0], item)
        else:
            require(len(value) == len(item_types), ReasonCode.INVALID_TYPE)
            for expected, item in zip(item_types, value):
                _check(expected, item)
        return
    require(type(value) is annotation, ReasonCode.INVALID_TYPE)
    if annotation is str:
        _string(value)
    elif annotation is bytes:
        require(len(value) <= MAX_BYTES + 16, ReasonCode.LIMIT_EXCEEDED)
    elif annotation is datetime:
        utc(value)
    elif annotation is float:
        require(math.isfinite(value))


def _decode(annotation, value):
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        if value is None and type(None) in get_args(annotation):
            return None
        for choice in get_args(annotation):
            try:
                return _decode(choice, value)
            except ContractViolation:
                pass
        raise ContractViolation(ReasonCode.INVALID_TYPE)
    if origin is tuple:
        require(type(value) is list, ReasonCode.INVALID_TYPE)
        require(len(value) <= MAX_ITEMS, ReasonCode.LIMIT_EXCEEDED)
        types = get_args(annotation)
        if len(types) == 2 and types[1] is Ellipsis:
            return tuple(_decode(types[0], item) for item in value)
        require(len(value) == len(types), ReasonCode.INVALID_TYPE)
        return tuple(_decode(expected, item) for expected, item in zip(types, value))
    if isinstance(annotation, type) and issubclass(annotation, DTO):
        return annotation.from_wire(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        require(type(value) is str, ReasonCode.INVALID_TYPE)
        try:
            return annotation(value)
        except ValueError:
            raise ContractViolation(ReasonCode.INVALID_VALUE) from None
    if annotation is FrozenJSON:
        require(type(value) is dict and set(value) == {'value'}, ReasonCode.INVALID_TYPE)
        return FrozenJSON(value['value'])
    if annotation is bytes:
        require(type(value) is str and len(value) <= MAX_WIRE_BYTES, ReasonCode.INVALID_TYPE)
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, UnicodeError):
            raise ContractViolation(ReasonCode.INVALID_VALUE) from None
        require(base64.b64encode(decoded).decode('ascii') == value)
        _check(bytes, decoded)
        return decoded
    if annotation is datetime:
        require(type(value) is str and re.fullmatch(
            r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z', value) is not None)
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            raise ContractViolation(ReasonCode.INVALID_VALUE) from None
        utc(parsed)
        return parsed
    _check(annotation, value)
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, ReasonCode.DUPLICATE_FIELD)
        result[key] = value
    return result


def _reject_constant(value):
    raise ContractViolation(ReasonCode.INVALID_VALUE)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DTO:
    schema_version: str
    SCHEMA: ClassVar[str] = 'ds.abstract.v1'
    SENSITIVE: ClassVar[bool] = False
    SERVER_ONLY: ClassVar[bool] = False

    def __post_init__(self):
        require(self.schema_version == self.SCHEMA, ReasonCode.UNKNOWN_SCHEMA)
        annotations = _annotations(type(self))
        for field in fields(self):
            _check(annotations[field.name], getattr(self, field.name))

    def __repr__(self):
        return f'{type(self).__name__}(<redacted>)'

    def to_wire(self, *, include_payload=False):
        return primitive(self, include_payload=include_payload)

    @classmethod
    def from_wire(cls, data):
        require(not cls.SERVER_ONLY, ReasonCode.TRUSTED_CONSTRUCTION_REQUIRED)
        require(type(data) is dict, ReasonCode.INVALID_TYPE)
        expected = {field.name for field in fields(cls)}
        require(not data.keys() - expected, ReasonCode.UNKNOWN_FIELD)
        require(not expected - data.keys(), ReasonCode.MISSING_FIELD)
        require(data['schema_version'] == cls.SCHEMA, ReasonCode.UNKNOWN_SCHEMA)
        annotations = _annotations(cls)
        return cls(**{key: _decode(annotations[key], value) for key, value in data.items()})

    @classmethod
    def from_json(cls, data):
        require(type(data) is bytes, ReasonCode.INVALID_TYPE)
        require(len(data) <= MAX_WIRE_BYTES, ReasonCode.LIMIT_EXCEEDED)
        try:
            value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_reject_constant)
        except (ValueError, UnicodeError, RecursionError) as error:
            if isinstance(error, ContractViolation):
                raise
            raise ContractViolation(ReasonCode.INVALID_VALUE) from None
        return cls.from_wire(value)
