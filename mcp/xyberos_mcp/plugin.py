"""MCP client plugin entry point (RFC-0019, M3).

Connects to every configured server (allowlist-checked), lists its tools, and
registers one typed :class:`~xyberos.contracts.Tool` per server tool — named
``{server}_{tool}``. Connection uses the core's ``utils.resilience.retry`` with
a short timeout; an unreachable server is skipped with a warning so
auto-discovery never takes the app down. The module-level ``plugin`` is safe to
discover via the ``xyberos.plugins`` entry-point group even before any server
is configured.
"""

from __future__ import annotations

import os
from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.utils.resilience import retry

from .client import McpClient
from .registry import ServerConfig, load_servers, servers_from_env
from .schema import build_function_tool
from .security import ServerAllowlist


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class McpPlugin(Plugin):
    """Registers one typed Tool per MCP server tool."""

    def __init__(
        self,
        servers: Any = None,
        *,
        allowlist: list[str] | None = None,
        env_prefix: str = "MCP",
        timeout: float = 30.0,
        retries: int = 1,
    ) -> None:
        self._servers_arg = servers
        self._allowlist = ServerAllowlist(allowlist)
        self._env_prefix = env_prefix
        self._timeout = timeout
        self._retries = max(0, retries)
        self._kernel: Any = None
        self._clients: list[McpClient] = []
        self._tools: list[Tool] | None = None

    @property
    def name(self) -> str:
        return "mcp"

    @property
    def clients(self) -> tuple[McpClient, ...]:
        return tuple(self._clients)

    def tools(self) -> list[Tool]:
        if self._tools is None:
            self._tools = self._connect_and_build()
        return self._tools

    def register(self, kernel: object) -> None:
        self._kernel = kernel
        try:
            tools = self.tools()
        except ValueError as exc:
            logger = getattr(kernel, "logger", None)
            if logger is not None and callable(getattr(logger, "warning", None)):
                logger.warning("mcp plugin not configured: %s", exc)
            return
        registry = kernel.resolve("tools")
        for tool in tools:
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self._tools or []:
            _pop_tool(registry, tool.name)
        for client in self._clients:
            client.disconnect()
        self._clients = []
        self._tools = None

    # -- internals ----------------------------------------------------------

    def _resolve_servers(self) -> list[ServerConfig]:
        if self._servers_arg is not None:
            return load_servers(self._servers_arg)
        servers = servers_from_env(self._env_prefix)
        if not servers:
            raise ValueError(
                "mcp plugin is not configured: pass servers=... or set "
                f"{self._env_prefix}_SERVERS (JSON path or inline JSON)"
            )
        return servers

    def _connect_and_build(self) -> list[Tool]:
        servers = self._resolve_servers()
        built: list[Tool] = []
        for config in servers:
            self._allowlist.check(config.name)
            try:
                client = retry(
                    lambda: McpClient(config, timeout=self._timeout).connect(),
                    max_attempts=self._retries + 1,
                    backoff=0,
                )
            except Exception as exc:
                logger = getattr(self._kernel, "logger", None)
                if logger is not None and callable(getattr(logger, "warning", None)):
                    logger.warning("mcp server '%s' unavailable: %s", config.name, exc)
                continue
            self._clients.append(client)
            for tool in client.list_tools():
                built.append(build_function_tool(config.name, tool, client))
        return built


#: Auto-discovered by ``app.load_entry_points()``.
plugin = McpPlugin()
