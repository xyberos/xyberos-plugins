"""Tests for the MCP client over the stdio transport.

Launches the bundled :file:`fake_mcp_server.py` as a subprocess and talks to it
over newline-delimited JSON-RPC — no external network, no third-party SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from xyberos_mcp import McpClient
from xyberos_mcp.registry import ServerConfig

FAKE_SERVER = Path(__file__).parent / "fake_mcp_server.py"


@pytest.fixture()
def config() -> ServerConfig:
    return ServerConfig(name="demo", command=[sys.executable, str(FAKE_SERVER)])


@pytest.fixture()
def client(config) -> McpClient:
    instance = McpClient(config, timeout=10.0).connect()
    yield instance
    instance.disconnect()


def test_initialize_handshake(client):
    assert client.connected
    assert client.server_info["name"] == "demo-mcp-server"


def test_ping(client):
    assert client.ping() is True


def test_list_tools(client):
    tools = client.list_tools()
    names = {tool["name"] for tool in tools}
    assert names == {"echo", "add"}


def test_call_tool_echo(client):
    result = client.call_tool("echo", {"text": "hello", "repeat": 2})
    assert result["content"][0]["text"] == "hello\nhello"


def test_call_tool_add(client):
    result = client.call_tool("add", {"a": 2, "b": 3})
    assert result["content"][0]["text"] == "5"


def test_context_manager(config):
    with McpClient(config, timeout=10.0) as client:
        assert client.connected
        assert client.list_tools()
    assert not client.connected


def test_timeout_raises(config):
    from xyberos_mcp.transport import StdioTransport

    # A command that never answers -> the per-request timeout fires.
    transport = StdioTransport(
        [sys.executable, "-c", "import time; time.sleep(60)"], timeout=1.0
    )
    transport.start()
    try:
        with pytest.raises(Exception, match="timed out"):
            transport.request(1, "ping", {})
    finally:
        transport.close()
