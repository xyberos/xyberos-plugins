"""STT plugin entry point (RFC-0019, M8)."""

from __future__ import annotations

import os
from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .adapters import AssemblyAISTT, DeepgramSTT, LocalWhisperSTT
from .contract import SpeechToText
from .http import RawRequestTransport, RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class SttPlugin(Plugin):
    """Registers the ``stt_transcribe`` tool backed by a configured provider."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        *,
        env_prefix: str = "STT",
        request: RequestTransport | None = None,
        raw_request: RawRequestTransport | None = None,
    ) -> None:
        self._provider = (provider or os.getenv(f"{env_prefix}_PROVIDER") or "deepgram").lower()
        self._api_key = api_key
        self._request = request
        self._raw_request = raw_request

    @property
    def name(self) -> str:
        return "stt"

    def speech_to_text(self) -> SpeechToText:
        name = self._provider
        if name == "whisper":
            return LocalWhisperSTT()
        if name == "assemblyai":
            return AssemblyAISTT(self._api_key, request=self._request)
        if name == "deepgram":
            return DeepgramSTT(self._api_key, request=self._request)
        raise ValueError(f"unknown STT provider '{name}' (deepgram | assemblyai | whisper)")

    def tools(self) -> list[Tool]:
        provider = self.speech_to_text()

        def _transcribe(audio_path: str) -> str:
            return provider.transcribe(audio_path)

        return [
            FunctionTool(
                "stt_transcribe",
                _transcribe,
                description=f"Transcribe an audio file to text via {self._provider}.",
            )
        ]

    def register(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            _pop_tool(registry, tool.name)


#: Auto-discovered by ``app.load_entry_points()``.
plugin = SttPlugin()
