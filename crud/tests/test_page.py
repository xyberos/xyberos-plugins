"""`fetch_page` against a real database, through the shipped provider double.

`temporary_database()` yields a started SQLite provider over a real temporary file, so the pagination
below is exercised against the database rather than against a mock of one.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select

from xyberos.database import DatabaseProvider, temporary_database
from xyberos_crud import CrudSettings, Filter, PageRequest, Query, Sort, fetch_page

METADATA = MetaData()
ITEMS = Table(
    "items",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(64), nullable=False),
)

FILTERABLE = {"id": ITEMS.c.id, "name": ITEMS.c.name}

#: A maximum of four and a default of two, so both the clamp and the default are reachable.
SETTINGS = CrudSettings(max_limit=4, default_limit=2)


async def populate(database: DatabaseProvider) -> None:
    async with database.transaction() as connection:
        await connection.run_sync(METADATA.create_all)
        for index in range(5):
            await connection.execute(insert(ITEMS).values(name=f"item-{index:02d}"))


def test_a_page_is_bounded_and_reports_whether_another_follows() -> None:
    async def scenario() -> None:
        async with temporary_database() as database:
            await populate(database)
            statement = select(ITEMS).order_by(ITEMS.c.id)

            first = await fetch_page(
                database, statement, Query(), filterable=FILTERABLE, settings=SETTINGS
            )
            assert [row["name"] for row in first.items] == ["item-00", "item-01"]
            assert first.limit == SETTINGS.default_limit
            assert first.has_more is True

            middle = await fetch_page(
                database,
                statement,
                Query(page=PageRequest(limit=2, offset=2)),
                filterable=FILTERABLE,
                settings=SETTINGS,
            )
            assert [row["name"] for row in middle.items] == ["item-02", "item-03"]
            assert middle.has_more is True

            last = await fetch_page(
                database,
                statement,
                Query(page=PageRequest(limit=2, offset=4)),
                filterable=FILTERABLE,
                settings=SETTINGS,
            )
            assert [row["name"] for row in last.items] == ["item-04"]
            assert last.has_more is False

    asyncio.run(scenario())


def test_a_request_cannot_widen_the_page_beyond_the_deployment_maximum() -> None:
    async def scenario() -> None:
        async with temporary_database() as database:
            await populate(database)

            page = await fetch_page(
                database,
                select(ITEMS),
                Query(page=PageRequest(limit=1000)),
                filterable=FILTERABLE,
                settings=SETTINGS,
            )

            assert page.limit == SETTINGS.max_limit
            assert len(page.items) == SETTINGS.max_limit
            assert page.has_more is True

    asyncio.run(scenario())


def test_a_filter_and_a_sort_are_applied_through_the_page() -> None:
    async def scenario() -> None:
        async with temporary_database() as database:
            await populate(database)
            query = Query(
                filters=(Filter(field="name", operator="gte", value="item-02"),),
                sorts=(Sort(field="name", descending=True),),
                page=PageRequest(limit=3),
            )

            page = await fetch_page(
                database, select(ITEMS), query, filterable=FILTERABLE, settings=SETTINGS
            )

            assert [row["name"] for row in page.items] == ["item-04", "item-03", "item-02"]
            assert page.has_more is False

    asyncio.run(scenario())


def test_a_second_page_does_not_repeat_the_first() -> None:
    async def scenario() -> None:
        async with temporary_database() as database:
            await populate(database)

            first = await fetch_page(
                database,
                select(ITEMS),
                Query(page=PageRequest(limit=2, offset=0)),
                filterable=FILTERABLE,
                settings=SETTINGS,
            )
            second = await fetch_page(
                database,
                select(ITEMS),
                Query(page=PageRequest(limit=2, offset=2)),
                filterable=FILTERABLE,
                settings=SETTINGS,
            )

            first_names = {row["name"] for row in first.items}
            second_names = {row["name"] for row in second.items}

            assert not first_names & second_names

    asyncio.run(scenario())
