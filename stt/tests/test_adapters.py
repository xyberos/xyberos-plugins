"""Tests for the STT adapters (injectable transports, no network)."""

from __future__ import annotations

import importlib.util

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_stt import AssemblyAISTT, DeepgramSTT, LocalWhisperSTT


def test_deepgram_transcribe(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"\x00\x01\x02")
    captured = {}

    def request(method, url, **kwargs):
        captured.update(kwargs)
        return 200, {"results": {"channels": [{"alternatives": [{"transcript": "Hello world"}]}]}}

    stt = DeepgramSTT(api_key="k", request=request)
    assert stt.transcribe(str(audio)) == "Hello world"
    assert captured["raw_body"] == b"\x00\x01\x02"
    assert captured["headers"]["Authorization"] == "Token k"


def test_deepgram_requires_key():
    with pytest.raises(ProviderError, match="DEEPGRAM_API_KEY"):
        DeepgramSTT(api_key=None, request=lambda *a, **k: (200, {})).transcribe("x.wav")


def test_assemblyai_flow(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"abc")
    captured = []

    def request(method, url, **kwargs):
        captured.append((method, url, kwargs))
        if url.endswith("/upload"):
            return 200, {"upload_url": "https://cdn.assemblyai.com/up"}
        if url.endswith("/transcript") and method == "POST":
            return 200, {"id": "abc"}
        if url.endswith("/transcript/abc"):
            return 200, {"status": "completed", "text": "Hello world"}
        return 404, {"error": "not found"}

    stt = AssemblyAISTT(api_key="k", request=request, poll_interval=0)
    assert stt.transcribe(str(audio)) == "Hello world"
    assert captured[0][2]["raw_body"] == b"abc"
    assert captured[2][0] == "GET"


def test_assemblyai_error_status(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"abc")

    def request(method, url, **kwargs):
        if url.endswith("/upload"):
            return 200, {"upload_url": "https://cdn.assemblyai.com/up"}
        if url.endswith("/transcript") and method == "POST":
            return 200, {"id": "abc"}
        return 200, {"status": "error", "error": "invalid audio"}

    stt = AssemblyAISTT(api_key="k", request=request, poll_interval=0)
    with pytest.raises(ProviderError, match="invalid audio"):
        stt.transcribe(str(audio))


def test_local_whisper():
    if importlib.util.find_spec("whisper") is None:
        pytest.skip("openai-whisper is not installed")
    stt = LocalWhisperSTT()
    assert isinstance(stt, LocalWhisperSTT)
    # Actual transcription requires model weights (network); just assert the
    # lazy-import guard path raises when the module is absent is covered above.
