# xyberos-notion

**Notion API plugin — RFC-0019, M7 (community wave).** Search and create pages
from Xyberos agents via the Notion API v1. Stdlib-only with an injectable
transport for tests.

## Install

```bash
pip install xyberos-notion            # from PyPI

# development (editable, from this repo):
pip install -e ./notion
```

## Usage

```python
from xyberos import create_app
from xyberos_notion import NotionPlugin

app = create_app()
app.load_plugin(NotionPlugin())            # token from NOTION_TOKEN

app.tools.execute("notion_search", None, query="roadmap")
app.tools.execute("notion_create_page", None, database_id="DB_ID", title="New page")
```

## Tools

| Tool | Notes |
| ---- | ----- |
| `notion_search(query="")` | search pages + databases |
| `notion_create_page(database_id, title, title_property="Name")` | create a page in a database |

Requires `NOTION_TOKEN` (an internal integration token).

## Tests

```bash
pip install pytest
pytest tests/
```

Canned responses via an injectable transport — no network.

## Ship location

Plugin (`xyberos.plugins` entry point) — community wave (M7).
