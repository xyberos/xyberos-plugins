"""Text-to-speech adapters: ElevenLabs, OpenAI, Polly (AWS), Piper (local).

Cloud adapters use stdlib HTTP with an injectable transport; Polly lazy-imports
``boto3``; Piper shells out to the ``piper`` CLI (injectable runner for tests).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from xyberos.exceptions.provider import ProviderError

from .http import RawRequestTransport, default_raw_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, (str, bytes)) else str(body)
    raise ProviderError(f"TTS API returned HTTP {status}: {message[:200]}")


def _write_audio(data: bytes, output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


class ElevenLabsTTS:
    """ElevenLabs text-to-speech (cloud)."""

    name = "elevenlabs"
    url = "https://api.elevenlabs.io/v1/text-to-speech"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        voice_id: str = "pNInz6obpgDQGcFmaJgB",  # default "Adam"
        model_id: str = "eleven_multilingual_v2",
        raw_request: RawRequestTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("ELEVENLABS_API_KEY")
        self._voice_id = voice_id
        self._model_id = model_id
        self._raw_request = raw_request or default_raw_request
        self._timeout = timeout

    def synthesize(self, text: str, output_path: str) -> str:
        if not self._api_key:
            raise ProviderError("ElevenLabs requires an API key (set ELEVENLABS_API_KEY)")
        status, data = self._raw_request(
            "POST",
            f"{self.url}/{self._voice_id}",
            query={"model_id": self._model_id},
            json_body={"text": text},
            headers={"xi-api-key": self._api_key},
            timeout=self._timeout,
        )
        _raise_for_status(status, data)
        return _write_audio(data, output_path)


class OpenAITTS:
    """OpenAI text-to-speech (cloud)."""

    name = "openai"
    url = "https://api.openai.com/v1/audio/speech"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "tts-1",
        voice: str = "alloy",
        raw_request: RawRequestTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self._model = model
        self._voice = voice
        self._raw_request = raw_request or default_raw_request
        self._timeout = timeout

    def synthesize(self, text: str, output_path: str) -> str:
        if not self._api_key:
            raise ProviderError("OpenAI TTS requires an API key (set OPENAI_API_KEY)")
        status, data = self._raw_request(
            "POST",
            self.url,
            json_body={"model": self._model, "input": text, "voice": self._voice},
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout,
        )
        _raise_for_status(status, data)
        return _write_audio(data, output_path)


class PollyTTS:
    """AWS Polly (lazy ``boto3``)."""

    name = "polly"

    def __init__(self, voice_id: str = "Joanna", *, client: Any | None = None) -> None:
        self._voice_id = voice_id
        self._client = client

    def synthesize(self, text: str, output_path: str) -> str:
        client = self._get_client()
        response = client.synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId=self._voice_id
        )
        stream = response.get("AudioStream")
        if stream is None:
            raise ProviderError("Polly returned no audio stream")
        return _write_audio(stream.read(), output_path)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:
            raise ProviderError(
                "the 'boto3' package is required for AWS Polly; install it with "
                "'pip install xyberos-tts[aws]'"
            ) from exc
        self._client = boto3.client("polly")
        return self._client


class PiperTTS:
    """Local Piper TTS (shells out to the ``piper`` CLI; injectable runner)."""

    name = "piper"

    def __init__(
        self,
        model_path: str,
        *,
        executable: str | None = None,
        run: Callable[..., int] | None = None,
    ) -> None:
        self._model_path = model_path
        self._executable = executable or shutil.which("piper")
        self._run = run

    def synthesize(self, text: str, output_path: str) -> str:
        if self._executable is None:
            raise ProviderError(
                "the 'piper' executable is not installed; install it and pass "
                "a --model path (or pip install piper-tts)"
            )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [self._executable, "--model", self._model_path, "--output_file", str(path)]
        if self._run is not None:
            self._run(command, text)
        else:
            subprocess.run(
                command,
                input=text,
                text=True,
                capture_output=True,
                check=True,
                shell=False,
            )
        return str(path)
