"""Provider registry for the WebSearch contract."""

from __future__ import annotations

from collections.abc import Callable

from .adapters import (
    BraveSearch,
    DuckDuckGoSearch,
    ExaSearch,
    FirecrawlSearch,
    SerperSearch,
    TavilySearch,
)
from .contract import WebSearch
from .http import RequestTransport

#: provider key -> adapter class. ``Callable[..., WebSearch]`` (rather than
#: ``type[WebSearch]``) because adapters take keyword constructor args the
#: protocol does not declare.
WebSearchFactory = Callable[..., WebSearch]

#: provider key -> adapter class
PROVIDERS: dict[str, WebSearchFactory] = {
    "tavily": TavilySearch,
    "serper": SerperSearch,
    "brave": BraveSearch,
    "exa": ExaSearch,
    "firecrawl": FirecrawlSearch,
    "duckduckgo": DuckDuckGoSearch,
}


def get_web_search(
    provider: str,
    *,
    api_key: str | None = None,
    request: RequestTransport | None = None,
    timeout: float = 30.0,
) -> WebSearch:
    """Return a :class:`WebSearch` adapter by provider key."""
    key = provider.lower()
    if key not in PROVIDERS:
        raise ValueError(
            f"unknown web search provider '{provider}' "
            f"(choose from {sorted(PROVIDERS)})"
        )
    return PROVIDERS[key](api_key=api_key, request=request, timeout=timeout)
