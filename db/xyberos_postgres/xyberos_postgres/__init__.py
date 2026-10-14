"""PostgreSQL as a Xyberos ``DatabaseProvider``.

Services depend on :class:`~xyberos.database.contracts.DatabaseProvider`, never on this package: the
provider is supplied at composition time, already started, and the application owns closing it.

    from xyberos import App
    from xyberos.database import DatabaseProvider
    from xyberos_postgres import PostgresSettings, postgres_provider

    app = App()
    app.provide(DatabaseProvider, factory=postgres_provider(PostgresSettings(...)), eager=True)

What this package owns is the engine, the pool, and the two engine-specific members of the contract:
the retry policy for PostgreSQL's own contention failures, and rollback on a raising body. What it
does not own is a migration path — Alembic and its dialect-specific revision bodies stay with the
provider that ships them.
"""

from xyberos_postgres.provider import (
    PostgresDatabase,
    PostgresSettings,
    open_database,
    postgres_provider,
)

__all__ = ["PostgresDatabase", "PostgresSettings", "open_database", "postgres_provider"]
