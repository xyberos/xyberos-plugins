"""Jira plugin entry point (RFC-0019, M7)."""

from __future__ import annotations

from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .client import JiraClient
from .http import RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class JiraPlugin(Plugin):
    """Registers Jira tools (search / create issues)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        email: str | None = None,
        api_token: str | None = None,
        request: RequestTransport | None = None,
    ) -> None:
        self._client = JiraClient(base_url, email=email, api_token=api_token, request=request)

    @property
    def name(self) -> str:
        return "jira"

    def tools(self) -> list[Tool]:
        client = self._client

        def _search_issues(jql: str, max_results: int = 50) -> list[dict[str, Any]]:
            return client.search_issues(jql, max_results=max_results)

        def _create_issue(project_key: str, summary: str, description: str = "", issuetype: str = "Task") -> dict[str, Any]:
            return client.create_issue(project_key, summary, description, issuetype)

        return [
            FunctionTool("jira_search_issues", _search_issues, description="Search Jira issues with a JQL query."),
            FunctionTool("jira_create_issue", _create_issue, description="Create a Jira issue."),
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
plugin = JiraPlugin()
