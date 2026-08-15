"""The MCP client: handshake, tool discovery, and tool calls (RFC-0019, M3).

Implements the client side of the Model Context Protocol: an ``initialize``
handshake, a ``notifications/initialized`` notification, ``tools/list`` and
``tools/call``. Lifecycle (connect/disconnect/reconnect), per-request timeouts,
and correlation are handled here; transports live in :mod:`transport`.
"""

from __future__ import annotations

import threading
from typing import Any

from .errors import McpError
from .registry import ServerConfig
from .transport import HttpTransport, StdioTransport


def _build_transport(config: ServerConfig, *, timeout: float) -> Any:
    if config.command:
        return StdioTransport(
            config.command, env=config.env, cwd=config.cwd, timeout=timeout
        )
    if config.url:
        return HttpTransport(
            config.url, headers=config.headers, timeout=timeout
        )
    raise McpError(f"server '{config.name}' needs a 'command' (stdio) or 'url' (HTTP)")


class McpClient:
    """A single MCP server connection with request/response correlation."""

    def __init__(self, config: ServerConfig, *, timeout: float = 30.0) -> None:
        self._config = config
        self._timeout = timeout
        self._transport: Any = None
        self._connected = False
        self._server_info: dict[str, Any] = {}
        self._protocol_version: str | None = None
        self._id_counter = 0
        self._id_lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def server_info(self) -> dict[str, Any]:
        return dict(self._server_info)

    # -- lifecycle ----------------------------------------------------------

    def connect(self) -> "McpClient":
        """Open the transport and run the MCP initialize handshake."""
        if self._connected:
            return self
        transport = _build_transport(self._config, timeout=self._timeout)
        transport.start()
        self._transport = transport
        try:
            result = self.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "xyberos-mcp", "version": "0.1.0"},
                },
            )
            self._server_info = dict(result.get("serverInfo") or {})
            self._protocol_version = result.get("protocolVersion")
            self._transport.notify("notifications/initialized", {})
            self._connected = True
        except Exception:
            transport.close()
            self._transport = None
            raise
        return self

    def disconnect(self) -> None:
        """Close the transport and drop the connection."""
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self._connected = False

    def reconnect(self) -> "McpClient":
        """Close and re-open the connection (with a fresh handshake)."""
        self.disconnect()
        return self.connect()

    def close(self) -> None:
        self.disconnect()

    def __enter__(self) -> "McpClient":
        return self.connect()

    def __exit__(self, *exc: Any) -> None:
        self.disconnect()

    # -- MCP methods --------------------------------------------------------

    def ping(self) -> bool:
        self.request("ping")
        return True

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list")
        return list(result.get("tools", []))

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.request(
            "tools/call", {"name": name, "arguments": dict(arguments or {})}
        )
        return dict(result)

    # -- internals ----------------------------------------------------------

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._transport is None:
            raise McpError("client is not connected; call connect() first")
        message = self._transport.request(self._next_id(), method, params)
        if "error" in message:
            error = message["error"]
            raise McpError(
                f"{method} failed: {error.get('message', error)}",
                code=error.get("code"),
            )
        result = message.get("result")
        if not isinstance(result, dict):
            raise McpError(f"{method} returned a non-object result")
        return result

    def _next_id(self) -> int:
        with self._id_lock:
            self._id_counter += 1
            return self._id_counter
