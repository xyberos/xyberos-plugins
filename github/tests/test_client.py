"""Tests for the GitHub REST client (injectable transport, no network)."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_github import GithubClient


def _fake_request():
    calls: list[tuple[str, str, dict]] = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/users/octocat"):
            return 200, {
                "login": "octocat", "name": "The Octocat",
                "public_repos": 8, "html_url": "https://github.com/octocat",
            }
        if url.endswith("/users/octocat/repos"):
            return 200, [
                {"full_name": "octocat/Hello-World", "html_url": "https://github.com/octocat/Hello-World", "language": "Ruby"}
            ]
        if url.endswith("/repos/octocat/Hello-World/issues"):
            return 201, {"number": 1, "html_url": "https://github.com/octocat/Hello-World/issues/1", "state": "open"}
        return 404, {"message": "not found"}

    return request, calls


def test_get_user():
    request, calls = _fake_request()
    client = GithubClient(token="t", request=request)
    result = client.get_user("octocat")
    assert result == {
        "login": "octocat", "name": "The Octocat",
        "public_repos": 8, "html_url": "https://github.com/octocat",
    }
    assert calls[0][0] == "GET"


def test_list_repos_sends_query():
    request, calls = _fake_request()
    client = GithubClient(token="t", request=request)
    repos = client.list_repos("octocat", per_page=5)
    assert repos[0]["full_name"] == "octocat/Hello-World"
    assert calls[0][2]["query"] == {"per_page": 5}


def test_create_issue_sends_bearer():
    request, calls = _fake_request()
    client = GithubClient(token="secret", request=request)
    result = client.create_issue("octocat", "Hello-World", "Bug", "Details")
    assert result["number"] == 1
    assert calls[0][2]["headers"]["Authorization"] == "Bearer secret"
    assert calls[0][2]["json_body"] == {"title": "Bug", "body": "Details"}


def test_create_issue_requires_token():
    request, _ = _fake_request()
    client = GithubClient(token=None, request=request)
    with pytest.raises(ProviderError, match="token"):
        client.create_issue("o", "r", "Bug")


def test_http_error_raises():
    def request(method, url, **kwargs):
        return 401, {"message": "Bad credentials"}

    client = GithubClient(token="t", request=request)
    with pytest.raises(ProviderError, match="401"):
        client.get_user("octocat")
