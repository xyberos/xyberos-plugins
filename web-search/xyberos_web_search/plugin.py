"""Web search plugin entry point (RFC-0019, M5).

Registers a single ``web_search(query, top_k=5)`` typed tool backed by the
configured provider. Provider and API key come from explicit args, then
``WEB_SEARCH_PROVIDER`` / provider-specific ``*_API_KEY`` env vars (default
provider: ``tavily``). Calling the tool without a key raises a clear
``ProviderError``.
"""

from __future__ import annotations

import os
from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .http import RequestTransport
from .registry import get_web_search


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class WebSearchPlugin(Plugin):
    """Registers the ``web_search`` tool."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        *,
        env_prefix: str = "WEB_SEARCH",
        timeout: float = 30.0,
        request: RequestTransport | None = None,
    ) -> None:
        self._provider = (provider or os.getenv(f"{env_prefix}_PROVIDER") or "tavily").lower()
        self._api_key = api_key
        self._env_prefix = env_prefix
        self._timeout = timeout
        self._request = request
        self._tools: list[Tool] | None = None

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def provider_name(self) -> str:
        return self._provider

    def search_provider(self) -> Any:
        return get_web_search(
            self._provider,
            api_key=self._api_key,
            request=self._request,
            timeout=self._timeout,
        )

    def tools(self) -> list[Tool]:
        if self._tools is None:
            provider = self.search_provider()

            def _web_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
                results = provider.search(query, top_k=top_k)
                return [
                    {
                        "title": result.title,
                        "url": result.url,
                        "snippet": result.snippet,
                        "score": result.score,
                    }
                    for result in results
                ]

            self._tools = [
                FunctionTool(
                    "web_search",
                    _web_search,
                    description=(
                        f"Search the web via {self._provider} and return up to "
                        "top_k ranked results (title, url, snippet)."
                    ),
                )
            ]
        return self._tools

    def register(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            _pop_tool(registry, tool.name)


#: Auto-discovered by ``app.load_entry_points()``.
plugin = WebSearchPlugin()
