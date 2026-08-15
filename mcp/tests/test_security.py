"""Tests for the security and registry modules."""

from __future__ import annotations

import pytest

from xyberos_mcp import McpSecurityError, ServerAllowlist
from xyberos_mcp.registry import ServerConfig, load_servers
from xyberos_mcp.security import looks_shellish, validate_command


def test_validate_command_rejects_empty():
    with pytest.raises(McpSecurityError):
        validate_command([])


def test_validate_command_rejects_non_strings():
    with pytest.raises(McpSecurityError):
        validate_command(["python", 3])


def test_validate_command_ok():
    assert validate_command(["python", "-m", "server"]) == ["python", "-m", "server"]


def test_looks_shellish():
    assert looks_shellish(["python", "server; rm -rf /"]) is True
    assert looks_shellish(["python", "-m", "server"]) is False


def test_allowlist_allows():
    allowlist = ServerAllowlist(["demo", "remote"])
    allowlist.check("demo")
    allowlist.check("remote")


def test_allowlist_refuses():
    allowlist = ServerAllowlist(["demo"])
    with pytest.raises(McpSecurityError, match="allowlist"):
        allowlist.check("other")


def test_empty_allowlist_allows_everything():
    ServerAllowlist([]).check("anything")


def test_server_config_requires_command_or_url():
    with pytest.raises(ValueError):
        ServerConfig(name="broken")


def test_server_config_stdio_and_http():
    stdio = ServerConfig(name="a", command=["python", "s.py"])
    http = ServerConfig(name="b", url="https://example.com/mcp")
    assert stdio.transport_type == "stdio"
    assert http.transport_type == "http"


def test_server_config_string_command_split():
    config = ServerConfig(name="a", command="python s.py")
    assert config.command == ["python", "s.py"]


def test_load_servers_from_mapping():
    servers = load_servers(
        {"demo": {"command": ["python", "s.py"]}, "remote": {"url": "https://x/mcp"}}
    )
    assert len(servers) == 2
    assert servers[0].name == "demo"
    assert servers[1].url == "https://x/mcp"


def test_load_servers_from_json_file(tmp_path):
    path = tmp_path / "servers.json"
    path.write_text('{"demo": {"command": ["python", "s.py"]}}', encoding="utf-8")
    servers = load_servers(path)
    assert servers[0].name == "demo"
