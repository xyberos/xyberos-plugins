"""Tests for the provider registry and the plugin tool."""

from __future__ import annotations

import pytest
from xyberos import create_app

from xyberos_web_search import PROVIDERS, WebSearchPlugin, get_web_search


def test_get_web_search_known_providers():
    for provider in PROVIDERS:
        assert get_web_search(provider, api_key="k").name == provider


def test_get_web_search_unknown_raises():
    with pytest.raises(ValueError, match="unknown web search provider"):
        get_web_search("bogus")


def test_plugin_conforms_to_contract():
    plugin = WebSearchPlugin()
    assert plugin.name == "web_search"
    assert callable(plugin.register) and callable(plugin.unregister)


def _fake_request(body):
    return lambda *args, **kwargs: (200, body)


def test_plugin_registers_and_calls_web_search_tool():
    body = {
        "results": [
            {"title": "Xyberos Docs", "url": "https://docs.xyberos.com", "content": "Platform docs", "score": 0.8}
        ]
    }
    app = create_app()
    plugin = WebSearchPlugin(provider="tavily", api_key="k", request=_fake_request(body))
    app.load_plugin(plugin)

    assert "web_search" in app.tools.names
    result = app.tools.execute("web_search", None, query="xyberos", top_k=1)
    assert result == [
        {"title": "Xyberos Docs", "url": "https://docs.xyberos.com", "snippet": "Platform docs", "score": 0.8}
    ]

    app.unload_plugin("web_search")
    assert "web_search" not in app.tools.names
