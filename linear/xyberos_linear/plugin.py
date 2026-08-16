"""Linear plugin entry point (RFC-0019, M7)."""

from __future__ import annotations

from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .client import LinearClient
from .http import RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class LinearPlugin(Plugin):
    """Registers Linear tools (search / create issues)."""

    def __init__(self, api_key: str | None = None, *, request: RequestTransport | None = None) -> None:
        self._client = LinearClient(api_key, request=request)

    @property
    def name(self) -> str:
        return "linear"

    def tools(self) -> list[Tool]:
        client = self._client

        def _search_issues(query: str = "", first: int = 10) -> list[dict[str, Any]]:
            return client.search_issues(query, first=first)

        def _create_issue(team_id: str, title: str, description: str = "") -> dict[str, Any]:
            return client.create_issue(team_id, title, description)

        return [
            FunctionTool("linear_search_issues", _search_issues, description="Search Linear issues by title."),
            FunctionTool("linear_create_issue", _create_issue, description="Create a Linear issue in a team."),
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
plugin = LinearPlugin()
