"""Tests for the MCP client over the streamable HTTP transport.

Serves a local HTTP endpoint that speaks the MCP JSON-RPC subset, in both
``application/json`` and ``text/event-stream`` response modes.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from xyberos_mcp import McpClient
from xyberos_mcp.registry import ServerConfig

TOOLS: list[dict[str, Any]] = [
    {
        "name": "echo",
        "description": "Echo text back.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
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


def _handle(message: dict[str, Any]) -> dict[str, Any]:
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "http-mcp-server", "version": "0.1.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "echo":
            return {"content": [{"type": "text", "text": arguments.get("text", "")}]}
        if name == "add":
            total = arguments.get("a", 0) + arguments.get("b", 0)
            text = str(int(total)) if float(total).is_integer() else str(total)
            return {"content": [{"type": "text", "text": text}]}
    return {"content": [{"type": "text", "text": "unknown"}], "isError": True}


class _Handler(BaseHTTPRequestHandler):
    mode: str = "json"

    def log_message(self, *args: Any) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0) or 0)
        message = json.loads(self.rfile.read(length).decode("utf-8"))
        if "id" not in message:
            self.send_response(202)
            self.end_headers()
            return
        payload = json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": _handle(message)})
        if self.__class__.mode == "sse":
            body = f"event: message\ndata: {payload}\n\n".encode("utf-8")
            content_type = "text/event-stream"
        else:
            body = payload.encode("utf-8")
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.mark.parametrize("mode", ["json", "sse"])
def test_client_over_http(http_server, mode):
    _Handler.mode = mode
    with McpClient(ServerConfig(name="http", url=http_server), timeout=10.0) as client:
        assert client.connected
        assert client.server_info["name"] == "http-mcp-server"
        assert {t["name"] for t in client.list_tools()} == {"echo", "add"}
        result = client.call_tool("add", {"a": 4, "b": 5})
        assert result["content"][0]["text"] == "9"
