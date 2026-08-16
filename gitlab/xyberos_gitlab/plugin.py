"""GitLab plugin entry point (RFC-0019, M7)."""

from __future__ import annotations

from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .client import GitlabClient
from .http import RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class GitlabPlugin(Plugin):
    """Registers GitLab tools (projects)."""

    def __init__(self, token: str | None = None, *, request: RequestTransport | None = None) -> None:
        self._client = GitlabClient(token, request=request)

    @property
    def name(self) -> str:
        return "gitlab"

    def tools(self) -> list[Tool]:
        client = self._client

        def _get_project(project: str) -> dict[str, Any]:
            return client.get_project(project)

        def _list_projects(search: str = "", per_page: int = 20) -> list[dict[str, Any]]:
            return client.list_projects(search, per_page=per_page)

        return [
            FunctionTool("gitlab_get_project", _get_project, description="Get a GitLab project by path or id."),
            FunctionTool("gitlab_list_projects", _list_projects, description="Search GitLab projects."),
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
plugin = GitlabPlugin()
