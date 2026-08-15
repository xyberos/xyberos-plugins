"""Web search abstraction plugin (RFC-0019, M5).

One :class:`~xyberos_web_search.contract.WebSearch` contract,
:meth:`~xyberos_web_search.contract.WebSearch.search(query, top_k) -> list[Result]`,
with thin adapters for Tavily, Serper, Brave, Exa and Firecrawl behind it. Each
adapter is stdlib-only (``urllib``), injectable for tests, and reads its API key
from an environment variable.
"""

from .contract import SearchResult, WebSearch
from .plugin import WebSearchPlugin
from .registry import PROVIDERS, get_web_search

__all__ = [
    "PROVIDERS",
    "SearchResult",
    "WebSearch",
    "WebSearchPlugin",
    "get_web_search",
]
