"""Tests for the Notion API client (injectable transport, no network)."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_notion import NotionClient


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/search"):
            return 200, {"results": [{"id": "page1", "object": "page", "url": "https://www.notion.so/page1"}]}
        if url.endswith("/pages"):
            return 200, {"id": "page2", "url": "https://www.notion.so/page2"}
        return 404, {"message": "Not found"}

    return request


def test_search():
    request = _fake_request()
    client = NotionClient(token="t", request=request)
    results = client.search("roadmap")
    assert results == [{"id": "page1", "object": "page", "url": "https://www.notion.so/page1"}]


def test_create_page():
    request = _fake_request()
    client = NotionClient(token="t", request=request)
    result = client.create_page("db1", "New page")
    assert result == {"id": "page2", "url": "https://www.notion.so/page2"}


def test_sends_notion_version_header():
    captured = {}

    def capturing(method, url, **kwargs):
        captured.update(kwargs)
        return 200, {"results": []}

    NotionClient(token="secret", request=capturing).search("q")
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["headers"]["Notion-Version"] == "2022-06-28"


def test_requires_token():
    request = _fake_request()
    client = NotionClient(token=None, request=request)
    with pytest.raises(ProviderError, match="token"):
        client.search("q")
