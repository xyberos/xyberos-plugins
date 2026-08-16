"""Auth plugin entry point (RFC-0019, M9)."""

from __future__ import annotations

import os
from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .jwt import JwtCodec


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class AuthPlugin(Plugin):
    """Registers JWT sign/verify tools backed by a configured :class:`JwtCodec`.

    ``secret`` comes from ``AUTH_JWT_SECRET`` (HS256) or the ``private_key`` /
    ``public_key`` args (RS256). If none is configured the plugin registers
    nothing (logs a warning).
    """

    def __init__(
        self,
        secret: str | None = None,
        *,
        algorithm: str = "HS256",
        private_key: str | None = None,
        public_key: str | None = None,
    ) -> None:
        self._secret = secret if secret is not None else os.getenv("AUTH_JWT_SECRET")
        self._algorithm = algorithm
        self._private_key = private_key or os.getenv("AUTH_JWT_PRIVATE_KEY")
        self._public_key = public_key or os.getenv("AUTH_JWT_PUBLIC_KEY")
        self._codec: JwtCodec | None = None

    @property
    def name(self) -> str:
        return "auth"

    def jwt_codec(self) -> JwtCodec:
        if self._codec is None:
            self._codec = JwtCodec(
                self._secret,
                algorithm=self._algorithm,
                private_key=self._private_key,
                public_key=self._public_key,
            )
        return self._codec

    def tools(self) -> list[Tool]:
        def _sign(payload: dict[str, Any], ttl: int = 3600) -> str:
            return self.jwt_codec().encode(payload, ttl=ttl)

        def _verify(token: str) -> dict[str, Any]:
            return self.jwt_codec().decode(token, verify=True)

        return [
            FunctionTool("jwt_sign", _sign, description="Sign a payload as a JWT."),
            FunctionTool("jwt_verify", _verify, description="Verify and decode a JWT."),
        ]

    def register(self, kernel: object) -> None:
        try:
            self.jwt_codec()
        except Exception as exc:
            logger = getattr(kernel, "logger", None)
            if logger is not None and callable(getattr(logger, "warning", None)):
                logger.warning("auth plugin not configured: %s", exc)
            return
        registry = kernel.resolve("tools")
        for tool in self.tools():
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            _pop_tool(registry, tool.name)


#: Auto-discovered by ``app.load_entry_points()``.
plugin = AuthPlugin()
