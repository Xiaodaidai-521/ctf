"""Recursive immutability helpers (review R7).

`@dataclass(frozen=True)` only blocks attribute rebinding; it does **not** stop
mutation of a nested dict/list still aliased by the caller. The judgment core and
replay depend on snapshots being value-stable after construction, so snapshot
dataclasses normalise their nested fields through `deep_freeze` in __post_init__.
"""

from types import MappingProxyType
from typing import Any, Mapping


def deep_freeze(value: Any) -> Any:
    """Return a read-only, structurally-copied view of ``value``.

    Mappings become ``MappingProxyType`` over frozen items, sequences become
    tuples, sets become frozensets. Scalars pass through. The returned object
    shares no mutable container with the input, so a later mutation of the
    original dict/list cannot change what a snapshot already captured.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    return value


def freeze_field(instance: Any, field_name: str) -> None:
    """Replace one field of a frozen dataclass with its deep-frozen copy.

    Uses ``object.__setattr__`` to bypass the frozen guard during __post_init__,
    which is the sanctioned pattern for normalising frozen-dataclass fields.
    """
    object.__setattr__(instance, field_name, deep_freeze(getattr(instance, field_name)))
