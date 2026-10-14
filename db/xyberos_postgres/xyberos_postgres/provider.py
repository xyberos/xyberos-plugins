"""A PostgreSQL provider built on SQLAlchemy Core and the ``asyncpg`` driver.

Two members of the contract are engine-specific, and the provider guide names both as the things
whose meaning changes when the engine changes. They are decided here rather than inherited from the
shipped SQLite provider:

* ``retrying`` retries PostgreSQL's own contention failures — a serialization failure and a deadlock,
  the two SQLSTATEs the server asks a client to retry — and nothing else. Retrying a syntax error or
  a constraint violation would hide it.
* A body that raises leaves no work behind, because the connection's transaction is rolled back
  before the exception continues.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TypeVar
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncTransaction,
    create_async_engine,
)

from xyberos.database.contracts import TransactionOperation
from xyberos.errors import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    DatabaseError,
    TransactionError,
    TransientDatabaseError,
)

T = TypeVar("T")

_SSL_MODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})

#: The SQLSTATEs PostgreSQL asks a client to retry: ``serialization_failure`` and
#: ``deadlock_detected``. Anything else is a bug rather than a timing accident.
_RETRYABLE_SQLSTATES = frozenset({"40001", "40P01"})


@dataclass(frozen=True)
class PostgresSettings:
    """Explicit connection and contention settings for one PostgreSQL database."""

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = field(default="", repr=False)
    """Never rendered. A dataclass repr would put the password into the first log line that prints
    the settings, and a log is the easiest place to lose a credential from."""

    database: str = "postgres"
    ssl: str = "prefer"
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    connect_timeout: float = 10.0
    statement_timeout_ms: int | None = None
    application_name: str = "xyberos"
    retry_attempts: int = 5
    retry_base_delay: float = 0.05

    def __post_init__(self) -> None:
        if not self.host:
            raise DatabaseConfigurationError("host must not be empty")
        if not 1 <= self.port <= 65535:
            raise DatabaseConfigurationError(f"port {self.port} is outside 1-65535")
        if not self.user:
            raise DatabaseConfigurationError("user must not be empty")
        if not self.database:
            raise DatabaseConfigurationError("database must not be empty")
        ssl = self.ssl.lower()
        if ssl not in _SSL_MODES:
            supported = ", ".join(sorted(_SSL_MODES))
            raise DatabaseConfigurationError(
                f"unsupported ssl mode {self.ssl!r}; expected one of: {supported}"
            )
        object.__setattr__(self, "ssl", ssl)
        if self.pool_size < 1:
            raise DatabaseConfigurationError("pool_size must be at least 1")
        if self.max_overflow < 0:
            raise DatabaseConfigurationError("max_overflow must not be negative")
        if self.pool_timeout <= 0:
            raise DatabaseConfigurationError("pool_timeout must be positive")
        if self.connect_timeout <= 0:
            raise DatabaseConfigurationError("connect_timeout must be positive")
        if self.statement_timeout_ms is not None and self.statement_timeout_ms < 1:
            raise DatabaseConfigurationError("statement_timeout_ms must be positive when set")
        if self.retry_attempts < 1:
            raise DatabaseConfigurationError("retry_attempts must be at least 1")
        if self.retry_base_delay < 0:
            raise DatabaseConfigurationError("retry_base_delay must not be negative")

    @property
    def url(self) -> str:
        """The async SQLAlchemy URL.

        Credentials are percent-encoded with an empty safe set, so a password containing ``@``,
        ``/``, or a space survives the round trip instead of silently truncating the host.
        """
        credentials = quote(self.user, safe="")
        if self.password:
            credentials = f"{credentials}:{quote(self.password, safe='')}"
        return (
            f"postgresql+asyncpg://{credentials}@{self.host}:{self.port}"
            f"/{self.database}?ssl={self.ssl}"
        )

    @property
    def safe_url(self) -> str:
        """The URL without the password, for a log line or an error message."""
        return (
            f"postgresql+asyncpg://{quote(self.user, safe='')}@"
            f"{self.host}:{self.port}/{self.database}"
        )

    def connect_arguments(self) -> dict[str, object]:
        """The ``asyncpg`` arguments, passed beside the URL rather than through it."""
        server_settings: dict[str, str] = {"application_name": self.application_name}
        if self.statement_timeout_ms is not None:
            # The server enforces this, so a runaway statement is cancelled by PostgreSQL rather
            # than left holding a pool connection.
            server_settings["statement_timeout"] = str(self.statement_timeout_ms)
        return {"timeout": self.connect_timeout, "server_settings": server_settings}


class PostgresDatabase:
    """Owns one PostgreSQL database's engine, its pool, and its transaction boundaries."""

    def __init__(self, settings: PostgresSettings | None = None) -> None:
        self.settings = PostgresSettings() if settings is None else settings
        self._engine: AsyncEngine | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Return the started engine, or report that the provider was never started."""
        if self._engine is None:
            raise DatabaseConnectionError("the database has not been started")
        return self._engine

    async def start(self) -> None:
        """Create the engine and verify connectivity before anyone is handed the provider."""
        if self._engine is not None:
            return
        engine = create_async_engine(
            self.settings.url,
            echo=self.settings.echo,
            pool_size=self.settings.pool_size,
            max_overflow=self.settings.max_overflow,
            pool_timeout=self.settings.pool_timeout,
            connect_args=self.settings.connect_arguments(),
        )
        self._engine = engine
        try:
            await self.health()
        except BaseException:
            # Including a cancellation: an engine left behind holds a pool the application can no
            # longer reach, and the caller is told the provider never started either way.
            self._engine = None
            await engine.dispose()
            raise

    async def aclose(self) -> None:
        """Release the engine and its pooled connections."""
        engine, self._engine = self._engine, None
        if engine is not None:
            await engine.dispose()

    async def health(self) -> None:
        """Run a trivial query, so readiness reflects real connectivity.

        A refused socket, a name that does not resolve, and a connect that times out are all
        "cannot serve a query", so all three arrive as ``DatabaseConnectionError``: the contract
        says ``health`` raises a ``DatabaseError``, and a caller should not have to catch three
        exception types to find that out.
        """
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError, TimeoutError) as error:
            raise DatabaseConnectionError(
                f"database health check failed for {self.settings.safe_url}: {error}"
            ) from error

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncConnection, None]:
        """Open a short-lived transaction, committing on success and rolling back on error."""
        async with self.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                yield connection
            except BaseException:
                await _rollback_quietly(transaction)
                raise
            try:
                await transaction.commit()
            except SQLAlchemyError as error:
                await _rollback_quietly(transaction)
                raise _transaction_error(error) from error

    async def retrying(
        self,
        operation: TransactionOperation[T],
        *,
        attempts: int | None = None,
        base_delay: float | None = None,
    ) -> T:
        """Retry an idempotent operation while PostgreSQL reports contention.

        The budget is bounded and the delay grows linearly, so a database that stays contended
        fails with ``TransientDatabaseError`` rather than waiting indefinitely. A failure that is
        not one of the two retryable SQLSTATEs is raised unchanged, on the first attempt.
        """
        max_attempts = self.settings.retry_attempts if attempts is None else attempts
        delay = self.settings.retry_base_delay if base_delay is None else base_delay
        for attempt in range(1, max_attempts + 1):
            try:
                async with self.transaction() as connection:
                    return await operation(connection)
            except Exception as error:
                if not _is_retryable(error):
                    raise
                if attempt >= max_attempts:
                    raise TransientDatabaseError(
                        f"the database stayed contended after {max_attempts} attempt(s): {error}"
                    ) from error
                await asyncio.sleep(delay * attempt)
        raise AssertionError("unreachable: the retry loop always returns or raises")


async def open_database(settings: PostgresSettings | None = None) -> PostgresDatabase:
    """Create, start, and return a database the caller owns and closes."""
    database = PostgresDatabase(settings)
    await database.start()
    return database


def postgres_provider(
    settings: PostgresSettings | None = None,
) -> Callable[[], Awaitable[PostgresDatabase]]:
    """Return a zero-argument factory suitable for ``App.provide(..., eager=True)``."""

    async def factory() -> PostgresDatabase:
        return await open_database(settings)

    return factory


async def _rollback_quietly(transaction: AsyncTransaction) -> None:
    try:
        await transaction.rollback()
    except SQLAlchemyError:
        pass


def _transaction_error(error: SQLAlchemyError) -> DatabaseError:
    if _is_retryable(error):
        return TransientDatabaseError(f"the transaction could not commit: {error}")
    return TransactionError(f"the transaction could not commit: {error}")


def _is_retryable(error: BaseException) -> bool:
    """Whether PostgreSQL asked for this failure to be retried.

    ``asyncpg`` puts the SQLSTATE on the driver exception, which SQLAlchemy wraps as ``.orig``, so
    the check reads the original rather than the message, which is localized and reformatted.
    """
    if isinstance(error, TransientDatabaseError):
        return True
    sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
    return sqlstate in _RETRYABLE_SQLSTATES
