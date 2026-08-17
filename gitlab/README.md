# xyberos-gitlab

**GitLab REST plugin — RFC-0019, M7 (community wave).** Project tools for
Xyberos agents via the GitLab REST API v4. Stdlib-only with an injectable
transport for tests.

## Install

```bash
pip install xyberos-gitlab            # from PyPI

# development (editable, from this repo):
pip install -e ./gitlab
```

## Usage

```python
from xyberos import create_app
from xyberos_gitlab import GitlabPlugin

app = create_app()
app.load_plugin(GitlabPlugin())            # token from GITLAB_TOKEN

app.tools.execute("gitlab_get_project", None, project="group/repo")
app.tools.execute("gitlab_list_projects", None, search="xyberos", per_page=20)
```

## Tools

| Tool | Notes |
| ---- | ----- |
| `gitlab_get_project(project)` | project by id or URL-encoded path |
| `gitlab_list_projects(search="", per_page=20)` | search projects |

Requires `GITLAB_TOKEN`.

## Tests

```bash
pip install pytest
pytest tests/
```

Canned responses via an injectable transport — no network.

## Ship location

Plugin (`xyberos.plugins` entry point) — community wave (M7).
