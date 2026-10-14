"""What this provider promises without a server, and the suite it runs when there is one.

The tests are ordinary pytest tests: an async scenario is a synchronous test that calls
``asyncio.run(...)``. Everything here runs offline; the conformance suite needs a real PostgreSQL and
is skipped unless ``XYBEROS_POSTGRES_DSN`` names one (``python xyberos_postgres/conformance.py`` runs
it directly, which is what CI does against a service container).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert, select

from xyberos.database.testing import assert_provider_contract
from xyberos.errors import DatabaseConfigurationError, DatabaseConnectionError

from xyberos_postgres import (
    PostgresDatabase,
    PostgresSettings,
    open_database,
    postgres_provider,
)
from xyberos_postgres.conformance import settings_from_environment

#: A port nothing listens on, so a refused connection is the fast, deterministic outcome.
DEAD_SERVER = PostgresSettings(host="127.0.0.1", port=1, connect_timeout=1.0, retry_attempts=1)

LIVE_DSN = os.environ.get("XYBEROS_POSTGRES_DSN")


def test_credentials_are_encoded_so_a_password_cannot_truncate_the_url() -> None:
    settings = PostgresSettings(
        host="db.internal", port=6432, user="app@corp", password="p@ss w/ord", database="app"
    )

    assert settings.url == (
        "postgresql+asyncpg://app%40corp:p%40ss%20w%2Ford@db.internal:6432/app?ssl=prefer"
    )


def test_the_password_is_never_rendered() -> None:
    """A dataclass repr is the quickest way for a credential to reach a log."""
    settings = PostgresSettings(password="s3cret")

    assert "s3cret" not in repr(settings)
    assert "s3cret" not in settings.safe_url
    assert settings.url.count("s3cret") == 1, "the password belongs in the URL and nowhere else"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"port": 0}, "outside 1-65535"),
        ({"host": ""}, "host must not be empty"),
        ({"database": ""}, "database must not be empty"),
        ({"ssl": "sometimes"}, "unsupported ssl mode"),
        ({"pool_size": 0}, "pool_size must be at least 1"),
        ({"max_overflow": -1}, "max_overflow must not be negative"),
        ({"connect_timeout": 0}, "connect_timeout must be positive"),
        ({"statement_timeout_ms": 0}, "statement_timeout_ms must be positive"),
        ({"retry_attempts": 0}, "retry_attempts must be at least 1"),
        ({"retry_base_delay": -0.1}, "retry_base_delay must not be negative"),
    ],
)
def test_settings_refuse_a_value_that_would_fail_later(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(DatabaseConfigurationError, match=message):
        PostgresSettings(**changes)  # type: ignore[arg-type]


def test_the_statement_timeout_is_enforced_by_the_server() -> None:
    settings = PostgresSettings(statement_timeout_ms=2500, application_name="checkout")

    assert settings.connect_arguments() == {
        "timeout": 10.0,
        "server_settings": {"application_name": "checkout", "statement_timeout": "2500"},
    }


def test_an_unstarted_provider_reports_that_rather_than_connecting() -> None:
    database = PostgresDatabase(DEAD_SERVER)

    with pytest.raises(DatabaseConnectionError, match="has not been started"):
        _ = database.engine

    async def scenario() -> None:
        await database.aclose()
        assert database.settings is DEAD_SERVER

    asyncio.run(scenario())


def test_a_refused_connection_is_a_connection_error_not_a_crash() -> None:
    async def scenario() -> None:
        with pytest.raises(DatabaseConnectionError, match="health check failed"):
            await open_database(DEAD_SERVER)

    asyncio.run(scenario())


def test_the_provider_factory_is_zero_argument_and_starts_the_database() -> None:
    factory = postgres_provider(DEAD_SERVER)

    async def scenario() -> None:
        with pytest.raises(DatabaseConnectionError):
            await factory()

    assert factory.__code__.co_argcount == 0
    asyncio.run(scenario())


def test_the_conformance_module_reads_a_dsn() -> None:
    settings = settings_from_environment(
        {"XYBEROS_POSTGRES_DSN": "postgresql://app:pw@db.internal:6432/orders?sslmode=require"}
    )

    assert settings.host == "db.internal"
    assert settings.port == 6432
    assert settings.user == "app"
    assert settings.password == "pw"
    assert settings.database == "orders"
    assert settings.ssl == "require"


def test_the_conformance_module_refuses_a_dsn_it_cannot_use() -> None:
    with pytest.raises(SystemExit, match="must be a postgresql:// DSN"):
        settings_from_environment({"XYBEROS_POSTGRES_DSN": "sqlite:///app.db"})


@pytest.mark.skipif(
    not LIVE_DSN, reason="set XYBEROS_POSTGRES_DSN to a scratch database to run the suite"
)
def test_the_shipped_suite_passes_and_a_failed_body_leaves_nothing_behind() -> None:
    metadata = MetaData()
    items = Table(
        "xyberos_postgres_rollback",
        metadata,
        Column("id", Integer, primary_key=True),
    )

    async def scenario() -> None:
        database = await open_database(settings_from_environment())
        try:
            checked = await assert_provider_contract(database)
            assert checked, "the suite reports what it checked"

            async with database.transaction() as connection:
                await connection.run_sync(metadata.create_all)
                await connection.execute(insert(items).values(id=1))

            with pytest.raises(RuntimeError):
                async with database.transaction() as connection:
                    await connection.execute(insert(items).values(id=2))
                    raise RuntimeError("the application failed mid-transaction")

            async with database.transaction() as connection:
                rows = (await connection.execute(select(items.c.id))).scalars().all()
                assert rows == [1], "the rolled-back insert must not be visible"

            async with database.transaction() as connection:
                await connection.run_sync(metadata.drop_all)
        finally:
            await database.aclose()

    asyncio.run(scenario())


def test_the_package_ships_its_types() -> None:
    marker = Path(__file__).resolve().parents[1] / "xyberos_postgres" / "py.typed"

    assert marker.is_file(), "strict-mode consumers need the PEP 561 marker"
