"""Run the shipped conformance suite against this provider.

The core repository's ``packages.toml`` names this module as the package's conformance target, so
the compatibility job runs it with ``python -c`` against the published core, and this package's own
CI runs it against a PostgreSQL service before a release is tagged. It exits non-zero when a check
fails, which is the point: a package that is installed and not checked is worse than one that is not
installed at all.

The database is named by ``XYBEROS_POSTGRES_DSN``; the default is a local scratch database, which is
what a service container started for this purpose serves.
"""

from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import urlsplit

from xyberos.database.testing import assert_provider_contract

from xyberos_postgres import PostgresSettings, open_database

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5432/postgres"
"""A local scratch database, which is what CI starts a service container to serve."""


def settings_from_environment(environment: dict[str, str] | None = None) -> PostgresSettings:
    """Build settings from ``XYBEROS_POSTGRES_DSN``.

    A DSN rather than five variables, because a DSN is what a service container and a hosted
    database both hand out, and it carries the sslmode the server requires.
    """
    source = os.environ if environment is None else environment
    dsn = source.get("XYBEROS_POSTGRES_DSN", DEFAULT_DSN)
    parts = urlsplit(dsn)
    if parts.scheme not in {"postgres", "postgresql"}:
        raise SystemExit(
            "XYBEROS_POSTGRES_DSN must be a postgresql:// DSN, not "
            f"{parts.scheme or 'a relative path'!r}"
        )
    query = dict(pair.split("=", 1) for pair in parts.query.split("&") if "=" in pair)
    return PostgresSettings(
        host=parts.hostname or "localhost",
        port=parts.port or 5432,
        user=parts.username or "postgres",
        password=parts.password or "",
        database=parts.path.lstrip("/") or "postgres",
        ssl=query.get("sslmode", "prefer"),
        application_name="xyberos-postgres-conformance",
    )


def main() -> int:
    """Run the suite, report what was checked, and return an exit code."""
    settings = settings_from_environment()

    async def run() -> tuple[str, ...]:
        database = await open_database(settings)
        try:
            return await assert_provider_contract(database)
        finally:
            await database.aclose()

    checked = asyncio.run(run())
    for check in checked:
        print(f"ok: {check}")
    print(f"{len(checked)} checks passed against {settings.safe_url}")
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point the job runs
    sys.exit(main())
