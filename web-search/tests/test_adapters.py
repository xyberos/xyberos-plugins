"""Tests for the WebSearch adapters against fake transports (no network)."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_web_search import PROVIDERS, SearchResult, get_web_search

# provider -> (canned JSON body, expected (title, url, snippet))
BODIES: dict[str, tuple[dict, tuple[str, str, str]]] = {
    "tavily": (
        {"results": [{"title": "Tavily Title", "url": "https://t", "content": "Tavily snippet", "score": 0.9}]},
        ("Tavily Title", "https://t", "Tavily snippet"),
    ),
    "serper": (
        {"organic": [{"title": "Serper Title", "link": "https://s", "snippet": "Serper snippet"}]},
        ("Serper Title", "https://s", "Serper snippet"),
    ),
    "brave": (
        {"web": {"results": [{"title": "Brave Title", "url": "https://b", "description": "Brave snippet"}]}},
        ("Brave Title", "https://b", "Brave snippet"),
    ),
    "exa": (
        {"results": [{"title": "Exa Title", "url": "https://e", "text": "Exa snippet", "score": 0.5}]},
        ("Exa Title", "https://e", "Exa snippet"),
    ),
    "firecrawl": (
        {"data": [{"title": "Fire Title", "url": "https://f", "description": "Fire snippet"}]},
        ("Fire Title", "https://f", "Fire snippet"),
    ),
}


def _fake_request(body: dict):
    def request(method, url, **kwargs):
        return 200, body

    return request


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_adapter_parses_results(provider):
    body, expected = BODIES[provider]
    search = get_web_search(provider, api_key="test-key", request=_fake_request(body))
    results = search.search("xyberos")
    assert isinstance(results[0], SearchResult)
    assert (results[0].title, results[0].url, results[0].snippet) == expected
    assert search.name == provider


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_adapter_respects_top_k(provider):
    body = BODIES[provider][0]
    # Repeat the single result a few times so top_k truncation is observable.
    repeated = _repeat(body)
    search = get_web_search(provider, api_key="k", request=_fake_request(repeated))
    assert len(search.search("q", top_k=2)) == 2


def _repeat(body):
    # Cheap way to get more than one result per provider shape.
    if "organic" in body:
        return {"organic": body["organic"] * 3}
    if "web" in body:
        return {"web": {"results": body["web"]["results"] * 3}}
    if "data" in body:
        return {"data": body["data"] * 3}
    return {"results": body["results"] * 3}


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_missing_api_key_raises(provider, monkeypatch):
    env_var = PROVIDERS[provider].api_key_env
    monkeypatch.delenv(env_var, raising=False)
    search = get_web_search(provider, api_key=None, request=_fake_request({}))
    with pytest.raises(ProviderError, match="API key"):
        search.search("q")


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_http_error_raises(provider):
    search = get_web_search(provider, api_key="k", request=lambda *a, **k: (500, "boom"))
    with pytest.raises(ProviderError, match="500"):
        search.search("q")
