"""Notion plugin entry point (RFC-0019, M7)."""

from __future__ import annotations

from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .client import NotionClient
from .http import RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class NotionPlugin(Plugin):
    """Registers Notion tools (search / create page)."""

    def __init__(self, token: str | None = None, *, request: RequestTransport | None = None) -> None:
        self._client = NotionClient(token, request=request)

    @property
    def name(self) -> str:
        return "notion"

    def tools(self) -> list[Tool]:
        client = self._client

        def _search(query: str = "") -> list[dict[str, Any]]:
            return client.search(query)

        def _create_page(database_id: str, title: str, title_property: str = "Name") -> dict[str, Any]:
            return client.create_page(database_id, title, title_property=title_property)

        return [
            FunctionTool("notion_search", _search, description="Search Notion pages and databases."),
            FunctionTool("notion_create_page", _create_page, description="Create a page in a Notion database."),
        ]

    def register(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            _pop_tool(registry, tool.name)


#: Auto-discovered by ``app.load_entry_points()``.
plugin = NotionPlugin()
