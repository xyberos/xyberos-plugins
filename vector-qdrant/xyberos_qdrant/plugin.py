"""Qdrant plugin entry point (RFC-0019, M4)."""

from __future__ import annotations

import os
from typing import Any

from xyberos.contracts import Plugin, VectorStore

from .vector import QdrantVectorStore


class QdrantPlugin(Plugin):
    """Registers a :class:`QdrantVectorStore` as the app's ``vector_store``.

    Configuration (in priority order): explicit constructor args, then
    ``QDRANT_URL`` / ``QDRANT_API_KEY`` / ``QDRANT_DIM`` env vars. With no
    configuration it defaults to Qdrant's in-memory local mode, which is
    harmless for development and testing.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        api_key: str | None = None,
        location: str | None = None,
        path: str | None = None,
        dim: int | None = None,
        client: Any | None = None,
    ) -> None:
        self._url = url or os.getenv("QDRANT_URL")
        self._api_key = api_key or os.getenv("QDRANT_API_KEY")
        self._location = location
        self._path = path
        raw_dim = dim if dim is not None else os.getenv("QDRANT_DIM")
        self._dim = int(raw_dim) if raw_dim else None
        self._client = client
        self._store: QdrantVectorStore | None = None

    @property
    def name(self) -> str:
        return "qdrant"

    def vector_store(self) -> QdrantVectorStore:
        if self._store is None:
            self._store = QdrantVectorStore(
                url=self._url,
                api_key=self._api_key,
                location=self._location or (":memory:" if not self._url and not self._path else None),
                path=self._path,
                dim=self._dim,
                client=self._client,
            )
        return self._store

    def register(self, kernel: object) -> None:
        kernel.register("vector_store", self.vector_store(), replace=True)

    def unregister(self, kernel: object) -> None:
        pass


#: Auto-discovered by ``app.load_entry_points()``.
plugin = QdrantPlugin()
