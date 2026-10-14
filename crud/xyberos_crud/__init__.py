"""CRUD query construction over the ``DatabaseProvider`` contract.

Filtering, sorting, and pagination for a collection endpoint, expressed as values and applied to a
SQLAlchemy Core ``select()``:

    from sqlalchemy import select

    from xyberos_crud import Query, apply_query

    filterable = {"status": orders.c.status, "created_at": orders.c.created_at}
    query = Query.from_parameters(dict(request.query_params), filterable=filterable)
    statement = apply_query(select(orders), query, filterable=filterable)

What it does not do is why it is values rather than an ORM: it does not map rows to objects, does not
own identity, and does not wrap ``DatabaseProvider`` — a service still opens its own transaction. It
takes a statement and returns a statement; what a row means is the caller's business.

Field names are resolved only through the ``filterable`` mapping the caller supplies, operators only
through ``CrudSettings.allowed_operators``, and values are always bound parameters, so there is no
path from a query string to SQL text.
"""

from xyberos_crud.page import Page, fetch_page
from xyberos_crud.query import Filter, PageRequest, Query, Sort
from xyberos_crud.settings import CrudSettings
from xyberos_crud.statement import apply_query

__all__ = [
    "CrudSettings",
    "Filter",
    "Page",
    "PageRequest",
    "Query",
    "Sort",
    "apply_query",
    "fetch_page",
]
