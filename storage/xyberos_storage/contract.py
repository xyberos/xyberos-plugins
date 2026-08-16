"""The ObjectStore contract (RFC-0019, M9)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStore(Protocol):
    """Anything that lists, uploads and downloads objects by key."""

    name: str

    def list(self, prefix: str = "") -> list[str]:
        """Return the object keys under ``prefix``."""
        ...

    def upload(self, key: str, data: bytes) -> str:
        """Store ``data`` under ``key``; return the key."""
        ...

    def download(self, key: str) -> bytes:
        """Return the bytes stored under ``key``."""
        ...
