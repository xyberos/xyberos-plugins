"""Tests for loading the db plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_db import DbPlugin


def test_plugin_registers_and_executes():
    app = create_app()
    app.load_plugin(DbPlugin(backend="sqlite"))  # in-memory sqlite
    assert "db_list_tables" in app.tools.names
    assert "db_query" in app.tools.names

    assert app.tools.execute("db_list_tables", None) == []
    rows = app.tools.execute("db_query", None, sql="SELECT 1 AS one")
    assert rows == [{"one": 1}]

    app.unload_plugin("db")
    assert "db_list_tables" not in app.tools.names


def test_unconfigured_register_is_safe():
    app = create_app()
    app.load_plugin(DbPlugin())  # no dsn/backend -> no-op
    assert app.plugins.names == ("db",)
    app.unload_plugin("db")
