"""MCP server exposure for a Xyberos app (RFC-0019, M3 companion).

Turns a :class:`~xyberos.Xyberos` app's registered tools into one MCP server
exposed to external MCP clients (Claude Desktop, VS Code Copilot, Cursor, ...)
over stdio / SSE / streamable HTTP. This is the server half that mirrors
:mod:`xyberos_mcp.client` (the client half imports external servers' tools).

The server is built on the official MCP SDK - ``FastMCP`` (mcp<2) or
``MCPServer`` (mcp>=2) - imported lazily so the client stays stdlib-only.
Install the SDK with ``pip install "xyberos-mcp[mcp]"``.
"""

from __future__ import annotations

import importlib
import inspect
import re
from typing import Any, cast

from .errors import McpError

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _load_server_class() -> type:
    """Return the MCP server class (mcp<2 ``FastMCP`` or mcp>=2 ``MCPServer``)."""
    try:
        module = importlib.import_module("mcp.server.fastmcp")  # mcp < 2
        return cast(type, module.FastMCP)
    except Exception:
        try:
            module = importlib.import_module("mcp.server.mcpserver")  # mcp >= 2
            return cast(type, module.MCPServer)
        except Exception as exc:
            raise McpError(
                "expose()/build_server() require the official MCP SDK; "
                "install 'xyberos-mcp[mcp]'"
            ) from exc


def _safe_identifier(name: str) -> str:
    ident = re.sub(r"\W", "_", name)
    if not ident:
        ident = "param"
    if ident[0].isdigit():
        ident = "_" + ident
    return ident


def _tool_callable(tool: Any) -> Any:
    """Return a plain callable that the MCP SDK can register for ``tool``.

    The signature is rebuilt from ``tool.schema`` - the mirror image of
    :func:`xyberos_mcp.schema.build_function_tool` - so the SDK derives a
    correct ``inputSchema`` and validates incoming arguments before execution.
    """
    schema = cast(dict[str, Any], getattr(tool, "schema", {}) or {})
    parameters = cast(dict[str, Any], schema.get("parameters") or {})
    properties = cast(dict[str, Any], parameters.get("properties") or {})
    required = set(cast(list[str], parameters.get("required") or []))

    mapping: dict[str, str] = {}
    signature_params: list[inspect.Parameter] = []
    for prop_name, prop in properties.items():
        sig_name = prop_name if prop_name.isidentifier() else _safe_identifier(prop_name)
        mapping[sig_name] = prop_name
        default = (
            inspect.Parameter.empty
            if prop_name in required
            else prop.get("default", inspect.Parameter.empty)
        )
        signature_params.append(
            inspect.Parameter(
                sig_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=_TYPE_MAP.get(prop.get("type"), str),
            )
        )

    def _call(**kwargs: Any) -> str:
        arguments = {mapping.get(key, key): value for key, value in kwargs.items()}
        result = tool.execute(None, **arguments)
        return result if isinstance(result, str) else str(result)

    _call.__name__ = tool.name
    _call.__qualname__ = tool.name
    setattr(_call, "__signature__", inspect.Signature(parameters=signature_params))
    return _call


def build_server(
    app: Any,
    tools: list[str] | None = None,
    server_name: str = "xyberos",
) -> Any:
    """Build (but do not run) an MCP server exposing ``app``'s registered tools.

    ``tools=None`` exposes every tool registered on ``app.tools``; a sequence
    of names exposes only those. Returns the SDK server object so callers can
    run it themselves (``server.run(...)``) or mount it into a web app.
    """
    server_class = _load_server_class()
    server = server_class(server_name)

    registry = app.tools
    names = tuple(tools) if tools is not None else registry.names
    for name in names:
        tool = registry.get(name)
        server.tool(name=tool.name, description=tool.description)(_tool_callable(tool))
    return server


def expose(
    app: Any,
    tools: list[str] | None = None,
    server_name: str = "xyberos",
    transport: str = "stdio",
) -> None:
    """Expose ``app``'s tools as one MCP server and run it (blocking).

    ``tools=None`` exposes every registered tool. ``transport`` is ``"stdio"``
    (default), ``"sse"``, or ``"streamable-http"``.
    """
    server = build_server(app, tools=tools, server_name=server_name)
    server.run(transport=transport)
