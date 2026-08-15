"""The WebSearch contract (RFC-0019, M5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SearchResult:
    """One ranked web search result."""

    title: str
    url: str
    snippet: str = ""
    score: float | None = None
    extra: dict[str, Any] | None = None


@runtime_checkable
class WebSearch(Protocol):
    """Any provider that turns a query into ranked search results."""

    name: str

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Return up to ``top_k`` results for ``query``, best first."""
        ...
