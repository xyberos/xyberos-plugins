"""JSON-RPC 2.0 framing for the MCP server direction.

The client half — ``xyberos.mcp`` in the core package — reads JSON-RPC; this module writes it. The
envelope, the MCP revision both halves speak, and the codes a reply may carry live here, so that the
server module states *what* it answers while this one owns *how* an answer is shaped.

A failure a *request earned* is a value here rather than an exception. A tool name this server does
not offer and a tool whose handler raised are both answers to a message the server read, and the core
tool model already reports a refused call as a result rather than raising; :class:`JsonRpcFault`
keeps that shape on the wire, so the only thing an exception is left to mean is what a Python caller
sees when a message cannot be answered at all — an :class:`~xyberos.errors.McpError`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "JSONRPC_VERSION",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "SUPPORTED_PROTOCOL_VERSION",
    "JsonRpcFault",
    "as_mapping",
    "as_text",
    "error_reply",
    "result_reply",
]

JSONRPC_VERSION = "2.0"
"""The JSON-RPC revision this server writes, and the only value it accepts on a request."""

SUPPORTED_PROTOCOL_VERSION = "2025-06-18"
"""The MCP revision this server speaks.

It is the same string the client half declares. One revision is a fact about the seam, and two
constants free to drift apart would be two answers to one question.
"""

PARSE_ERROR = -32700
"""The body was not JSON, so no request could be read out of it."""

INVALID_REQUEST = -32600
"""The message was read, and is not a JSON-RPC request this server can answer."""

METHOD_NOT_FOUND = -32601
"""The request names a method this server does not implement."""

INVALID_PARAMS = -32602
"""The request's parameters are unusable: an unknown tool, arguments that are not an object, or
arguments the tool's own schema rejects."""

INTERNAL_ERROR = -32603
"""Arguments the schema accepted, and a handler that raised anyway. The reply carries the cause."""


@dataclass(frozen=True)
class JsonRpcFault:
    """A JSON-RPC error a request earned, as a value rather than an exception."""

    code: int
    message: str
    data: Mapping[str, object] | None = None

    def reply(self, request_id: object) -> dict[str, object]:
        """Return this fault as the JSON-RPC error reply to ``request_id``."""
        return error_reply(request_id, self.code, self.message, data=self.data)


def result_reply(request_id: object, result: Mapping[str, object]) -> dict[str, object]:
    """Return ``result`` as the reply to a request."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": dict(result)}


def error_reply(
    request_id: object,
    code: int,
    message: str,
    *,
    data: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return a JSON-RPC error reply, carrying ``data`` when there is any to carry.

    The reply always names the code and the message, because the client half reports both: a server
    that answered with an HTTP status instead would hide the one thing the caller can act on.
    """
    error: dict[str, object] = {"code": code, "message": message}
    if data is not None:
        error["data"] = dict(data)
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def as_mapping(value: object) -> Mapping[str, object] | None:
    """Return ``value`` as a string-keyed mapping, or ``None`` when it is not a JSON object.

    Every read of a request narrows rather than assumes: what arrives on this surface was written by
    another process, so ``params`` is an object only once something has said so.
    """
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)
    return None


def as_text(value: object) -> str | None:
    """Return ``value`` when it is a non-empty string.

    A method name and a tool name are both *a name*, and neither is usable when it is blank: an
    empty one would answer a request that asked for nothing in particular.
    """
    if isinstance(value, str) and value.strip():
        return value
    return None
