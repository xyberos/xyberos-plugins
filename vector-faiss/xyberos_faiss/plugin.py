"""FAISS plugin entry point (RFC-0019, M4)."""

from __future__ import annotations

import os
from typing import Any

from xyberos.contracts import Plugin, VectorStore

from .vector import FaissVectorStore


class FaissPlugin(Plugin):
    """Registers a :class:`FaissVectorStore` as the app's ``vector_store``.

    ``dim`` is optional and auto-detected from the first upsert. ``FAISS_DIM``
    env var is honored as a fallback.
    """

    def __init__(self, *, dim: int | None = None) -> None:
        raw_dim = dim if dim is not None else os.getenv("FAISS_DIM")
        self._dim = int(raw_dim) if raw_dim else None
        self._store: FaissVectorStore | None = None

    @property
    def name(self) -> str:
        return "faiss"

    def vector_store(self) -> FaissVectorStore:
        if self._store is None:
            self._store = FaissVectorStore(dim=self._dim)
        return self._store

    def register(self, kernel: object) -> None:
        kernel.register("vector_store", self.vector_store(), replace=True)

    def unregister(self, kernel: object) -> None:
        pass


#: Auto-discovered by ``app.load_entry_points()``.
plugin = FaissPlugin()
