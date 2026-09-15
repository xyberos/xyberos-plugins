"""Thin WebSearch adapters: Tavily, Serper, Brave, Exa, Firecrawl.

Each adapter is a small stdlib ``urllib`` call with a provider-specific
request/parse shape, an injectable ``request`` transport for tests, and an API
key read from an environment variable. A missing key raises a clear
:class:`~xyberos.exceptions.provider.ProviderError`.
"""

from __future__ import annotations

import html
import os
import urllib.parse
from html.parser import HTMLParser
from typing import Any, cast

from xyberos.exceptions.provider import ProviderError

from .contract import SearchResult, WebSearch
from .http import RequestTransport, default_request


#: Browser-ish user agent for the free DuckDuckGo endpoint (no API key).
USER_AGENT = "xyberos-web-search/duckduckgo (no api key)"


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
            headers={"X-API-KEY": cast(str, self._api_key)},
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
            headers={"X-Subscription-Token": cast(str, self._api_key)},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        payload = cast(dict[str, Any], body) if isinstance(body, dict) else {}
        results = cast(list[dict[str, Any]], payload.get("web", {}).get("results", []))
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
            headers={"x-api-key": cast(str, self._api_key)},
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


class _DdgParser(HTMLParser):
    """Pull ranked result titles / URLs / snippets from DuckDuckGo lite HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[SearchResult] = []
        self._current: dict[str, str] | None = None
        self._buf: list[str] = []
        self._in_link = False
        self._in_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        classes = (attr_map.get("class") or "").split()
        if tag == "a" and "result-link" in classes:
            self._current = {
                "title": "",
                "url": self._clean_url(attr_map.get("href") or ""),
            }
            self._in_link = True
            self._buf = []
        elif tag == "td" and "result-snippet" in classes:
            self._in_snippet = True
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_link or self._in_snippet:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link and self._current is not None:
            self._current["title"] = " ".join("".join(self._buf).split())
            self.results.append(
                SearchResult(title=self._current["title"], url=self._current["url"])
            )
            self._current = None
            self._in_link = False
            self._buf = []
        elif tag == "td" and self._in_snippet:
            snippet = " ".join("".join(self._buf).split())
            if self.results and not self.results[-1].snippet:
                self.results[-1] = SearchResult(
                    title=self.results[-1].title,
                    url=self.results[-1].url,
                    snippet=snippet,
                    score=self.results[-1].score,
                    extra=self.results[-1].extra,
                )
            self._in_snippet = False
            self._buf = []

    @staticmethod
    def _clean_url(href: str) -> str:
        if not href:
            return ""
        if href.startswith("//"):
            href = "https:" + href
        if "uddg=" in href:
            parsed = urllib.parse.urlparse(href)
            return urllib.parse.parse_qs(parsed.query).get("uddg", [href])[0]
        return html.unescape(href)


class DuckDuckGoSearch(WebSearch):
    """Free, keyless web search backed by DuckDuckGo's lite endpoint.

    Implements the same :class:`~xyberos_web_search.contract.WebSearch` contract
    as the paid adapters but requires **no API key** (``api_key`` is accepted
    for registry parity and never used). A bot-block or server-error response
    (HTTP 202/403/5xx, or an empty page) surfaces as no results / a clear
    :class:`~xyberos.exceptions.provider.ProviderError` instead of a crash.
    """

    name = "duckduckgo"
    url = "https://lite.duckduckgo.com/lite/"

    def __init__(
        self,
        api_key: str | None = None,  # accepted for registry parity, never used
        *,
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._request = request or default_request
        self._timeout = timeout

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Return up to ``top_k`` ranked results for ``query``, best first."""
        query = (query or "").strip()
        if not query:
            return []
        limit = max(int(top_k), 1)

        status, body = self._request(
            "GET",
            self.url,
            query={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=self._timeout,
        )
        page = body if isinstance(body, str) else str(body)
        # DuckDuckGo returns HTTP 202/403 (or an empty page) to clients whose
        # TLS fingerprint it dislikes - treat that as "no results", not a crash.
        if status in (202, 403) or not page.strip():
            return []
        _raise_for_status(status, page)

        parser = _DdgParser()
        parser.feed(page)
        return parser.results[:limit]
