"""The page a query returns, and the one function that fetches it.

:func:`fetch_page` is the only member of this package that touches a database, and it does so through
the contract: it opens ``provider.transaction()``, executes a statement the caller already built, and
lets the transaction close before it returns. It never wraps the provider, so the caller keeps owning
the pool and every write boundary around it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Column, Select

from xyberos.database import DatabaseProvider

from xyberos_crud.query import Query
from xyberos_crud.settings import CrudSettings
from xyberos_crud.statement import apply_query


@dataclass(frozen=True)
class Page:
    """One page of rows, and what a caller needs to ask for the next one.

    There is no total. ``has_more`` is a fact about the page that was fetched; a count of everything
    else would be a second query, whose answer a concurrent write can already have invalidated by the
    time it is rendered.
    """

    items: tuple[Mapping[str, Any], ...]
    limit: int
    offset: int
    has_more: bool


async def fetch_page(
    provider: DatabaseProvider,
    statement: Select[Any],
    query: Query,
    *,
    filterable: Mapping[str, Column[Any]],
    settings: CrudSettings | None = None,
) -> Page:
    """Fetch one page of ``statement`` and report whether another one follows.

    The page is found by asking the database for one row more than the page holds: a row coming back
    means ``has_more`` is true, and it is dropped rather than returned. That is the whole reason
    there is no total count — a count is a second query, and it is a lie under concurrent writes.

    ``provider`` is used, not wrapped: the transaction is opened and closed here, so a caller that
    needs a write to share it composes ``apply_query`` with its own ``provider.transaction()``
    instead.
    """
    resolved = CrudSettings() if settings is None else settings
    limit, offset = query.page.resolved(resolved)
    probe = apply_query(statement, query, filterable=filterable, settings=resolved).limit(limit + 1)
    async with provider.transaction() as connection:
        rows = (await connection.execute(probe)).mappings().all()
    return Page(
        items=tuple(dict(row) for row in rows[:limit]),
        limit=limit,
        offset=offset,
        has_more=len(rows) > limit,
    )
