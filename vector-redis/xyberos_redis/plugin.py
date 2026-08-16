"""Redis plugin entry point (RFC-0019, M4)."""

from __future__ import annotations

import importlib
import os
from typing import Any

from xyberos.contracts import Plugin
from xyberos.exceptions.provider import ProviderError

from .cache import RedisStringCache
from .memory import RedisMemory
from .vector import RedisVectorStore


def _require_redis() -> Any:
    try:
        redis = importlib.import_module("redis")
    except ImportError as exc:
        raise ProviderError(
            "the 'redis' package is required; install it with "
            "'pip install xyberos[state]'"
        ) from exc
    return redis


class RedisPlugin(Plugin):
    """Registers Redis-backed services.

    Registers named services ``redis_client``, ``redis_vector``,
    ``redis_memory`` and ``redis_cache`` (all sharing one Redis client). When
    ``replace_defaults=True`` it also replaces the app's ``vector_store`` and
    ``memory`` providers. Configuration comes from explicit args, then
    ``REDIS_URL`` / ``REDIS_PREFIX`` env vars.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        client: Any | None = None,
        key_prefix: str | None = None,
        replace_defaults: bool = False,
    ) -> None:
        self._url = url or os.getenv("REDIS_URL")
        self._client = client
        self._prefix = key_prefix or os.getenv("REDIS_PREFIX") or "xyberos"
        self._replace_defaults = replace_defaults

    @property
    def name(self) -> str:
        return "redis"

    def _shared_client(self) -> Any:
        if self._client is None:
            redis = _require_redis()
            self._client = redis.from_url(self._url) if self._url else redis.Redis()
        return self._client

    def register(self, kernel: object) -> None:
        client = self._shared_client()
        kernel.register("redis_client", client, replace=True)
        kernel.register(
            "redis_vector",
            RedisVectorStore(client=client, key_prefix=f"{self._prefix}:vs"),
            replace=True,
        )
        kernel.register(
            "redis_memory",
            RedisMemory(client=client, key=f"{self._prefix}:memory"),
            replace=True,
        )
        kernel.register(
            "redis_cache",
            RedisStringCache(client=client, key_prefix=f"{self._prefix}:cache"),
            replace=True,
        )
        if self._replace_defaults:
            kernel.register(
                "vector_store",
                RedisVectorStore(client=client, key_prefix=f"{self._prefix}:vs"),
                replace=True,
            )
            kernel.register(
                "memory",
                RedisMemory(client=client, key=f"{self._prefix}:memory"),
                replace=True,
            )

    def unregister(self, kernel: object) -> None:
        pass


#: Auto-discovered by ``app.load_entry_points()``.
plugin = RedisPlugin()
