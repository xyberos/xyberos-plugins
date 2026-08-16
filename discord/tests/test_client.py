"""Tests for the Discord bot API client (injectable transport, no network)."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_discord import DiscordClient


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/channels/111/messages"):
            return 200, {"id": "m1", "channel_id": "111", "content": "hello"}
        if url.endswith("/channels/111"):
            return 200, {"id": "111", "name": "general", "type": 0}
        return 404, {"message": "Unknown Channel"}

    return request


def test_send_message():
    request = _fake_request()
    client = DiscordClient(token="t", request=request)
    result = client.send_message("111", "hello")
    assert result == {"id": "m1", "channel_id": "111", "content": "hello"}


def test_get_channel():
    request = _fake_request()
    client = DiscordClient(token="t", request=request)
    assert client.get_channel("111") == {"id": "111", "name": "general", "type": 0}


def test_sends_bot_header():
    request = _fake_request()
    client = DiscordClient(token="secret", request=request)
    client.send_message("111", "hi")
    # verify auth via a capturing request
    captured = {}

    def capturing(method, url, **kwargs):
        captured.update(kwargs)
        return 200, {"id": "m1", "channel_id": "111", "content": "hi"}

    DiscordClient(token="secret", request=capturing).send_message("111", "hi")
    assert captured["headers"]["Authorization"] == "Bot secret"


def test_requires_token():
    request = _fake_request()
    client = DiscordClient(token=None, request=request)
    with pytest.raises(ProviderError, match="token"):
        client.get_channel("111")
