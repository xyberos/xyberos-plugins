"""Vision plugin entry point (RFC-0019, M8)."""

from __future__ import annotations

import os
from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .adapters import OpenAICompatibleVision, OpenAIImageGenerator, TesseractOCR
from .http import RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class VisionPlugin(Plugin):
    """Registers vision / OCR / image-generation tools."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        env_prefix: str = "VISION",
        request: RequestTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._env_prefix = env_prefix
        self._request = request
        self._model = os.getenv(f"{env_prefix}_MODEL", "gpt-4o-mini")

    @property
    def name(self) -> str:
        return "vision"

    def vision_model(self) -> OpenAICompatibleVision:
        return OpenAICompatibleVision(self._api_key, model=self._model, request=self._request)

    def ocr(self) -> TesseractOCR:
        return TesseractOCR()

    def image_generator(self) -> OpenAIImageGenerator:
        return OpenAIImageGenerator(self._api_key, request=self._request)

    def tools(self) -> list[Tool]:
        vision = self.vision_model()
        ocr = self.ocr()
        generator = self.image_generator()

        def _describe(image_path: str, prompt: str = "Describe this image in detail.") -> str:
            return vision.describe(image_path, prompt)

        def _ocr(image_path: str) -> str:
            return ocr.extract_text(image_path)

        def _generate(prompt: str, output_path: str) -> str:
            return generator.generate(prompt, output_path)

        return [
            FunctionTool("vision_describe", _describe, description="Describe an image with a vision model."),
            FunctionTool("ocr_extract_text", _ocr, description="Extract text from an image with OCR."),
            FunctionTool("image_generate", _generate, description="Generate an image from a prompt."),
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
plugin = VisionPlugin()
