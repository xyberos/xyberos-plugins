"""The Database contract (RFC-0020): connect -> inspect -> query -> result."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Database(Protocol):
    """A DB-agnostic connection that returns structured results.

    ``query`` returns a list of row dicts (column name -> value) so every
    backend — SQL, document, or graph — speaks one shape.
    """

    name: str

    def connect(self) -> None:
        """Open the connection."""

    def list_tables(self) -> list[str]:
        """Return the schema's table names."""

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """Execute ``sql`` and return rows as dicts."""

    def close(self) -> None:
        """Release the connection."""
