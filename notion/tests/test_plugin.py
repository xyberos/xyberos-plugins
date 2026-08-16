"""Tests for loading the Notion plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_notion import NotionPlugin


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/search"):
            return 200, {"results": [{"id": "page1", "object": "page", "url": "https://www.notion.so/page1"}]}
        return 200, {"id": "page2", "url": "https://www.notion.so/page2"}

    return request


def test_plugin_registers_and_executes():
    app = create_app()
    app.load_plugin(NotionPlugin(token="t", request=_fake_request()))
    assert "notion_search" in app.tools.names
    assert "notion_create_page" in app.tools.names

    results = app.tools.execute("notion_search", None, query="roadmap")
    assert results[0]["id"] == "page1"

    app.unload_plugin("notion")
