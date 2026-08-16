"""Tests for loading the TTS plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_tts import TtsPlugin


def test_plugin_registers_and_executes(tmp_path):
    def raw_request(method, url, **kwargs):
        return 200, b"MP3DATA"

    app = create_app()
    app.load_plugin(TtsPlugin(provider="openai", api_key="k", raw_request=raw_request))
    assert "tts_synthesize" in app.tools.names

    output = tmp_path / "out.mp3"
    result = app.tools.execute("tts_synthesize", None, text="hello", output_path=str(output))
    assert result == str(output)
    assert output.read_bytes() == b"MP3DATA"

    app.unload_plugin("tts")


def test_unknown_provider_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown TTS provider"):
        TtsPlugin(provider="bogus").text_to_speech()
