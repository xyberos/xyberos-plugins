"""Qdrant-backed :class:`~xyberos.contracts.VectorStore` (lazy ``qdrant-client``).

Each namespace maps to a Qdrant collection using cosine distance. Supports
hosted Qdrant (``url`` + optional ``api_key``) and local modes (``location=
":memory:"`` or a ``path``). The client is imported lazily on first use and a
clear :class:`~xyberos.exceptions.provider.ProviderError` is raised when
``qdrant-client`` is missing (``pip install xyberos[vectors]``).

Arbitrary string ids are mapped to deterministic UUIDs (Qdrant point ids are
``int`` or ``UUID``); the original id is preserved in the payload and restored
on query, so the :class:`VectorStore` contract (string ids) holds exactly.
"""

from __future__ import annotations

import importlib
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from xyberos.contracts.vector import ScoredHit, VectorStore
from xyberos.exceptions.provider import ProviderError

_DEFAULT_DIM = 384
_ID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace


def _require_qdrant() -> Any:
    try:
        importlib.import_module("qdrant_client")  # noqa: F401
        models = importlib.import_module("qdrant_client.models")
    except ImportError as exc:
        raise ProviderError(
            "the 'qdrant-client' package is required; install it with "
            "'pip install xyberos[vectors]'"
        ) from exc
    return models


class QdrantVectorStore(VectorStore):
    """A :class:`VectorStore` backed by Qdrant (hosted or local)."""

    def __init__(
        self,
        *,
        url: str | None = None,
        api_key: str | None = None,
        location: str | None = None,
        path: str | None = None,
        dim: int | None = None,
        prefer_grpc: bool = False,
        client: Any | None = None,
    ) -> None:
        if dim is not None and dim <= 0:
            raise ValueError("dim must be a positive integer")
        self._url = url
        self._api_key = api_key
        self._location = location
        self._path = path
        self._dim = dim
        self._prefer_grpc = prefer_grpc
        self._client = client
        self._known: set[str] = set()

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Connect to Qdrant (kernel lifecycle hook)."""
        self._get_client()

    def stop(self) -> None:
        """Release the client (kernel lifecycle hook)."""
        self._client = None
        self._known.clear()

    # -- VectorStore contract -----------------------------------------------

    def upsert(
        self,
        namespace: str,
        id: str,
        vector: Sequence[float],
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        models = _require_qdrant()
        client = self._get_client()
        collection = self._ensure_collection(client, namespace, dim=len(vector), models=models)
        stored = dict(payload or {})
        stored["_id"] = str(id)
        point = models.PointStruct(
            id=self._point_id(id),
            vector=[float(value) for value in vector],
            payload=stored,
        )
        client.upsert(collection, points=[point])

    def query(
        self,
        namespace: str,
        vector: Sequence[float],
        *,
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[ScoredHit]:
        client = self._get_client()
        if not self._collection_exists(client, namespace):
            return []
        result = client.query_points(
            collection_name=namespace,
            query=[float(value) for value in vector],
            limit=max(top_k, 1),
            with_payload=True,
        )
        hits: list[ScoredHit] = []
        for point in result.points:
            score = float(point.score)
            if threshold is not None and score < threshold:
                continue
            payload = dict(point.payload or {})
            stored_id = payload.pop("_id", None)
            hits.append(
                ScoredHit(
                    id=str(stored_id) if stored_id is not None else str(point.id),
                    score=score,
                    payload=payload or None,
                )
            )
        return hits

    def delete(self, namespace: str, id: str) -> None:
        models = _require_qdrant()
        client = self._get_client()
        if not self._collection_exists(client, namespace):
            return
        client.delete(
            collection_name=namespace,
            points_selector=models.PointIdsList(points=[self._point_id(id)]),
        )

    def clear(self, namespace: str) -> None:
        client = self._get_client()
        if not self._collection_exists(client, namespace):
            return
        client.delete_collection(collection_name=namespace)
        self._known.discard(namespace)

    # -- helpers ------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        QdrantClient = importlib.import_module("qdrant_client").QdrantClient

        if self._location is not None or self._path is not None:
            self._client = QdrantClient(location=self._location, path=self._path)
        else:
            self._client = QdrantClient(
                url=self._url,
                api_key=self._api_key,
                prefer_grpc=self._prefer_grpc,
            )
        return self._client

    @staticmethod
    def _point_id(id: str) -> Any:
        """Map an arbitrary string id to an int or UUID (Qdrant point id)."""
        if isinstance(id, int):
            return id
        text = str(id)
        if text.isdigit():
            return int(text)
        return uuid.uuid5(_ID_NAMESPACE, text)

    def _ensure_collection(self, client: Any, namespace: str, *, dim: int, models: Any) -> str:
        if namespace in self._known:
            return namespace
        if not self._collection_exists(client, namespace):
            client.create_collection(
                collection_name=namespace,
                vectors_config=models.VectorParams(
                    size=self._dim or dim,
                    distance=models.Distance.COSINE,
                ),
            )
        self._known.add(namespace)
        return namespace

    def _collection_exists(self, client: Any, namespace: str) -> bool:
        try:
            client.get_collection(collection_name=namespace)
            return True
        except Exception:
            return False
