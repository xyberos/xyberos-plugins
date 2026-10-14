"""The values one collection query is described by, and the parse from a query string.

A :class:`Query` is a filter set, a sort list, and a page request — values, not entities. It can be
built, compared, and logged without a database, and it is applied to a statement later, by
:func:`~xyberos_crud.statement.apply_query`.

:meth:`Query.from_parameters` reads a query string the caller has already reduced to a mapping, which
is why this package needs no HTTP dependency: pass ``dict(request.query_params)`` and the request
body never matters. ``field=value`` is equality, ``field__gte=30`` is the operator named after the
double underscore, ``sort=-created_at,name`` is descending then ascending, and ``limit`` and
``offset`` are reserved names rather than fields.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Column

from xyberos.errors import RequestValidationError

from xyberos_crud.settings import EQ, IN, IS_NULL, CrudSettings


@dataclass(frozen=True)
class Filter:
    """One field, one operator, and the value to bind to it."""

    field: str
    operator: str = EQ
    value: object = None


@dataclass(frozen=True)
class Sort:
    """One ordering: a field name and whether it descends."""

    field: str
    descending: bool = False


@dataclass(frozen=True)
class PageRequest:
    """How much of a result set to take, and how far into it to start.

    ``limit`` of ``None`` means "whatever the settings default to". The ceiling is applied by
    :func:`~xyberos_crud.statement.apply_query` as well, so a request can never widen it.
    """

    limit: int | None = None
    offset: int = 0

    def __post_init__(self) -> None:
        if self.limit is not None and self.limit < 0:
            raise RequestValidationError(f"limit must not be negative, got {self.limit}")
        if self.offset < 0:
            raise RequestValidationError(f"offset must not be negative, got {self.offset}")

    def resolved(self, settings: CrudSettings) -> tuple[int, int]:
        """The effective ``(limit, offset)``: the settings default when missing, and never above
        ``settings.max_limit``."""
        limit = settings.default_limit if self.limit is None else self.limit
        return min(limit, settings.max_limit), self.offset


@dataclass(frozen=True)
class Query:
    """Filters, sorts, and a page: the whole description of a collection query."""

    filters: tuple[Filter, ...] = ()
    sorts: tuple[Sort, ...] = ()
    page: PageRequest = PageRequest()

    @classmethod
    def from_parameters(
        cls,
        parameters: Mapping[str, str],
        *,
        filterable: Mapping[str, Column[Any]],
        settings: CrudSettings | None = None,
    ) -> Query:
        """Build a query from a query string the caller already parsed into a mapping.

        Every field name is resolved through ``filterable`` and every operator through
        ``settings.allowed_operators``, so a name that reaches the values here is one the caller
        listed and one the deployment allows. ``limit`` is clamped to ``settings.max_limit`` and a
        missing one becomes ``settings.default_limit``, because the parse is the first place both
        are known.
        """
        resolved = CrudSettings() if settings is None else settings
        filters: list[Filter] = []
        sorts: list[Sort] = []
        requested_limit: int | None = None
        requested_offset = 0
        for name, raw in parameters.items():
            if name == "sort":
                sorts.extend(_parse_sorts(raw, filterable))
            elif name == "limit":
                requested_limit = _parse_non_negative(name, raw)
            elif name == "offset":
                requested_offset = _parse_non_negative(name, raw)
            else:
                field, separator, operator = name.partition("__")
                operator_name = operator if separator else EQ
                resolve_column(filterable, field)
                check_operator(resolved, operator_name, field=field)
                filters.append(
                    Filter(
                        field=field,
                        operator=operator_name,
                        value=_parse_value(field, operator_name, raw),
                    )
                )
        limit, offset = PageRequest(limit=requested_limit, offset=requested_offset).resolved(
            resolved
        )
        return cls(
            filters=tuple(filters),
            sorts=tuple(sorts),
            page=PageRequest(limit=limit, offset=offset),
        )


def resolve_column(filterable: Mapping[str, Column[Any]], field: str) -> Column[Any]:
    """Return the column ``field`` names, or refuse the name.

    The mapping is the whole allowlist. The name is looked up as a key: it is never turned into SQL,
    never read off a table with ``getattr``, and never interpolated. A name that is not a key is
    refused with the names that are, which is what makes "the caller's mapping decides which columns
    may be filtered" a fact rather than a promise.
    """
    try:
        return filterable[field]
    except KeyError:
        allowed = ", ".join(sorted(filterable)) if filterable else "none"
        raise RequestValidationError(
            f"unknown field {field!r}; allowed fields are: {allowed}"
        ) from None


def check_operator(settings: CrudSettings, operator: str, *, field: str) -> None:
    """Refuse an operator the settings do not allow, naming the ones they do."""
    if operator not in settings.allowed_operators:
        allowed = ", ".join(sorted(settings.allowed_operators)) or "none"
        raise RequestValidationError(
            f"operator {operator!r} is not allowed for field {field!r}; "
            f"allowed operators are: {allowed}"
        )


def _parse_sorts(raw: str, filterable: Mapping[str, Column[Any]]) -> tuple[Sort, ...]:
    sorts: list[Sort] = []
    for item in raw.split(","):
        name = item.strip()
        descending = name.startswith("-")
        field = name[1:] if descending else name
        if not field:
            raise RequestValidationError(
                f"sort needs field names, got {raw!r}; write '-field' to descend"
            )
        resolve_column(filterable, field)
        sorts.append(Sort(field=field, descending=descending))
    return tuple(sorts)


def _parse_value(field: str, operator: str, raw: str) -> object:
    if operator == IN:
        values = tuple(part for part in raw.split(",") if part != "")
        if not values:
            raise RequestValidationError(
                f"filter {field!r} with {IN!r} needs at least one comma-separated value"
            )
        return values
    if operator == IS_NULL:
        lowered = raw.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        raise RequestValidationError(
            f"filter {field!r} with {IS_NULL!r} needs true or false, not {raw!r}"
        )
    return raw


def _parse_non_negative(name: str, raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise RequestValidationError(f"{name} must be an integer, got {raw!r}") from None
    if value < 0:
        raise RequestValidationError(f"{name} must not be negative, got {value}")
    return value
