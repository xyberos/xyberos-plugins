# xyberos-jira

**Jira Cloud REST API plugin — RFC-0019, M7 (community wave).** Search and
create issues from Xyberos agents. Stdlib-only with an injectable transport for
tests.

## Install

```bash
pip install -e ./jira
```

## Usage

```python
from xyberos import create_app
from xyberos_jira import JiraPlugin

app = create_app()
app.load_plugin(JiraPlugin())      # JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN

app.tools.execute("jira_search_issues", None, jql="project = PROJ", max_results=50)
app.tools.execute("jira_create_issue", None, project_key="PROJ", summary="New bug", description="...")
```

## Tools

| Tool | Notes |
| ---- | ----- |
| `jira_search_issues(jql, max_results=50)` | JQL search |
| `jira_create_issue(project_key, summary, description="", issuetype="Task")` | create an issue |

Requires `JIRA_BASE_URL` (e.g. `https://your.atlassian.net`), `JIRA_EMAIL` and
`JIRA_API_TOKEN` (basic auth).

## Tests

```bash
pip install pytest
pytest tests/
```

Canned responses via an injectable transport — no network.

## Ship location

Plugin (`xyberos.plugins` entry point) — community wave (M7).
