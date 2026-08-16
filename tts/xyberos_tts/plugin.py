"""TTS plugin entry point (RFC-0019, M8)."""

from __future__ import annotations

import os
from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .adapters import ElevenLabsTTS, OpenAITTS, PiperTTS, PollyTTS
from .contract import TextToSpeech
from .http import RawRequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class TtsPlugin(Plugin):
    """Registers the ``tts_synthesize`` tool backed by a configured provider."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        *,
        env_prefix: str = "TTS",
        voice_id: str = "Joanna",
        model_path: str | None = None,
        raw_request: RawRequestTransport | None = None,
    ) -> None:
        self._provider = (provider or os.getenv(f"{env_prefix}_PROVIDER") or "elevenlabs").lower()
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_path = model_path
        self._raw_request = raw_request

    @property
    def name(self) -> str:
        return "tts"

    def text_to_speech(self) -> TextToSpeech:
        name = self._provider
        if name == "elevenlabs":
            return ElevenLabsTTS(self._api_key, raw_request=self._raw_request)
        if name == "openai":
            return OpenAITTS(self._api_key, raw_request=self._raw_request)
        if name == "polly":
            return PollyTTS(self._voice_id)
        if name == "piper":
            model_path = self._model_path or os.getenv("PIPER_MODEL")
            if not model_path:
                raise ValueError("piper requires a model path (PIPER_MODEL or model_path=...)")
            return PiperTTS(model_path)
        raise ValueError(f"unknown TTS provider '{name}' (elevenlabs | openai | polly | piper)")

    def tools(self) -> list[Tool]:
        provider = self.text_to_speech()

        def _synthesize(text: str, output_path: str) -> str:
            return provider.synthesize(text, output_path)

        return [
            FunctionTool(
                "tts_synthesize",
                _synthesize,
                description=f"Synthesize text to an audio file via {self._provider}.",
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
plugin = TtsPlugin()
