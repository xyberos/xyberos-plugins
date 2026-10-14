# xyberos-postgres

**A `DatabaseProvider` for PostgreSQL, proved against the suite this project ships.**

Xyberos keeps one database provider in the core (`xyberos[database]`, SQLite) and makes the boundary a
protocol: a service depends on `DatabaseProvider`, never on a driver. This package supplies a second
implementation — SQLAlchemy Core with `asyncpg` — and proves it the way
[the provider guide](https://github.com/xyberos/xyberos2.0/blob/master/docs/database-providers.md)
requires, by running the shipped conformance suite against a real server rather than by asserting that
it works.

## Install

```bash
pip install xyberos-postgres
```

## Register it

A provider arrives the way any other service does: already started, supplied as an instance the
application owns and closes.

```python
from xyberos import App
from xyberos.database import DatabaseProvider
from xyberos_postgres import PostgresSettings, postgres_provider

app = App()
app.provide(
    DatabaseProvider,
    factory=postgres_provider(
        PostgresSettings(host="db.internal", database="app", user="app", password="…")
    ),
    eager=True,
)
```

The settings carry the pool, the connect timeout, the server-side `statement_timeout_ms`, and the
retry budget. The password is never rendered: `safe_url` is the one a log line or an error message
should name.

## Conformance

```bash
XYBEROS_POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/postgres \
  python -m xyberos_postgres.conformance
```

The core repository's `packages.toml` names that module as this package's conformance target, so the
compatibility job runs it against the published core, and a release waits on it passing against a
PostgreSQL service.

## What it does not do

- **No migrations.** Alembic, its revision bodies, and `batch_alter_table` belong to the provider that
  ships them, not to the contract.
- **No ORM sessions.** The contract exposes transaction boundaries and a bounded retry helper, and so
  does this package.
- **No SQLite assumptions.** `retrying` retries the two failures PostgreSQL asks a client to retry — a
  serialization failure and a deadlock, SQLSTATE `40001` and `40P01` — and raises anything else
  unchanged on the first attempt. A transaction body that raises is rolled back before the error
  continues.
