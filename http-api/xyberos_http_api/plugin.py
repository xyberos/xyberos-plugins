"""Generic HTTP/API connector plugin (RFC-0019, M2).

Ships as a plugin using only the public ``xyberos`` API — the ``Plugin``
contract plus ``Tool`` / ``FunctionTool``. A declarative spec (passed directly,
or loaded from ``HTTP_API_SPEC`` / ``HTTP_API_SPEC_JSON``) yields one typed
:class:`~xyberos.contracts.Tool` per declared operation.

The module-level ``plugin`` instance is safe to auto-discover via the
``xyberos.plugins`` entry-point group: when no spec is configured it registers
nothing and logs a warning instead of raising.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from xyberos.contracts import Plugin, Tool

from .builder import build_operation_tool
from .client import HttpClient
from .spec import HttpApiSpec, load_spec


def _pop_tool(registry: Any, name: str) -> None:
    """Best-effort removal of a tool (ToolRegistry has no public unregister)."""
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


def _normalize_specs(spec: Any) -> list[HttpApiSpec]:
    loaded = load_spec(spec)
    return loaded if isinstance(loaded, list) else [loaded]


class HttpApiPlugin(Plugin):
    """Registers one typed :class:`Tool` per declared operation."""

    def __init__(self, spec: Any = None, *, env_prefix: str = "HTTP_API") -> None:
        # Spec resolution is deferred so the module-level instance can be
        # auto-discovered even before any configuration exists.
        self._spec_arg = spec
        self._env_prefix = env_prefix
        self._specs: list[HttpApiSpec] | None = None
        self._tools: list[Tool] | None = None

    @property
    def name(self) -> str:
        return "http_api"

    # -- public API ---------------------------------------------------------

    def tools(self) -> list[Tool]:
        """The generated tools; raises if no spec has been configured."""
        if self._tools is None:
            specs = self._resolve_specs()
            built: list[Tool] = []
            multiple = len(specs) > 1
            for spec in specs:
                prefix = f"{spec.name}_" if multiple else ""
                client = HttpClient(
                    spec.base_url,
                    headers=spec.headers,
                    auth=spec.auth if spec.auth.type != "none" else None,
                    rate_limit=spec.rate_limit,
                    timeout=spec.timeout,
                )
                for operation in spec.operations:
                    built.append(build_operation_tool(spec, operation, client, prefix=prefix))
            self._tools = built
        return self._tools

    def register(self, kernel: object) -> None:
        try:
            tools = self.tools()
        except ValueError as exc:
            logger = getattr(kernel, "logger", None)
            if logger is not None and callable(getattr(logger, "warning", None)):
                logger.warning("http_api plugin not configured: %s", exc)
            return
        registry = kernel.resolve("tools")
        for tool in tools:
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        if self._spec_arg is None and self._specs is None and not self._configured_via_env():
            return
        registry = kernel.resolve("tools")
        for tool in self.tools():
            _pop_tool(registry, tool.name)

    def _configured_via_env(self) -> bool:
        prefix = self._env_prefix
        return bool(os.getenv(f"{prefix}_SPEC") or os.getenv(f"{prefix}_SPEC_JSON"))

    # -- internals ----------------------------------------------------------

    def _resolve_specs(self) -> list[HttpApiSpec]:
        if self._specs is None:
            if self._spec_arg is not None:
                self._specs = _normalize_specs(self._spec_arg)
            else:
                self._specs = _normalize_specs(self._spec_from_env())
        return self._specs

    def _spec_from_env(self) -> Any:
        prefix = self._env_prefix
        spec_json = os.getenv(f"{prefix}_SPEC_JSON")
        if spec_json:
            try:
                return json.loads(spec_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{prefix}_SPEC_JSON is not valid JSON: {exc}") from exc
        spec_path = os.getenv(f"{prefix}_SPEC")
        if spec_path:
            path = Path(spec_path)
            if not path.is_file():
                raise ValueError(f"{prefix}_SPEC points to a missing file: {path}")
            return path
        raise ValueError(
            "http_api plugin is not configured: pass spec=... or set "
            f"{prefix}_SPEC (path to a JSON/YAML file) or {prefix}_SPEC_JSON"
        )


#: Auto-discovered by ``app.load_entry_points()``.
plugin = HttpApiPlugin()
