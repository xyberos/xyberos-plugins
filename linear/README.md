# xyberos-linear

**Linear GraphQL plugin — RFC-0019, M7 (community wave).** Search and create
issues from Xyberos agents via the Linear GraphQL API. Stdlib-only with an
injectable transport for tests.

## Install

```bash
pip install -e ./linear
```

## Usage

```python
from xyberos import create_app
from xyberos_linear import LinearPlugin

app = create_app()
app.load_plugin(LinearPlugin())          # key from LINEAR_API_KEY

app.tools.execute("linear_search_issues", None, query="bug", first=10)
app.tools.execute("linear_create_issue", None, team_id="TEAM_ID", title="New issue", description="...")
```

## Tools

| Tool | Notes |
| ---- | ----- |
| `linear_search_issues(query="", first=10)` | search by title |
| `linear_create_issue(team_id, title, description="")` | create an issue |

Requires `LINEAR_API_KEY` (sent as the `Authorization` header).

## Tests

```bash
pip install pytest
pytest tests/
```

Canned responses via an injectable transport — no network.

## Ship location

Plugin (`xyberos.plugins` entry point) — community wave (M7).
