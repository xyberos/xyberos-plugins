"""Apply a :class:`~xyberos_crud.query.Query` to a SQLAlchemy Core statement.

Every field name a query carries is resolved through the caller's ``filterable`` mapping, and every
value becomes a bound parameter. Operators are dispatched here to SQLAlchemy's own constructs, so
this module never builds SQL text — which is why the package has no raw-SQL escape hatch to offer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import Column, ColumnElement, Select

from xyberos.errors import RequestValidationError

from xyberos_crud.query import Query, check_operator, resolve_column
from xyberos_crud.settings import (
    CONTAINS,
    EQ,
    GTE,
    GT,
    IN,
    IS_NULL,
    LTE,
    LT,
    NE,
    STARTSWITH,
    CrudSettings,
)


def apply_query(
    statement: Select[Any],
    query: Query,
    *,
    filterable: Mapping[str, Column[Any]],
    settings: CrudSettings | None = None,
) -> Select[Any]:
    """Return ``statement`` with the query's filters, sorts, and page applied.

    Filters are ANDed, sorts are applied in the order given, and the page becomes ``LIMIT`` and
    ``OFFSET``. The limit is the request's, or the settings default when the request was silent, and
    it is clamped to ``settings.max_limit`` here as well as where a request is parsed: a query
    assembled by hand cannot ask for more than the deployment allows either.
    """
    resolved = CrudSettings() if settings is None else settings
    for item in query.filters:
        column = resolve_column(filterable, item.field)
        check_operator(resolved, item.operator, field=item.field)
        statement = statement.where(_condition(item.field, column, item.operator, item.value))
    for ordering in query.sorts:
        column = resolve_column(filterable, ordering.field)
        statement = statement.order_by(column.desc() if ordering.descending else column.asc())
    limit, offset = query.page.resolved(resolved)
    return statement.limit(limit).offset(offset)


def _condition(
    field: str, column: Column[Any], operator: str, value: object
) -> ColumnElement[bool]:
    """The WHERE clause one filter means, built from SQLAlchemy constructs so values bind."""
    if operator == EQ:
        return column == value
    if operator == NE:
        return column != value
    if operator == LT:
        return column < value
    if operator == LTE:
        return column <= value
    if operator == GT:
        return column > value
    if operator == GTE:
        return column >= value
    if operator == IN:
        return column.in_(_values(field, value))
    if operator == CONTAINS:
        return column.contains(_text(field, operator, value))
    if operator == STARTSWITH:
        return column.startswith(_text(field, operator, value))
    if operator == IS_NULL:
        return column.is_(None) if _flag(field, value) else column.is_not(None)
    raise RequestValidationError(f"unknown operator {operator!r} for field {field!r}")


def _values(field: str, value: object) -> Sequence[object]:
    """The sequence an ``in`` filter needs, or a refusal naming what arrived instead."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise RequestValidationError(
            f"filter {field!r} with {IN!r} needs a sequence of values, not {type(value).__name__}"
        )
    # `isinstance(value, Sequence)` narrows to `Sequence[Unknown]`, and the elements are bound as
    # parameters rather than read here, so the element type is stated rather than inferred.
    return cast("Sequence[object]", value)


def _text(field: str, operator: str, value: object) -> str:
    """The text ``contains`` and ``startswith`` need, or a refusal naming what arrived instead."""
    if isinstance(value, str):
        return value
    raise RequestValidationError(
        f"filter {field!r} with {operator!r} needs text, not {type(value).__name__}"
    )


def _flag(field: str, value: object) -> bool:
    """The flag an ``is_null`` filter needs, or a refusal naming what arrived instead."""
    if isinstance(value, bool):
        return value
    raise RequestValidationError(
        f"filter {field!r} with {IS_NULL!r} needs true or false, not {type(value).__name__}"
    )
