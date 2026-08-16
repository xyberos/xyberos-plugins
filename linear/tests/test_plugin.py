"""Tests for loading the Linear plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_linear import LinearPlugin


def _fake_request():
    def request(method, url, **kwargs):
        return 200, {"data": {"issues": {"nodes": [{"id": "i1", "identifier": "TEAM-1", "title": "Fix bug", "url": "https://linear.app/x/TEAM-1"}]}}}

    return request


def test_plugin_registers_and_executes():
    app = create_app()
    app.load_plugin(LinearPlugin(api_key="k", request=_fake_request()))
    assert "linear_search_issues" in app.tools.names
    assert "linear_create_issue" in app.tools.names

    issues = app.tools.execute("linear_search_issues", None, query="bug")
    assert issues[0]["identifier"] == "TEAM-1"

    app.unload_plugin("linear")
