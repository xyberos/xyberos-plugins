"""The MessageQueue contract (RFC-0019, M9)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MessageQueue(Protocol):
    """Anything that publishes and polls messages on named topics."""

    name: str

    def publish(self, topic: str, message: str) -> None:
        """Publish ``message`` to ``topic``."""

    def poll(self, topic: str, timeout: float = 0.1) -> str | None:
        """Return one message from ``topic`` (or ``None`` if empty)."""

    def close(self) -> None:
        """Release the connection."""
