# xyberos-github

**GitHub REST plugin — RFC-0019, M7 (community wave).** User / repository /
issue tools for Xyberos agents, via the GitHub REST API v3. Stdlib-only
(`urllib`) with an injectable transport for tests.

## Install

```bash
pip install -e ./github
```

## Usage

```python
from xyberos import create_app
from xyberos_github import GithubPlugin

app = create_app()
app.load_plugin(GithubPlugin())          # token from GITHUB_TOKEN (optional for public reads)

app.tools.execute("github_get_user", None, username="octocat")
app.tools.execute("github_list_repos", None, username="octocat", per_page=30)
app.tools.execute("github_create_issue", None, owner="o", repo="r", title="Bug", body="...")
```

## Tools

| Tool | Notes |
| ---- | ----- |
| `github_get_user(username)` | public profile |
| `github_list_repos(username, per_page=30)` | public repositories |
| `github_create_issue(owner, repo, title, body="")` | requires `GITHUB_TOKEN` |

## Tests

```bash
pip install pytest
pytest tests/
```

Canned responses via an injectable transport — no network.

## Ship location

Plugin (`xyberos.plugins` entry point) — community wave (M7).
