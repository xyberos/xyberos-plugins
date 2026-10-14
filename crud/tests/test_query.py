"""Parsing a query string, and every name or value that must be refused."""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.types import DateTime

from xyberos.errors import RequestValidationError
from xyberos_crud import CrudSettings, Filter, PageRequest, Query, Sort

METADATA = MetaData()
ITEMS = Table(
    "items",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(64), nullable=False),
    Column("created_at", DateTime(), nullable=True),
)

#: The caller's allowlist, which is the whole of what may be named in a query string.
FILTERABLE = {"id": ITEMS.c.id, "name": ITEMS.c.name, "created_at": ITEMS.c.created_at}

SETTINGS = CrudSettings(max_limit=10, default_limit=3)


def parse(parameters: dict[str, str]) -> Query:
    return Query.from_parameters(parameters, filterable=FILTERABLE, settings=SETTINGS)


def test_a_bare_field_is_equality() -> None:
    query = parse({"name": "ada"})

    assert query.filters == (Filter(field="name", operator="eq", value="ada"),)


@pytest.mark.parametrize("operator", ["ne", "lt", "lte", "gt", "gte"])
def test_the_double_underscore_names_the_operator(operator: str) -> None:
    query = parse({f"id__{operator}": "7"})

    assert query.filters == (Filter(field="id", operator=operator, value="7"),)


def test_in_takes_a_list_and_is_null_takes_a_flag() -> None:
    query = parse({"name__in": "ada,grace", "created_at__is_null": "true"})

    assert query.filters == (
        Filter(field="name", operator="in", value=("ada", "grace")),
        Filter(field="created_at", operator="is_null", value=True),
    )


def test_a_sort_list_is_ordered_and_directed() -> None:
    query = parse({"sort": "-created_at,name"})

    assert query.sorts == (
        Sort(field="created_at", descending=True),
        Sort(field="name", descending=False),
    )


def test_a_missing_limit_becomes_the_default_and_a_large_one_is_clamped() -> None:
    assert parse({}).page.limit == SETTINGS.default_limit
    assert parse({"limit": "1000"}).page.limit == SETTINGS.max_limit
    assert parse({"offset": "5"}).page.offset == 5


def test_a_reserved_parameter_is_not_a_field() -> None:
    """`limit` and `offset` name the page, so neither may be filtered on."""
    query = parse({"limit": "2", "offset": "1"})

    assert query.filters == ()
    assert query.page == PageRequest(limit=2, offset=1)


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"absent": "1"}, "unknown field 'absent'"),
        ({"name__regexp": "a.*"}, "operator 'regexp' is not allowed"),
        ({"name__in": ","}, "needs at least one comma-separated value"),
        ({"created_at__is_null": "maybe"}, "needs true or false"),
        ({"limit": "abc"}, "limit must be an integer"),
        ({"limit": "-1"}, "limit must not be negative"),
        ({"offset": "-1"}, "offset must not be negative"),
        ({"sort": "-"}, "sort needs field names"),
    ],
)
def test_a_bad_parameter_is_a_client_error(parameters: dict[str, str], message: str) -> None:
    with pytest.raises(RequestValidationError, match=message):
        parse(parameters)


def test_a_field_name_that_looks_like_sql_is_only_ever_a_key() -> None:
    """Each half of a parameter name is looked up in a vocabulary, so neither can be anything else."""
    with pytest.raises(RequestValidationError, match="unknown field"):
        parse({"name; DROP TABLE items; --": "1"})

    with pytest.raises(RequestValidationError, match="unknown field"):
        parse({"sort": "name; DROP TABLE items; --"})

    # The half after `__` is an operator name, checked against the same closed vocabulary.
    with pytest.raises(RequestValidationError, match="is not allowed"):
        parse({"name__contains; DROP TABLE items; --": "1"})


def test_a_narrowed_vocabulary_is_enforced_where_the_request_is_read() -> None:
    settings = CrudSettings(allowed_operators=frozenset({"eq"}))

    with pytest.raises(RequestValidationError, match="operator 'gte' is not allowed"):
        Query.from_parameters({"id__gte": "1"}, filterable=FILTERABLE, settings=settings)


def test_a_page_request_refuses_its_own_bad_values() -> None:
    with pytest.raises(RequestValidationError, match="limit must not be negative"):
        PageRequest(limit=-1)

    with pytest.raises(RequestValidationError, match="offset must not be negative"):
        PageRequest(offset=-1)
