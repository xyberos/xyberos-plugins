"""Vision adapters: OpenAI-compatible vision, Tesseract OCR, image generation."""

from __future__ import annotations

import base64
import importlib
import mimetypes
import os
from pathlib import Path
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise ProviderError(f"vision API returned HTTP {status}: {message[:200]}")


def _image_data_url(image_path: str) -> str:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(image_path)
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class OpenAICompatibleVision:
    """Chat-completions vision model (works with OpenAI / Gemini-compatible)."""

    name = "openai_compatible"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        request: RequestTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._request = request or default_request
        self._timeout = timeout

    def describe(self, image_path: str, prompt: str) -> str:
        if not self._api_key:
            raise ProviderError("vision requires an API key (set OPENAI_API_KEY)")
        status, body = self._request(
            "POST",
            f"{self._base_url}/chat/completions",
            json_body={
                "model": self._model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                        ],
                    }
                ],
            },
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"vision returned an unexpected response: {body}") from exc


class TesseractOCR:
    """Local OCR via Tesseract (lazy ``pytesseract`` + ``Pillow``)."""

    name = "tesseract"

    def __init__(self, lang: str = "eng") -> None:
        self._lang = lang

    def extract_text(self, image_path: str) -> str:
        try:
            pytesseract = importlib.import_module("pytesseract")
            Image = importlib.import_module("PIL.Image")
        except ImportError as exc:
            raise ProviderError(
                "OCR requires 'pytesseract' and 'pillow'; install with "
                "'pip install xyberos-vision[ocr]' (plus the tesseract binary)"
            ) from exc
        return pytesseract.image_to_string(Image.open(image_path), lang=self._lang).strip()


class OpenAIImageGenerator:
    """Image generation via the OpenAI images API (b64_json)."""

    name = "openai"
    url = "https://api.openai.com/v1/images/generations"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        request: RequestTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self._model = model
        self._size = size
        self._request = request or default_request
        self._timeout = timeout

    def generate(self, prompt: str, output_path: str) -> str:
        if not self._api_key:
            raise ProviderError("image generation requires an API key (set OPENAI_API_KEY)")
        status, body = self._request(
            "POST",
            self.url,
            json_body={"model": self._model, "prompt": prompt, "n": 1, "size": self._size, "response_format": "b64_json"},
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        try:
            encoded = body["data"][0]["b64_json"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"image generation returned an unexpected response: {body}") from exc
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(encoded))
        return str(path)
