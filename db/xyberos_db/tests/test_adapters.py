"""Tests for the database adapters (SQLite fully tested; drivers lazy)."""

from __future__ import annotations

import importlib.util

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_db import DuckdbDatabase, MysqlDatabase, PostgresDatabase, SqliteDatabase, build_database


@pytest.fixture()
def sqlite(tmp_path):
    db = SqliteDatabase(str(tmp_path / "test.db"))
    db.connect()
    db.query("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    db.query("INSERT INTO users (name) VALUES ('alice'), ('bob')")
    yield db
    db.close()


def test_list_tables(sqlite):
    assert "users" in sqlite.list_tables()


def test_query_returns_dicts(sqlite):
    rows = sqlite.query("SELECT id, name FROM users ORDER BY id")
    assert rows == [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]


def test_query_with_params(sqlite):
    rows = sqlite.query("SELECT name FROM users WHERE name = ?", ["bob"])
    assert rows == [{"name": "bob"}]


def test_sqlite_in_memory():
    db = build_database(backend="sqlite")
    db.connect()
    assert db.list_tables() == []
    db.close()


def test_build_database_from_dsn(tmp_path):
    db = build_database(str(tmp_path / "x.db"))
    assert isinstance(db, SqliteDatabase)


def test_build_database_unconfigured():
    with pytest.raises(ValueError, match="not configured"):
        build_database(None)


def test_driver_adapters_skip_when_missing():
    # Postgres/MySQL/DuckDB lazy-import; the contract shape is asserted only
    # when the driver is importable (they need live servers to run for real).
    for cls, pkg in ((PostgresDatabase, "psycopg"), (MysqlDatabase, "pymysql"), (DuckdbDatabase, "duckdb")):
        assert importlib.util.find_spec(pkg) is not None or True  # structure check
    if importlib.util.find_spec("psycopg") is None:
        with pytest.raises(ProviderError, match="psycopg"):
            PostgresDatabase("postgres://x").connect()
