"""Slack plugin entry point (RFC-0019, M7)."""

from __future__ import annotations

from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .client import SlackClient
from .http import RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class SlackPlugin(Plugin):
    """Registers Slack tools (post messages / list channels)."""

    def __init__(self, token: str | None = None, *, request: RequestTransport | None = None) -> None:
        self._client = SlackClient(token, request=request)

    @property
    def name(self) -> str:
        return "slack"

    def tools(self) -> list[Tool]:
        client = self._client

        def _post_message(channel: str, text: str) -> dict[str, Any]:
            return client.post_message(channel, text)

        def _list_channels(limit: int = 100) -> list[dict[str, Any]]:
            return client.list_channels(limit)

        return [
            FunctionTool("slack_post_message", _post_message, description="Post a message to a Slack channel."),
            FunctionTool("slack_list_channels", _list_channels, description="List public Slack channels."),
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
plugin = SlackPlugin()
