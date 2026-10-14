"""What reaches the statement, and the evidence that a value is bound rather than written."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Column, Integer, MetaData, Select, String, Table, select

from xyberos.errors import RequestValidationError
from xyberos_crud import CrudSettings, Filter, PageRequest, Query, Sort
from xyberos_crud.statement import apply_query

METADATA = MetaData()
ITEMS = Table(
    "items",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(64), nullable=False),
)

FILTERABLE = {"id": ITEMS.c.id, "name": ITEMS.c.name}


def compiled(statement: Select[Any]) -> str:
    """The SQL as the database would receive it, with placeholders rather than values."""
    return str(statement.compile())


def test_filters_sorts_and_the_page_all_reach_the_statement() -> None:
    query = Query(
        filters=(Filter(field="id", operator="gte", value=10),),
        sorts=(Sort(field="name", descending=True),),
        page=PageRequest(limit=5, offset=2),
    )

    sql = compiled(apply_query(select(ITEMS), query, filterable=FILTERABLE))

    assert "WHERE" in sql
    assert "ORDER BY" in sql
    assert "DESC" in sql
    assert "LIMIT" in sql
    assert "OFFSET" in sql


def test_every_operator_builds_a_condition() -> None:
    for operator, value in (
        ("eq", "a"),
        ("ne", "a"),
        ("lt", 1),
        ("lte", 1),
        ("gt", 1),
        ("gte", 1),
        ("in", ("a", "b")),
        ("contains", "a"),
        ("startswith", "a"),
        ("is_null", True),
    ):
        query = Query(filters=(Filter(field="name", operator=operator, value=value),))

        assert "WHERE" in compiled(apply_query(select(ITEMS), query, filterable=FILTERABLE))


def test_a_hostile_value_is_a_bound_parameter_and_never_sql_text() -> None:
    """The package's whole security posture, in one assertion."""
    hostile = "'; DROP TABLE items; --"
    query = Query(filters=(Filter(field="name", value=hostile),))

    statement = apply_query(select(ITEMS), query, filterable=FILTERABLE)
    sql = compiled(statement)

    assert hostile not in sql, "the value reached the SQL text"
    assert "DROP" not in sql
    assert hostile in statement.compile().params.values(), "the value was not bound at all"


def test_the_limit_is_clamped_for_a_hand_built_query_too() -> None:
    """Clamping at the parse is not enough: a Query assembled in code must be bounded as well."""
    settings = CrudSettings(max_limit=3, default_limit=3)
    query = Query(page=PageRequest(limit=999))

    statement = apply_query(select(ITEMS), query, filterable=FILTERABLE, settings=settings)
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "LIMIT 3" in sql


def test_a_hand_built_query_still_resolves_its_fields_through_the_allowlist() -> None:
    query = Query(filters=(Filter(field="absent"),))

    with pytest.raises(RequestValidationError, match="unknown field 'absent'"):
        apply_query(select(ITEMS), query, filterable=FILTERABLE)


def test_a_disallowed_operator_is_refused_even_when_filter_and_settings_disagree() -> None:
    settings = CrudSettings(allowed_operators=frozenset({"eq"}))
    query = Query(filters=(Filter(field="id", operator="gte", value=1),))

    with pytest.raises(RequestValidationError, match="operator 'gte' is not allowed"):
        apply_query(select(ITEMS), query, filterable=FILTERABLE, settings=settings)


def test_a_value_of_the_wrong_shape_for_its_operator_is_refused() -> None:
    for operator, value, message in (
        ("in", "a,b", "needs a sequence of values"),
        ("contains", 1, "needs text"),
        ("is_null", "true", "needs true or false"),
    ):
        query = Query(filters=(Filter(field="name", operator=operator, value=value),))

        with pytest.raises(RequestValidationError, match=message):
            apply_query(select(ITEMS), query, filterable=FILTERABLE)
