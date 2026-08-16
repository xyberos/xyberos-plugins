"""Tests for loading the Slack plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_slack import SlackPlugin


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/chat.postMessage"):
            return 200, {"ok": True, "channel": "C123", "ts": "1"}
        return 200, {"ok": True, "channels": [{"id": "C123", "name": "general"}]}

    return request


def test_plugin_registers_and_executes():
    app = create_app()
    app.load_plugin(SlackPlugin(token="t", request=_fake_request()))
    assert "slack_post_message" in app.tools.names
    assert "slack_list_channels" in app.tools.names

    result = app.tools.execute("slack_post_message", None, channel="general", text="hi")
    assert result["ok"] is True

    app.unload_plugin("slack")
