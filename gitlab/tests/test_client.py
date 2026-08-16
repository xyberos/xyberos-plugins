"""Tests for the GitLab REST client (injectable transport, no network)."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_gitlab import GitlabClient


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/projects/group%2Frepo"):
            return 200, {"id": 1, "name": "repo", "path_with_namespace": "group/repo", "web_url": "https://gitlab.com/group/repo"}
        if url.endswith("/projects"):
            return 200, [{"name": "repo", "path_with_namespace": "group/repo", "web_url": "https://gitlab.com/group/repo"}]
        return 404, {"message": "not found"}

    return request


def test_get_project_encodes_path():
    request = _fake_request()
    client = GitlabClient(token="t", request=request)
    result = client.get_project("group/repo")
    assert result["path_with_namespace"] == "group/repo"
    assert result["web_url"] == "https://gitlab.com/group/repo"


def test_list_projects():
    request = _fake_request()
    client = GitlabClient(token="t", request=request)
    projects = client.list_projects("repo", per_page=5)
    assert projects[0]["name"] == "repo"


def test_requires_token():
    request = _fake_request()
    client = GitlabClient(token=None, request=request)
    with pytest.raises(ProviderError, match="token"):
        client.get_project("g/r")
