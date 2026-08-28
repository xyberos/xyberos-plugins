"""Tests for the MCP server exposure (build_server / expose / _tool_callable).

The server module requires the official MCP SDK (``mcp<2`` FastMCP or ``mcp>=2``
MCPServer); the whole module skips cleanly when it is not installed.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

try:  # mcp < 2
    import mcp.server.fastmcp  # noqa: F401
except Exception:
    try:  # mcp >= 2
        import mcp.server.mcpserver  # noqa: F401
    except Exception:
        pytest.skip("requires the official MCP SDK (install 'xyberos-mcp[mcp]')", allow_module_level=True)

from xyberos import create_app
from xyberos.tools import FunctionTool

from xyberos_mcp import McpClient
from xyberos_mcp.registry import ServerConfig
from xyberos_mcp.server import _tool_callable, build_server

PLUGIN_ROOT = str(Path(__file__).parent.parent)


def _app() -> object:
    app = create_app()

    def echo(text: str, repeat: int = 1) -> str:
        return text * repeat

    def add(a: float, b: float) -> float:
        return a + b

    app.tools.register(FunctionTool("echo", echo, description="Echo text"))
    app.tools.register(FunctionTool("add", add, description="Add two numbers"))
    return app


def _server_tools(server):
    return asyncio.run(server.list_tools())


def _tool_schema(tool) -> dict:
    for attr in ("parameters", "input_schema", "inputSchema"):
        value = getattr(tool, attr, None)
        if value is not None:
            return value
    return {}


def test_tool_callable_executes_tool():
    callable_ = _tool_callable(_app().tools.get("echo"))
    assert callable_(text="ab", repeat=3) == "ababab"


def test_build_server_exposes_all_tools():
    tools = {t.name: t for t in _server_tools(build_server(_app()))}
    assert set(tools) == {"echo", "add"}
    params = _tool_schema(tools["echo"])
    assert "text" in params["properties"]
    assert "repeat" in params["properties"]
    # "text" (no default) is always required; SDK versions differ on whether a
    # defaulted param like "repeat" lands in "required", so only assert the
    # stable guarantee.
    assert "text" in params["required"]


def test_build_server_filters_tools():
    names = [t.name for t in _server_tools(build_server(_app(), tools=["echo"]))]
    assert names == ["echo"]


def test_expose_round_trip_over_stdio(tmp_path):
    """Expose a server over stdio and call a tool through the xyberos client."""
    script = tmp_path / "expose_runner.py"
    script.write_text(
        "\n".join(
            [
                "import sys",
                f"sys.path.insert(0, {PLUGIN_ROOT!r})",
                "from xyberos import create_app",
                "from xyberos.tools import FunctionTool",
                "from xyberos_mcp.server import expose",
                "",
                "def echo(text: str, repeat: int = 1) -> str:",
                "    return text * repeat",
                "",
                "app = create_app()",
                "app.tools.register(FunctionTool('echo', echo, description='Echo text'))",
                "expose(app, transport='stdio')",
            ]
        ),
        encoding="utf-8",
    )

    client = McpClient(
        ServerConfig(name="exposed", command=[sys.executable, str(script)]),
        timeout=20.0,
    ).connect()
    try:
        tools = client.list_tools()
        assert any(t["name"] == "echo" for t in tools)
        result = client.call_tool("echo", {"text": "hi", "repeat": 3})
        text = "\n".join(
            str(item.get("text", "")) for item in result.get("content") or []
        )
        assert text == "hihihi"
    finally:
        client.disconnect()
