"""Speech-to-text adapters: local Whisper + Deepgram + AssemblyAI.

Local Whisper lazy-imports ``whisper``; the cloud adapters use stdlib HTTP with
an injectable transport so tests run without a network.
"""

from __future__ import annotations

import importlib
import os
import time
from pathlib import Path
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RawRequestTransport, RequestTransport, default_raw_request, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, (str, bytes)) else str(body)
    raise ProviderError(f"STT API returned HTTP {status}: {message[:200]}")


def _read_audio(audio_path: str) -> bytes:
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(audio_path)
    return path.read_bytes()


class LocalWhisperSTT:
    """Local OpenAI Whisper transcription (lazy ``whisper`` import)."""

    name = "whisper"

    def __init__(self, model_size: str = "base", *, device: str | None = None) -> None:
        self._model_size = model_size
        self._device = device

    def transcribe(self, audio_path: str) -> str:
        try:
            whisper = importlib.import_module("whisper")
        except ImportError as exc:
            raise ProviderError(
                "the 'openai-whisper' package is required for local Whisper; "
                "install it with 'pip install xyberos-stt[local]'"
            ) from exc
        model = whisper.load_model(self._model_size, device=self._device)
        result = model.transcribe(audio_path)
        return str(result.get("text", "")).strip()


class DeepgramSTT:
    """Deepgram Listen API (cloud)."""

    name = "deepgram"
    url = "https://api.deepgram.com/v1/listen"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "nova-2",
        request: RequestTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("DEEPGRAM_API_KEY")
        self._model = model
        self._request = request or default_request
        self._timeout = timeout

    def transcribe(self, audio_path: str) -> str:
        if not self._api_key:
            raise ProviderError("Deepgram requires an API key (set DEEPGRAM_API_KEY)")
        status, body = self._request(
            "POST",
            self.url,
            query={"model": self._model, "smart_format": "true"},
            raw_body=_read_audio(audio_path),
            headers={"Authorization": f"Token {self._api_key}", "Content-Type": "application/octet-stream"},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        try:
            return body["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Deepgram returned an unexpected response: {body}") from exc


class AssemblyAISTT:
    """AssemblyAI — upload, create a transcript, and poll until complete."""

    name = "assemblyai"
    base_url = "https://api.assemblyai.com/v2"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        request: RequestTransport | None = None,
        poll_interval: float = 1.0,
        max_polls: int = 60,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("ASSEMBLYAI_API_KEY")
        self._request = request or default_request
        self._poll_interval = poll_interval
        self._max_polls = max_polls
        self._timeout = timeout

    def transcribe(self, audio_path: str) -> str:
        if not self._api_key:
            raise ProviderError("AssemblyAI requires an API key (set ASSEMBLYAI_API_KEY)")
        headers = {"authorization": self._api_key}

        status, body = self._request(
            "POST",
            f"{self.base_url}/upload",
            raw_body=_read_audio(audio_path),
            headers=headers,
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        upload_url = body["upload_url"]

        status, body = self._request(
            "POST",
            f"{self.base_url}/transcript",
            json_body={"audio_url": upload_url},
            headers=headers,
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        transcript_id = body["id"]

        for _ in range(self._max_polls):
            status, body = self._request(
                "GET",
                f"{self.base_url}/transcript/{transcript_id}",
                headers=headers,
                timeout=self._timeout,
            )
            _raise_for_status(status, body)
            if body.get("status") == "completed":
                return str(body.get("text", "")).strip()
            if body.get("status") in ("error",):
                raise ProviderError(f"AssemblyAI transcription failed: {body.get('error')}")
            if self._poll_interval:
                time.sleep(self._poll_interval)
        raise ProviderError("AssemblyAI transcription did not complete in time")
