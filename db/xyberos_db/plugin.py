"""Database plugin entry point (RFC-0019/0020, M9)."""

from __future__ import annotations

import os
from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .adapters import build_database


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class DbPlugin(Plugin):
    """Registers ``db_list_tables`` / ``db_query`` tools for a configured database."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        backend: str | None = None,
        env_prefix: str = "DB",
    ) -> None:
        self._dsn = dsn if dsn is not None else os.getenv("DB_DSN") or os.getenv("DATABASE_URL")
        self._backend = backend or os.getenv(f"{env_prefix}_BACKEND")
        self._database: Any = None

    @property
    def name(self) -> str:
        return "db"

    def database(self) -> Any:
        if self._database is None:
            db = build_database(self._dsn, backend=self._backend)
            db.connect()
            self._database = db
        return self._database

    def tools(self) -> list[Tool]:
        db = self.database()

        def _list_tables() -> list[str]:
            return db.list_tables()

        def _query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
            return db.query(sql, params)

        return [
            FunctionTool("db_list_tables", _list_tables, description="List the database tables."),
            FunctionTool("db_query", _query, description="Run a read query and return rows as dicts."),
        ]

    def register(self, kernel: object) -> None:
        try:
            self.database()
        except ValueError as exc:
            logger = getattr(kernel, "logger", None)
            if logger is not None and callable(getattr(logger, "warning", None)):
                logger.warning("db plugin not configured: %s", exc)
            return
        registry = kernel.resolve("tools")
        for tool in self.tools():
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        if self._database is None:
            return  # never configured -> nothing was registered
        registry = kernel.resolve("tools")
        for tool in self.tools():
            _pop_tool(registry, tool.name)
        try:
            self._database.close()
        except Exception:
            pass
        self._database = None


#: Auto-discovered by ``app.load_entry_points()``.
plugin = DbPlugin()
