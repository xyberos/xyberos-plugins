"""Redis-backed :class:`~xyberos.contracts.VectorStore` (lazy ``redis``).

Vectors are stored as JSON inside one Redis hash per namespace
(``<prefix>:<namespace>``). On query the whole namespace is scanned and scored
with exact cosine similarity — the same approach the stdlib
``SqliteVectorStore`` uses (it also scans rows and computes cosine in Python),
so behavior is identical and parity holds without requiring a RediSearch
vector module.

Because it is a full :class:`VectorStore`, it can be passed straight to
:class:`~xyberos.router.CacheResponder(store=..., embedder=...)` for
near-exact ``prompt -> answer`` caching.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from xyberos.contracts.vector import ScoredHit, VectorStore
from xyberos.exceptions.provider import ProviderError


def _require_redis() -> Any:
    try:
        redis = importlib.import_module("redis")
    except ImportError as exc:
        raise ProviderError(
            "the 'redis' package is required; install it with "
            "'pip install xyberos[state]'"
        ) from exc
    return redis


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class RedisVectorStore(VectorStore):
    """A :class:`VectorStore` backed by Redis hashes (one per namespace)."""

    def __init__(
        self,
        *,
        url: str | None = None,
        client: Any | None = None,
        key_prefix: str = "xyberos:vs",
    ) -> None:
        self._url = url
        self._client = client
        self._prefix = key_prefix

    def start(self) -> None:
        """Connect to Redis (kernel lifecycle hook)."""
        self._get_client()

    def stop(self) -> None:
        """Release the client (kernel lifecycle hook)."""
        self._client = None

    def upsert(
        self,
        namespace: str,
        id: str,
        vector: Sequence[float],
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        client = self._get_client()
        record = json.dumps(
            {"v": [float(value) for value in vector], "p": dict(payload or {})},
            default=str,
        )
        client.hset(self._key(namespace), str(id), record)

    def query(
        self,
        namespace: str,
        vector: Sequence[float],
        *,
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[ScoredHit]:
        client = self._get_client()
        raw = client.hgetall(self._key(namespace))
        if not raw:
            return []
        query_vector = [float(value) for value in vector]
        scored: list[ScoredHit] = []
        for raw_id, raw_record in raw.items():
            record = json.loads(_decode(raw_record))
            similarity = _cosine(query_vector, record["v"])
            if threshold is not None and similarity < threshold:
                continue
            scored.append(
                ScoredHit(
                    id=_decode(raw_id),
                    score=similarity,
                    payload=record.get("p"),
                )
            )
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]

    def delete(self, namespace: str, id: str) -> None:
        client = self._get_client()
        client.hdel(self._key(namespace), str(id))

    def clear(self, namespace: str) -> None:
        client = self._get_client()
        client.delete(self._key(namespace))

    # -- internals ----------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        redis = _require_redis()
        self._client = redis.from_url(self._url) if self._url else redis.Redis()
        return self._client

    def _key(self, namespace: str) -> str:
        return f"{self._prefix}:{namespace}"
