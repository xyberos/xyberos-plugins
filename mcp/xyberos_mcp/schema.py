"""Convert MCP tool ``inputSchema``s into typed :class:`~xyberos.contracts.Tool`s.

Each server tool becomes a :class:`~xyberos.tools.FunctionTool` whose signature
is derived from the MCP ``inputSchema`` ``properties``/``required`` — so the
JSON schema, argument validation, and coercion all flow through the same public
``FunctionTool`` / ``coerce_arguments`` path as the HTTP/API connector (M2).
"""

from __future__ import annotations

import inspect
import re
from typing import Any

from xyberos.contracts import Tool
from xyberos.tools import FunctionTool

from .client import McpClient
from .errors import McpError

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _safe_identifier(name: str) -> str:
    ident = re.sub(r"\W", "_", name)
    if not ident:
        ident = "param"
    if ident[0].isdigit():
        ident = "_" + ident
    return ident


def _annotation(json_type: str | None) -> type:
    return _TYPE_MAP.get(json_type or "", str)


def format_tool_result(result: dict[str, Any]) -> str:
    """Extract text from an MCP ``tools/call`` result; raise on ``isError``."""
    content = result.get("content") or []
    text = "\n".join(
        str(item.get("text", ""))
        for item in content
        if item.get("type") == "text"
    ).strip()
    if result.get("isError"):
        raise McpError(text or "MCP tool call failed")
    return text


def build_function_tool(
    server_name: str,
    tool: dict[str, Any],
    client: McpClient,
) -> Tool:
    """Build one typed tool for ``tool`` on ``client`` (name ``server_tool``)."""
    tool_name = str(tool["name"])
    name = f"{server_name}_{tool_name}"
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])

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
                annotation=_annotation(prop.get("type")),
            )
        )

    def _call(**kwargs: Any) -> Any:
        arguments = {mapping.get(key, key): value for key, value in kwargs.items()}
        result = client.call_tool(tool_name, arguments)
        return format_tool_result(result)

    _call.__name__ = name
    _call.__qualname__ = name
    _call.__signature__ = inspect.Signature(parameters=signature_params)
    return FunctionTool(name, _call, description=str(tool.get("description", "")))
