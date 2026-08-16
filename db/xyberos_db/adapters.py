"""Database adapters implementing the RFC-0020 contract.

``SqliteDatabase`` is stdlib-only and fully tested; the other backends
lazy-import their driver and raise a clear ``ProviderError`` when it is
missing.
"""

from __future__ import annotations

import importlib
from typing import Any

from xyberos.exceptions.provider import ProviderError


def _require(package: str, extra: str) -> Any:
    try:
        return importlib.import_module(package)
    except ImportError as exc:
        raise ProviderError(
            f"the '{package}' package is required for {extra}; install with "
            f"'pip install xyberos-db[{extra}]'"
        ) from exc


class SqliteDatabase:
    """SQLite via the standard library."""

    name = "sqlite"

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._connection: Any = None

    def connect(self) -> None:
        import sqlite3

        self._connection = sqlite3.connect(self._path)
        self._connection.row_factory = sqlite3.Row

    def list_tables(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        cursor = self._connection.execute(sql, tuple(params or ()))
        columns = [description[0] for description in (cursor.description or [])]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class PostgresDatabase:
    """PostgreSQL via lazy ``psycopg``."""

    name = "postgres"

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._connection: Any = None

    def connect(self) -> None:
        psycopg = _require("psycopg", "postgres")
        self._connection = psycopg.connect(self._dsn)

    def list_tables(self) -> list[str]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
            return [str(row[0]) for row in cursor.fetchall()]

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params or ()))
            columns = [description.name for description in (cursor.description or [])]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class MysqlDatabase:
    """MySQL / MariaDB via lazy ``pymysql``."""

    name = "mysql"

    def __init__(self, dsn: str | None = None, **connect_kwargs: Any) -> None:
        # dsn may be mysql://user:pass@host:port/db or keyword args.
        self._dsn = dsn
        self._connect_kwargs = connect_kwargs
        self._connection: Any = None

    def _kwargs(self) -> dict[str, Any]:
        if self._dsn:
            from urllib.parse import urlparse

            parsed = urlparse(self._dsn)
            return {
                "host": parsed.hostname or "localhost",
                "user": parsed.username or "root",
                "password": parsed.password or "",
                "database": (parsed.path or "/").lstrip("/") or None,
                "port": parsed.port or 3306,
            }
        return dict(self._connect_kwargs)

    def connect(self) -> None:
        pymysql = _require("pymysql", "mysql")
        self._connection = pymysql.connect(**self._kwargs())

    def list_tables(self) -> list[str]:
        with self._connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            return [str(row[0]) for row in cursor.fetchall()]

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params or ()))
            columns = [description[0] for description in (cursor.description or [])]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class DuckdbDatabase:
    """DuckDB via lazy ``duckdb``."""

    name = "duckdb"

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._connection: Any = None

    def connect(self) -> None:
        duckdb = _require("duckdb", "duckdb")
        self._connection = duckdb.connect(self._path)

    def list_tables(self) -> list[str]:
        return [str(row[0]) for row in self._connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()]

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        result = self._connection.execute(sql, params or [])
        columns = [description[0] for description in (result.description or [])]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


def build_database(dsn: str | None = None, *, backend: str | None = None) -> Any:
    """Return a :class:`Database` from a DSN or an explicit backend name."""
    if backend:
        name = backend.lower()
        if name == "sqlite":
            return SqliteDatabase(dsn or ":memory:")
        if name == "postgres":
            return PostgresDatabase(dsn or "")
        if name == "mysql":
            return MysqlDatabase(dsn)
        if name == "duckdb":
            return DuckdbDatabase(dsn or ":memory:")
        raise ValueError(f"unknown database backend '{backend}' (sqlite | postgres | mysql | duckdb)")
    if dsn:
        if dsn.startswith("postgres"):
            return PostgresDatabase(dsn)
        if dsn.startswith("mysql"):
            return MysqlDatabase(dsn)
        if dsn.startswith("duckdb"):
            return DuckdbDatabase(dsn)
        return SqliteDatabase(dsn)
    raise ValueError("db plugin not configured: pass dsn=... or backend=...")
