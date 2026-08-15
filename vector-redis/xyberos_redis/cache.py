"""A tiny exact-match string cache backed by Redis (lazy ``redis``).

This covers the "ephemeral state" side of the RFC-0019 M4 Redis scope; the
*vector* cache backing for :class:`~xyberos.router.CacheResponder` is provided
by :class:`~xyberos_redis.RedisVectorStore` (a full ``VectorStore``), which can
be passed as ``CacheResponder(store=..., embedder=...)`` for near-exact
``prompt -> answer`` caching.
"""

from __future__ import annotations

from typing import Any

from xyberos.exceptions.provider import ProviderError


def _require_redis() -> Any:
    try:
        import redis
    except ImportError as exc:
        raise ProviderError(
            "the 'redis' package is required; install it with "
            "'pip install xyberos[state]'"
        ) from exc
    return redis


class RedisStringCache:
    """An exact-match ``key -> value`` string cache with optional TTL."""

    def __init__(
        self,
        *,
        url: str | None = None,
        client: Any | None = None,
        key_prefix: str = "xyberos:cache",
    ) -> None:
        self._url = url
        self._client = client
        self._prefix = key_prefix

    def start(self) -> None:
        self._get_client()

    def stop(self) -> None:
        self._client = None

    def get(self, key: str) -> str | None:
        value = self._get_client().get(f"{self._prefix}:{key}")
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    def set(self, key: str, value: str, *, ttl: int | None = None) -> None:
        client = self._get_client()
        full_key = f"{self._prefix}:{key}"
        client.set(full_key, value, ex=ttl)

    def delete(self, key: str) -> None:
        self._get_client().delete(f"{self._prefix}:{key}")

    def clear(self) -> None:
        keys = self._keys()
        if keys:
            self._get_client().delete(*keys)

    def _keys(self) -> list[str]:
        client = self._get_client()
        pattern = f"{self._prefix}:*"
        if hasattr(client, "keys"):
            return [k.decode("utf-8") if isinstance(k, bytes) else str(k) for k in client.keys(pattern)]
        return []

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        redis = _require_redis()
        self._client = redis.from_url(self._url) if self._url else redis.Redis()
        return self._client
