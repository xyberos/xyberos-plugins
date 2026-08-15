"""Server discovery and configuration (RFC-0019, M3).

A server is either **stdio** (a local ``command``) or **streamable HTTP** (a
``url``). Servers are declared as a mapping/JSON/YAML and may also come from
the ``MCP_SERVERS`` environment variable (a path to a JSON file, or inline
JSON). Each configured server is subject to the allowlist at connect time.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from xyberos.exceptions.provider import ProviderError

from .security import validate_command


@dataclass
class ServerConfig:
    """One MCP server to connect to (stdio via ``command`` or HTTP via ``url``)."""

    name: str
    command: list[str] | None = None  # stdio transport (literal argv, no shell)
    url: str | None = None  # streamable HTTP transport
    env: dict[str, str] | None = None
    cwd: str | None = None
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.command, str):
            self.command = self.command.split()
        if self.command is not None:
            self.command = validate_command(self.command)
        if not self.command and not self.url:
            raise ValueError(
                f"server '{self.name}' must declare 'command' (stdio) or 'url' (HTTP)"
            )

    @property
    def transport_type(self) -> str:
        return "stdio" if self.command else "http"


def server_from_dict(name: str, data: Mapping[str, Any]) -> ServerConfig:
    """Build one :class:`ServerConfig` from a plain mapping."""
    command = data.get("command")
    if isinstance(command, str):
        command = command.split()  # a bare string is split into argv
    return ServerConfig(
        name=str(name),
        command=list(command) if command else None,
        url=str(data["url"]) if data.get("url") else None,
        env=dict(data["env"]) if data.get("env") else None,
        cwd=str(data["cwd"]) if data.get("cwd") else None,
        headers=dict(data["headers"]) if data.get("headers") else None,
    )


def load_servers(source: Any) -> list[ServerConfig]:
    """Load servers from a mapping, a list, or a path to a JSON/YAML file."""
    if isinstance(source, (str, Path)):
        return _servers_from_file(source)
    if isinstance(source, Mapping):
        return [server_from_dict(name, data) for name, data in source.items()]
    if isinstance(source, (list, tuple)):
        return [server_from_dict(item["name"], item) for item in source]
    raise TypeError("servers must be a mapping, a list, or a path to a JSON/YAML file")


def servers_from_env(env_prefix: str = "MCP") -> list[ServerConfig]:
    """Discover servers from ``{env_prefix}_SERVERS`` (JSON path or inline)."""
    raw = os.getenv(f"{env_prefix}_SERVERS")
    if not raw:
        return []
    path = Path(raw)
    if path.is_file():
        return load_servers(path)
    try:
        return load_servers(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{env_prefix}_SERVERS is not a file path or valid JSON") from exc


def _servers_from_file(path: str | Path) -> list[ServerConfig]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # optional dependency
        except ImportError as exc:
            raise ProviderError(
                "the 'PyYAML' package is required to load YAML server configs; "
                "use JSON or install PyYAML"
            ) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return load_servers(data)
