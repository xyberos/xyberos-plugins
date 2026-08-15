"""Shared types and text chunking for the documents plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass
class Document:
    """One loaded document: its source, extracted text, and metadata."""

    source: str
    text: str
    metadata: Mapping[str, Any] | None = None


@runtime_checkable
class Loader(Protocol):
    """Any object that turns a path into a list of :class:`Document`."""

    def load(self, path: str, **kwargs: Any) -> list[Document]: ...


def chunk_text(text: str, chunk_size: int = 512) -> list[str]:
    """Split ``text`` into paragraph-aware chunks of at most ``chunk_size`` chars.

    Mirrors ``xyberos.knowledge.ingesting._chunk_text`` so the loaders and the
    core agree on chunk boundaries.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            chunks.append(paragraph)
        else:
            chunks.extend(
                paragraph[index : index + chunk_size]
                for index in range(0, len(paragraph), chunk_size)
            )
    return chunks


def chunk_documents(documents: list[Document], chunk_size: int | None) -> list[Document]:
    """Expand each document into one :class:`Document` per chunk (if sized)."""
    if chunk_size is None:
        return documents
    expanded: list[Document] = []
    for doc in documents:
        for index, chunk in enumerate(chunk_text(doc.text, chunk_size)):
            metadata = dict(doc.metadata or {})
            metadata["chunk"] = index
            expanded.append(Document(source=doc.source, text=chunk, metadata=metadata))
    return expanded
