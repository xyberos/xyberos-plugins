"""Tests for loading the GitHub plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_github import GithubPlugin


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/users/octocat"):
            return 200, {"login": "octocat", "public_repos": 8, "html_url": "https://github.com/octocat"}
        return 404, {"message": "not found"}

    return request


def test_plugin_conforms_to_contract():
    plugin = GithubPlugin()
    assert plugin.name == "github"
    assert callable(plugin.register) and callable(plugin.unregister)


def test_plugin_registers_and_executes():
    app = create_app()
    app.load_plugin(GithubPlugin(token="t", request=_fake_request()))
    assert "github_get_user" in app.tools.names
    assert "github_list_repos" in app.tools.names
    assert "github_create_issue" in app.tools.names

    result = app.tools.execute("github_get_user", None, username="octocat")
    assert result["login"] == "octocat"

    app.unload_plugin("github")
    assert "github_get_user" not in app.tools.names
