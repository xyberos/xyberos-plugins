"""Typed values stored by ``xyberos-memory``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType

from xyberos.ai import Message


def _empty_mapping() -> dict[str, object]:
    return {}


@dataclass(frozen=True)
class MemoryScope:
    """An application-defined partition; it is not an authorization identity."""

    namespace: str
    key: str

    def __post_init__(self) -> None:
        for name in ("namespace", "key"):
            value = getattr(self, name)
            maximum = 255 if name == "namespace" else 1024
            normalized = _normalize_string(value, f"memory scope {name}", maximum)
            object.__setattr__(self, name, normalized)


@dataclass(frozen=True)
class ConversationEntry:
    """One stored Xyberos AI message."""

    id: str
    scope: MemoryScope
    message: Message
    attributes: Mapping[str, object] = field(default_factory=_empty_mapping)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        attributes = _copy_mapping(self.attributes)
        object.__setattr__(self, "attributes", MappingProxyType(attributes))


@dataclass(frozen=True)
class MemoryFact:
    """The latest value remembered for a key in a scope."""

    scope: MemoryScope
    key: str
    value: object
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _normalize_string(self.key, "fact key", 255))


def _normalize_string(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    return normalized


def _copy_mapping(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in value:
        result[key] = value[key]
    return result
