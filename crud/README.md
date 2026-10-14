# xyberos-crud

**Filtering, sorting, and pagination for a collection endpoint — over the database provider contract, as
values rather than entities.**

A service depends on `DatabaseProvider`, and a collection route usually needs the same three things: the
caller's filters, the caller's sort order, and one page of rows. `xyberos-crud` describes all three as
values, applies them to a SQLAlchemy Core `select()`, and fetches the page — so the query string is parsed
once, in one place, and no field name reaches SQL as text.

It is **not an ORM**, and that is deliberate
([ADR 0023](https://github.com/xyberos/xyberos2.0/blob/master/docs/adr/0023-crud-package-and-the-dx-refusals.md)).
It does not map rows to objects, does not own identity or a session, and does not wrap `DatabaseProvider`:
a service still opens its own transaction.

## Install

```bash
pip install xyberos-crud
```

## Use it

```python
from sqlalchemy import MetaData, Table, Column, Integer, String, select

from xyberos.database import DatabaseProvider
from xyberos_crud import CrudSettings, Query, fetch_page

metadata = MetaData()
orders = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("status", String(32), nullable=False),
)

# The allowlist. A field name that is not a key here cannot be filtered on, sorted by, or named at all.
FILTERABLE = {"status": orders.c.status, "id": orders.c.id}

SETTINGS = CrudSettings(max_limit=100, default_limit=25)


async def list_orders(provider: DatabaseProvider, parameters: dict[str, str]) -> dict[str, object]:
    query = Query.from_parameters(
        parameters, filterable=FILTERABLE, settings=SETTINGS
    )
    statement = select(orders)
    page = await fetch_page(
        provider, statement, query, filterable=FILTERABLE, settings=SETTINGS
    )
    return {
        "items": [dict(row) for row in page.items],
        "limit": page.limit,
        "offset": page.offset,
        "has_more": page.has_more,
    }
```

`from_parameters` takes a mapping rather than a `Request`, so the package needs no HTTP dependency: pass
`dict(request.query_params)`, or build the mapping from anything else you like.

## The query string

| Parameter | Meaning |
| --- | --- |
| `status=open` | equality |
| `id__gte=10` | the operator named after the double underscore |
| `status__in=open,pending` | a comma-separated list |
| `name__contains=ada`, `name__startswith=a` | text matching |
| `deleted_at__is_null=true` | null, or not null with `false` |
| `sort=-created_at,name` | descending, then ascending |
| `limit=25`, `offset=50` | the page; `limit` is clamped to `max_limit` |

The operators are `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `contains`, `startswith`, and `is_null`.
Which of them a deployment allows is `CrudSettings.allowed_operators`.

## What it does not do

- **No total count.** `has_more` is a fact about the page that was fetched. A total is a second query, and
  a concurrent write can invalidate it before it is rendered. If you need one, run it yourself.
- **No keyset pagination.** This is `LIMIT`/`OFFSET`, which is what an internal tool wants and what drifts
  under concurrent writes on a large table. A keyset cursor is a different query shape, and it is not here.
- **No writes.** It builds and runs one `SELECT`. Insert, update, and delete are your service's, inside
  your service's transaction.
- **No ORM, no entity mapping, no identity.** It takes a table and returns a statement, so it can answer a
  query without knowing what a row *means*.
- **No raw SQL.** There is no escape hatch, because the moment one exists a field name can reach the
  database as text.
