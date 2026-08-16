"""Tests for the Slack Web API client (injectable transport, no network)."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_slack import SlackClient


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/chat.postMessage"):
            return 200, {"ok": True, "channel": "C123", "ts": "1700000000.000001"}
        if url.endswith("/conversations.list"):
            return 200, {"ok": True, "channels": [{"id": "C123", "name": "general"}]}
        return 200, {"ok": False, "error": "not_authed"}

    return request


def test_post_message():
    request = _fake_request()
    client = SlackClient(token="t", request=request)
    result = client.post_message("general", "hello")
    assert result == {"ok": True, "channel": "C123", "ts": "1700000000.000001"}


def test_list_channels():
    request = _fake_request()
    client = SlackClient(token="t", request=request)
    channels = client.list_channels(limit=50)
    assert channels == [{"id": "C123", "name": "general"}]


def test_slack_ok_false_raises():
    def request(method, url, **kwargs):
        return 200, {"ok": False, "error": "not_authed"}

    client = SlackClient(token="t", request=request)
    with pytest.raises(ProviderError, match="not_authed"):
        client.list_channels()


def test_requires_token():
    request = _fake_request()
    client = SlackClient(token=None, request=request)
    with pytest.raises(ProviderError, match="token"):
        client.post_message("general", "hi")
