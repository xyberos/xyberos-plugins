"""FAISS-backed :class:`~xyberos.contracts.VectorStore` (lazy ``faiss-cpu``).

A purely local, no-server vector store. Each namespace is an in-memory
``faiss.IndexFlatIP`` over **L2-normalized** vectors, so inner-product scores
equal cosine similarity — matching the ``VectorStore`` contract where a higher
score means more relevant (and matching ``SqliteVectorStore`` / Qdrant
behavior).

The ``faiss`` module is imported lazily on first use and a clear
:class:`~xyberos.exceptions.provider.ProviderError` is raised when it is
missing (``pip install xyberos[vectors]``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from xyberos.contracts.vector import ScoredHit, VectorStore
from xyberos.exceptions.provider import ProviderError


def _require_faiss() -> Any:
    try:
        import faiss
    except ImportError as exc:
        raise ProviderError(
            "the 'faiss-cpu' package is required; install it with "
            "'pip install xyberos[vectors]'"
        ) from exc
    return faiss


def _normalize(vector: Sequence[float]) -> list[float]:
    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0.0:
        return [float(value) for value in vector]
    return [float(value) / norm for value in vector]


class FaissVectorStore(VectorStore):
    """A :class:`VectorStore` backed by an in-memory FAISS index per namespace."""

    def __init__(self, dim: int | None = None, *, normalize: bool = True) -> None:
        if dim is not None and dim <= 0:
            raise ValueError("dim must be a positive integer")
        self._dim = dim
        self._normalize = normalize
        # namespace -> ordered {id: (vector, payload)}
        self._data: dict[str, dict[str, tuple[list[float], dict[str, Any] | None]]] = {}
        # namespace -> faiss index
        self._indexes: dict[str, Any] = {}

    def upsert(
        self,
        namespace: str,
        id: str,
        vector: Sequence[float],
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        faiss = _require_faiss()
        vectors = [float(value) for value in vector]
        if self._dim is None:
            self._dim = len(vectors)
        elif len(vectors) != self._dim:
            raise ValueError(
                f"vector dimension {len(vectors)} != store dimension {self._dim}"
            )
        bucket = self._data.setdefault(namespace, {})
        bucket[str(id)] = (vectors, dict(payload or {}))
        self._rebuild(namespace, faiss)

    def query(
        self,
        namespace: str,
        vector: Sequence[float],
        *,
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[ScoredHit]:
        faiss = _require_faiss()
        bucket = self._data.get(namespace)
        if not bucket:
            return []
        if len(vector) != self._dim:
            raise ValueError(
                f"query dimension {len(vector)} != store dimension {self._dim}"
            )
        index = self._indexes.get(namespace)
        if index is None or index.ntotal != len(bucket):
            self._rebuild(namespace, faiss)
            index = self._indexes[namespace]
        if index.ntotal == 0:
            return []

        import numpy as np

        query_vector = _normalize(list(vector)) if self._normalize else list(vector)
        k = min(max(top_k, 1), index.ntotal)
        distances, indices = index.search(np.array([query_vector], dtype="float32"), k)

        ids = list(bucket.keys())
        hits: list[ScoredHit] = []
        for distance, position in zip(distances[0], indices[0]):
            if position < 0 or position >= len(ids):
                continue
            item_id = ids[int(position)]
            score = float(distance)
            if threshold is not None and score < threshold:
                continue
            _, payload = bucket[item_id]
            hits.append(ScoredHit(id=item_id, score=score, payload=payload))
        return hits

    def delete(self, namespace: str, id: str) -> None:
        faiss = _require_faiss()
        bucket = self._data.get(namespace)
        if bucket is None:
            return
        bucket.pop(str(id), None)
        self._rebuild(namespace, faiss)

    def clear(self, namespace: str) -> None:
        self._data.pop(namespace, None)
        self._indexes.pop(namespace, None)

    # -- internals ----------------------------------------------------------

    def _rebuild(self, namespace: str, faiss: Any) -> None:
        bucket = self._data.get(namespace, {})
        if not bucket:
            self._indexes.pop(namespace, None)
            return
        import numpy as np

        vectors = [v for v, _ in bucket.values()]
        if self._normalize:
            vectors = [_normalize(v) for v in vectors]
        index = faiss.IndexFlatIP(self._dim or len(vectors))
        index.add(np.array(vectors, dtype="float32"))
        self._indexes[namespace] = index
