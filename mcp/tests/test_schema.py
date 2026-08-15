"""Tests for MCP inputSchema -> typed FunctionTool conversion."""

from __future__ import annotations

import sys
from pathlib import Path

from xyberos.tools import coerce_arguments

from xyberos_mcp import McpClient
from xyberos_mcp.registry import ServerConfig
from xyberos_mcp.schema import build_function_tool, format_tool_result

FAKE_SERVER = Path(__file__).parent / "fake_mcp_server.py"


def _client() -> McpClient:
    return McpClient(
        ServerConfig(name="demo", command=[sys.executable, str(FAKE_SERVER)]),
        timeout=10.0,
    ).connect()


def test_schema_and_coercion():
    client = _client()
    try:
        tool_info = next(t for t in client.list_tools() if t["name"] == "echo")
        tool = build_function_tool("demo", tool_info, client)
        assert tool.name == "demo_echo"
        schema = tool.schema
        assert schema["parameters"]["properties"]["text"] == {"type": "string"}
        assert schema["parameters"]["properties"]["repeat"] == {"type": "integer"}
        assert schema["parameters"]["required"] == ["text"]
    finally:
        client.disconnect()


def test_tool_executes_via_call():
    client = _client()
    try:
        tool_info = next(t for t in client.list_tools() if t["name"] == "add")
        tool = build_function_tool("demo", tool_info, client)
        # Coerces strings to numbers, then round-trips through tools/call.
        result = tool.execute(None, a="2", b="3")
        assert result == "5"
    finally:
        client.disconnect()


def test_format_tool_result_is_error():
    result = {"content": [{"type": "text", "text": "boom"}], "isError": True}
    try:
        format_tool_result(result)
    except Exception as exc:
        assert "boom" in str(exc)
    else:
        raise AssertionError("expected isError result to raise")
