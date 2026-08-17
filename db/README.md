# xyberos-db

**Database plugin — RFC-0019/0020, M9.** The DB-agnostic `Database` contract
(`connect → list_tables → query → close`) with a stdlib SQLite reference plus
lazy Postgres / MySQL / DuckDB drivers.

## Install

```bash
pip install xyberos-db              # from PyPI
pip install xyberos-db[postgres]   # optional drivers
pip install xyberos-db[mysql]
pip install xyberos-db[duckdb]

# development (editable, from this repo):
pip install -e ./db
```

## Usage

```python
from xyberos import create_app
from xyberos_db import DbPlugin

app = create_app()
app.load_plugin(DbPlugin(backend="sqlite"))        # in-memory
# app.load_plugin(DbPlugin(dsn="postgres://user:pass@host/db"))

app.tools.execute("db_list_tables", None)
rows = app.tools.execute("db_query", None, sql="SELECT id, name FROM users")
```

`dsn` auto-detects the backend (`postgres://` / `mysql://` / `duckdb://` /
anything else → SQLite path). Returns rows as `list[dict]`.

## Direct use

```python
from xyberos_db import SqliteDatabase

db = SqliteDatabase("app.db")
db.connect()
print(db.list_tables())
print(db.query("SELECT 1 AS one"))
db.close()
```

## RFC

The contract is specified in [`RFC-0020-database-plugin-contract.md`](../RFC-0020-database-plugin-contract.md)
(the M9 "Core additive RFC").

## Tests

```bash
pip install pytest
pytest tests/
```

SQLite is fully tested; driver adapters skip when their driver is absent.

## Ship location

Plugin (`xyberos.plugins` entry point) + RFC-0020 contract — enterprise DBs (M9).
