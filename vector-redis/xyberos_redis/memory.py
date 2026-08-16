"""Redis-backed :class:`~xyberos.contracts.Memory` (lazy ``redis``).

Mirrors the stdlib ``SqliteMemory`` semantics: ``store`` appends one
reconstructable snapshot (a ``MemoryEntry``) and ``retrieve`` returns all
entries, oldest first, in insertion order. The list lives under
``<prefix>:memory``.
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from typing import Any

from xyberos.contracts.memory import Memory
from xyberos.memory import MemoryEntry
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RedisMemory(Memory):
    """A :class:`Memory` backed by a Redis list (one row per ``store`` call)."""

    def __init__(
        self,
        *,
        url: str | None = None,
        client: Any | None = None,
        key: str = "xyberos:memory",
    ) -> None:
        self._url = url
        self._client = client
        self._key = key

    def start(self) -> None:
        self._get_client()

    def stop(self) -> None:
        self._client = None

    def retrieve(self, context: object) -> list[MemoryEntry]:
        client = self._get_client()
        raw_entries = client.lrange(self._key, 0, -1)
        entries: list[MemoryEntry] = []
        for raw in raw_entries:
            record = json.loads(_decode(raw))
            entries.append(
                MemoryEntry(
                    prompt=record.get("prompt"),
                    response=record.get("response"),
                    metadata=record.get("metadata") or {},
                    plan=record.get("plan"),
                    error=record.get("error"),
                    created_at=record.get("created_at", ""),
                )
            )
        return entries

    def store(self, context: object) -> None:
        client = self._get_client()
        record = json.dumps(
            {
                "prompt": getattr(context, "prompt", None),
                "response": getattr(context, "response", None),
                "metadata": dict(getattr(context, "metadata", None) or {}),
                "plan": getattr(context, "plan", None),
                "error": getattr(context, "error", None),
                "created_at": _utc_now(),
            },
            default=str,
        )
        client.rpush(self._key, record)

    def clear(self) -> None:
        client = self._get_client()
        client.delete(self._key)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        redis = _require_redis()
        self._client = redis.from_url(self._url) if self._url else redis.Redis()
        return self._client
