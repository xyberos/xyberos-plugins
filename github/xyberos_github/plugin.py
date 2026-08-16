"""GitHub plugin entry point (RFC-0019, M7)."""

from __future__ import annotations

from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .client import GithubClient
from .http import RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class GithubPlugin(Plugin):
    """Registers GitHub tools (user / repos / issues)."""

    def __init__(self, token: str | None = None, *, request: RequestTransport | None = None) -> None:
        self._client = GithubClient(token, request=request)

    @property
    def name(self) -> str:
        return "github"

    def tools(self) -> list[Tool]:
        client = self._client

        def _get_user(username: str) -> dict[str, Any]:
            return client.get_user(username)

        def _list_repos(username: str, per_page: int = 30) -> list[dict[str, Any]]:
            return client.list_repos(username, per_page=per_page)

        def _create_issue(owner: str, repo: str, title: str, body: str = "") -> dict[str, Any]:
            return client.create_issue(owner, repo, title, body)

        return [
            FunctionTool("github_get_user", _get_user, description="Get a GitHub user's public profile."),
            FunctionTool("github_list_repos", _list_repos, description="List a GitHub user's public repositories."),
            FunctionTool("github_create_issue", _create_issue, description="Create a GitHub issue on a repository."),
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
plugin = GithubPlugin()
