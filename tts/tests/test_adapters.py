"""Tests for the TTS adapters (injectable transports / fakes, no network)."""

from __future__ import annotations

import importlib.util

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_tts import ElevenLabsTTS, OpenAITTS, PiperTTS, PollyTTS


def test_elevenlabs_synthesize(tmp_path):
    captured = {}

    def raw_request(method, url, **kwargs):
        captured.update(kwargs)
        return 200, b"\x00\x01MP3"

    output = tmp_path / "out.mp3"
    tts = ElevenLabsTTS(api_key="k", raw_request=raw_request)
    result = tts.synthesize("hello", str(output))
    assert result == str(output)
    assert output.read_bytes() == b"\x00\x01MP3"
    assert captured["headers"]["xi-api-key"] == "k"
    assert captured["json_body"]["text"] == "hello"


def test_openai_synthesize(tmp_path):
    def raw_request(method, url, **kwargs):
        return 200, b"MP3DATA"

    output = tmp_path / "out.mp3"
    tts = OpenAITTS(api_key="k", raw_request=raw_request)
    assert tts.synthesize("hi", str(output)) == str(output)
    assert output.read_bytes() == b"MP3DATA"


def test_polly_synthesize_with_fake_client(tmp_path):
    class _FakePolly:
        def __init__(self):
            self.calls = []

        def synthesize_speech(self, **kwargs):
            self.calls.append(kwargs)
            return {"AudioStream": __import__("io").BytesIO(b"MP3AUDIO")}

    fake = _FakePolly()
    output = tmp_path / "out.mp3"
    tts = PollyTTS("Joanna", client=fake)
    assert tts.synthesize("hi", str(output)) == str(output)
    assert fake.calls[0]["Text"] == "hi"
    assert fake.calls[0]["OutputFormat"] == "mp3"


def test_polly_requires_sdk():
    if importlib.util.find_spec("boto3"):
        pytest.skip("boto3 is installed")
    with pytest.raises(ProviderError, match="boto3"):
        PollyTTS(client=None).synthesize("hi", "out.mp3")


def test_piper_synthesize_with_runner(tmp_path):
    commands = []

    def run(command, text):
        commands.append((command, text))
        (tmp_path / "out.wav").write_bytes(b"WAV")

    output = tmp_path / "out.wav"
    tts = PiperTTS("/models/en_US-lessac-high.onnx", executable="piper", run=run)
    assert tts.synthesize("hello", str(output)) == str(output)
    assert commands[0][1] == "hello"
    assert "--model" in commands[0][0]


def test_piper_missing_executable():
    tts = PiperTTS("/models/x.onnx", executable=None, run=lambda *a: 0)
    with pytest.raises(ProviderError, match="piper"):
        tts.synthesize("hi", "out.wav")
