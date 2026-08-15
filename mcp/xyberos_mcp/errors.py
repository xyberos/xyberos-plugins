"""Errors raised by the MCP client plugin."""

from __future__ import annotations


class McpError(Exception):
    """A JSON-RPC error response or protocol failure."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        self.code = code
        super().__init__(message)


class McpTimeoutError(McpError):
    """A request exceeded its timeout."""


class McpSecurityError(McpError):
    """A connection was refused by a security policy."""
