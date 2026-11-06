"""Values and protocols shared by knowledge indexing and vector-store adapters."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType


def _empty_mapping() -> dict[str, object]:
    return {}


@dataclass(frozen=True)
class VectorRecord:
    """One indexed text chunk and its embedding."""

    id: str
    document_id: str
    text: str
    vector: tuple[float, ...]
    metadata: Mapping[str, object] = field(default_factory=_empty_mapping)

    def __post_init__(self) -> None:
        _require_identifier(self.id, "record id")
        _require_identifier(self.document_id, "document id")
        if not _require_string(self.text, "record text"):
            raise ValueError("record text must be a non-empty string")
        vector = tuple(float(value) for value in self.vector)
        _require_vector(vector)
        object.__setattr__(self, "vector", vector)
        metadata = _copy_mapping(self.metadata)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))


@dataclass(frozen=True)
class VectorMatch:
    """A vector-store search result; larger scores must rank as more similar."""

    id: str
    document_id: str
    text: str
    score: float
    metadata: Mapping[str, object] = field(default_factory=_empty_mapping)

    def __post_init__(self) -> None:
        _require_identifier(self.id, "match id")
        _require_identifier(self.document_id, "document id")
        _require_string(self.text, "match text")
        if not math.isfinite(self.score):
            raise ValueError("match score must be finite")
        metadata = _copy_mapping(self.metadata)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))


@dataclass(frozen=True)
class Citation:
    """A stable reference to the source document and retrieved chunk."""

    document_id: str
    chunk_id: str
    score: float


@dataclass(frozen=True)
class KnowledgeHit:
    """Retrieved passage and citation, without a generated answer."""

    text: str
    citation: Citation
    metadata: Mapping[str, object] = field(default_factory=_empty_mapping)

    def __post_init__(self) -> None:
        metadata = _copy_mapping(self.metadata)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))


@dataclass(frozen=True)
class IngestionReceipt:
    """The result of replacing a document's indexed chunks."""

    document_id: str
    chunks: int
    embedding_model: str


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _require_vector(vector: Sequence[float]) -> None:
    if not vector:
        raise ValueError("embedding vector must not be empty")
    if any(not math.isfinite(value) for value in vector):
        raise ValueError("embedding vector values must be finite")


def _copy_mapping(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in value:
        result[key] = value[key]
    return result
