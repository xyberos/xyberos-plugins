"""The TextToSpeech contract (RFC-0019, M8)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TextToSpeech(Protocol):
    """Anything that turns text into an audio file."""

    name: str

    def synthesize(self, text: str, output_path: str) -> str:
        """Write audio for ``text`` to ``output_path`` and return the path."""
        ...
