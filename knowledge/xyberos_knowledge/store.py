"""Vector-store protocol and adapter conformance checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from xyberos_knowledge.models import VectorMatch, VectorRecord


@runtime_checkable
class VectorStore(Protocol):
    """Application-supplied vector store for ``KnowledgeIndex``.

    ``replace_document`` replaces all previously indexed chunks for that document as one
    operation. ``search`` returns at most ``limit`` matches ordered by descending similarity and
    applies exact equality matching for every metadata filter.
    """

    async def replace_document(self, document_id: str, records: Sequence[VectorRecord]) -> None:
        """Replace one document's indexed records."""
        ...

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and report whether it existed."""
        ...

    async def search(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[VectorMatch]:
        """Return the nearest matching records in descending similarity order."""
        ...
