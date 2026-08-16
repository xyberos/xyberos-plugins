"""Tests for loading the Discord plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_discord import DiscordPlugin


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/messages"):
            return 200, {"id": "m1", "channel_id": "111", "content": "hello"}
        return 200, {"id": "111", "name": "general", "type": 0}

    return request


def test_plugin_registers_and_executes():
    app = create_app()
    app.load_plugin(DiscordPlugin(token="t", request=_fake_request()))
    assert "discord_send_message" in app.tools.names
    assert "discord_get_channel" in app.tools.names

    result = app.tools.execute("discord_send_message", None, channel_id="111", content="hello")
    assert result["content"] == "hello"

    app.unload_plugin("discord")
