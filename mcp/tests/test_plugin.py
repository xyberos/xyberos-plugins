"""Tests for loading the mcp plugin into a Xyberos app (against the fake server)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from xyberos import create_app

from xyberos_mcp import McpPlugin

FAKE_SERVER = Path(__file__).parent / "fake_mcp_server.py"


def _servers() -> dict:
    return {"demo": {"command": [sys.executable, str(FAKE_SERVER)]}}


def test_plugin_conforms_to_contract():
    plugin = McpPlugin(_servers())
    assert plugin.name == "mcp"
    assert callable(plugin.register) and callable(plugin.unregister)


def test_plugin_registers_and_calls_tools():
    app = create_app()
    app.load_plugin(McpPlugin(_servers()))
    assert "demo_echo" in app.tools.names
    assert "demo_add" in app.tools.names

    assert app.tools.execute("demo_echo", None, text="hi", repeat=2) == "hi\nhi"
    assert app.tools.execute("demo_add", None, a=2, b=3) == "5"

    app.unload_plugin("mcp")
    assert "demo_echo" not in app.tools.names


def test_allowlist_refuses_unknown_server():
    app = create_app()
    plugin = McpPlugin(_servers(), allowlist=["other"])
    with pytest.raises(Exception, match="allowlist"):
        app.load_plugin(plugin)


def test_unconfigured_register_is_safe():
    app = create_app()
    app.load_plugin(McpPlugin())  # no servers, no env -> no-op
    assert "mcp" in app.plugins.names
    app.unload_plugin("mcp")


def test_bad_server_is_skipped():
    app = create_app()
    servers = {
        "demo": {"command": [sys.executable, str(FAKE_SERVER)]},
        "broken": {"command": [sys.executable, "-c", "raise SystemExit(1)"]},
    }
    plugin = McpPlugin(servers, retries=0)
    app.load_plugin(plugin)
    # The healthy server still registers; the broken one is skipped with a warning.
    assert "demo_echo" in app.tools.names
    assert not any(name.startswith("broken_") for name in app.tools.names)
    app.unload_plugin("mcp")
