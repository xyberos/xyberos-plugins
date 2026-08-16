"""Tests for loading the Jira plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_jira import JiraPlugin

BASE = "https://your.atlassian.net"


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/rest/api/3/search"):
            return 200, {"issues": [{"key": "PROJ-1", "fields": {"summary": "Fix bug", "status": {"name": "To Do"}}}]}
        return 201, {"id": "1", "key": "PROJ-2"}

    return request


def test_plugin_registers_and_executes():
    app = create_app()
    app.load_plugin(
        JiraPlugin(BASE, email="a@b.com", api_token="tok", request=_fake_request())
    )
    assert "jira_search_issues" in app.tools.names
    assert "jira_create_issue" in app.tools.names

    issues = app.tools.execute("jira_search_issues", None, jql="project = PROJ")
    assert issues[0]["key"] == "PROJ-1"

    app.unload_plugin("jira")
