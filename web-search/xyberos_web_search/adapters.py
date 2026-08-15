"""Thin WebSearch adapters: Tavily, Serper, Brave, Exa, Firecrawl.

Each adapter is a small stdlib ``urllib`` call with a provider-specific
request/parse shape, an injectable ``request`` transport for tests, and an API
key read from an environment variable. A missing key raises a clear
:class:`~xyberos.exceptions.provider.ProviderError`.
"""

from __future__ import annotations

import os
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .contract import SearchResult, WebSearch
from .http import RequestTransport, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise ProviderError(f"search API returned HTTP {status}: {message[:200]}")


class _BaseSearch(WebSearch):
    """Shared plumbing: API key resolution, injectable transport, error check."""

    name = "base"
    api_key_env = "SEARCH_API_KEY"
    url = ""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv(self.api_key_env)
        self._request = request or default_request
        self._timeout = timeout

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if not self._api_key:
            raise ProviderError(
                f"{self.name} requires an API key (set {self.api_key_env})"
            )
        return self._perform(query, max(top_k, 1))

    def _perform(self, query: str, top_k: int) -> list[SearchResult]:  # pragma: no cover
        raise NotImplementedError


class TavilySearch(_BaseSearch):
    """Tavily — POST ``https://api.tavily.com/search``."""

    name = "tavily"
    api_key_env = "TAVILY_API_KEY"
    url = "https://api.tavily.com/search"

    def _perform(self, query: str, top_k: int) -> list[SearchResult]:
        status, body = self._request(
            "POST",
            self.url,
            json_body={"api_key": self._api_key, "query": query, "max_results": top_k},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return [
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("content", "")),
                score=item.get("score"),
            )
            for item in body.get("results", [])
        ][:top_k]


class SerperSearch(_BaseSearch):
    """Serper (Google SERP) — POST ``https://google.serper.dev/search``."""

    name = "serper"
    api_key_env = "SERPER_API_KEY"
    url = "https://google.serper.dev/search"

    def _perform(self, query: str, top_k: int) -> list[SearchResult]:
        status, body = self._request(
            "POST",
            self.url,
            json_body={"q": query, "num": top_k},
            headers={"X-API-KEY": self._api_key},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return [
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get("link", "")),
                snippet=str(item.get("snippet", "")),
            )
            for item in body.get("organic", [])
        ][:top_k]


class BraveSearch(_BaseSearch):
    """Brave Search — GET ``https://api.search.brave.com/res/v1/web/search``."""

    name = "brave"
    api_key_env = "BRAVE_API_KEY"
    url = "https://api.search.brave.com/res/v1/web/search"

    def _perform(self, query: str, top_k: int) -> list[SearchResult]:
        status, body = self._request(
            "GET",
            self.url,
            query={"q": query, "count": top_k},
            headers={"X-Subscription-Token": self._api_key},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        results = (body.get("web") or {}).get("results", []) if isinstance(body, dict) else []
        return [
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("description", "")),
            )
            for item in results
        ][:top_k]


class ExaSearch(_BaseSearch):
    """Exa — POST ``https://api.exa.ai/search``."""

    name = "exa"
    api_key_env = "EXA_API_KEY"
    url = "https://api.exa.ai/search"

    def _perform(self, query: str, top_k: int) -> list[SearchResult]:
        status, body = self._request(
            "POST",
            self.url,
            json_body={"query": query, "numResults": top_k},
            headers={"x-api-key": self._api_key},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return [
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("text", "")),
                score=item.get("score"),
            )
            for item in body.get("results", [])
        ][:top_k]


class FirecrawlSearch(_BaseSearch):
    """Firecrawl — POST ``https://api.firecrawl.dev/v1/search``."""

    name = "firecrawl"
    api_key_env = "FIRECRAWL_API_KEY"
    url = "https://api.firecrawl.dev/v1/search"

    def _perform(self, query: str, top_k: int) -> list[SearchResult]:
        status, body = self._request(
            "POST",
            self.url,
            json_body={"query": query, "limit": top_k},
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return [
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("description", "")),
            )
            for item in body.get("data", [])
        ][:top_k]
