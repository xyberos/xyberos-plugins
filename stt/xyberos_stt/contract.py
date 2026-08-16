"""The SpeechToText contract (RFC-0019, M8)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SpeechToText(Protocol):
    """Anything that turns an audio file into transcribed text."""

    name: str

    def transcribe(self, audio_path: str) -> str:
        """Return the transcribed text for ``audio_path``."""
        ...
