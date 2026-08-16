"""Tests for loading the STT plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_stt import SttPlugin


def _fake_request(transcript="Hello world"):
    def request(method, url, **kwargs):
        return 200, {"results": {"channels": [{"alternatives": [{"transcript": transcript}]}]}}

    return request


def test_plugin_registers_and_executes(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"\x00")
    app = create_app()
    app.load_plugin(SttPlugin(provider="deepgram", api_key="k", request=_fake_request()))
    assert "stt_transcribe" in app.tools.names

    result = app.tools.execute("stt_transcribe", None, audio_path=str(audio))
    assert result == "Hello world"

    app.unload_plugin("stt")
    assert "stt_transcribe" not in app.tools.names


def test_unknown_provider_raises():
    with __import__("pytest").raises(ValueError, match="unknown STT provider"):
        SttPlugin(provider="bogus").speech_to_text()
