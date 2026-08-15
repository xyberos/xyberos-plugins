"""A minimal local MCP server for the example (stdio, newline-delimited JSON-RPC).

Run it directly to smoke-test::

    python examples/demo_mcp_server.py

It exposes two tools: ``echo`` and ``add``.
"""

from __future__ import annotations

import json
import sys
from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "echo",
        "description": "Echo text back, optionally repeated.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo"},
                "repeat": {"type": "integer", "default": 1},
            },
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "Add two numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
]


def handle(message: dict[str, Any]) -> dict[str, Any]:
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "demo-mcp-server", "version": "0.1.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "echo":
            text = arguments.get("text", "")
            repeat = int(arguments.get("repeat", 1))
            return {
                "content": [
                    {"type": "text", "text": ((text + "\n") * max(1, repeat)).rstrip("\n")}
                ]
            }
        if name == "add":
            total = arguments.get("a", 0) + arguments.get("b", 0)
            return {"content": [{"type": "text", "text": _fmt(total)}]}
    return {"content": [{"type": "text", "text": "unknown"}], "isError": True}


def _fmt(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in message:
            continue
        response = {"jsonrpc": "2.0", "id": message["id"], "result": handle(message)}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
