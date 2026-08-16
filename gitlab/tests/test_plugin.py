"""Tests for loading the GitLab plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_gitlab import GitlabPlugin


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/projects"):
            return 200, [{"name": "repo", "path_with_namespace": "group/repo", "web_url": "https://gitlab.com/group/repo"}]
        return 404, {"message": "not found"}

    return request


def test_plugin_registers_and_executes():
    app = create_app()
    app.load_plugin(GitlabPlugin(token="t", request=_fake_request()))
    assert "gitlab_get_project" in app.tools.names
    assert "gitlab_list_projects" in app.tools.names

    projects = app.tools.execute("gitlab_list_projects", None, search="repo")
    assert projects[0]["name"] == "repo"

    app.unload_plugin("gitlab")
