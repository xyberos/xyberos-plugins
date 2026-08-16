"""Discord plugin entry point (RFC-0019, M7)."""

from __future__ import annotations

from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .client import DiscordClient
from .http import RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class DiscordPlugin(Plugin):
    """Registers Discord tools (send messages / get channels)."""

    def __init__(self, token: str | None = None, *, request: RequestTransport | None = None) -> None:
        self._client = DiscordClient(token, request=request)

    @property
    def name(self) -> str:
        return "discord"

    def tools(self) -> list[Tool]:
        client = self._client

        def _send_message(channel_id: str, content: str) -> dict[str, Any]:
            return client.send_message(channel_id, content)

        def _get_channel(channel_id: str) -> dict[str, Any]:
            return client.get_channel(channel_id)

        return [
            FunctionTool("discord_send_message", _send_message, description="Send a message to a Discord channel."),
            FunctionTool("discord_get_channel", _get_channel, description="Get a Discord channel by id."),
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
plugin = DiscordPlugin()
