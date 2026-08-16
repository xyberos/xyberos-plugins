"""Tests for the Linear GraphQL client (injectable transport, no network)."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_linear import LinearClient


def _fake_request():
    def request(method, url, **kwargs):
        body = kwargs.get("json_body", {})
        if "issueCreate" in body.get("query", ""):
            return 200, {"data": {"issueCreate": {"success": True, "issue": {"id": "i1", "url": "https://linear.app/x/ISSUE-1"}}}}
        return 200, {"data": {"issues": {"nodes": [{"id": "i1", "identifier": "TEAM-1", "title": "Fix bug", "url": "https://linear.app/x/TEAM-1"}]}}}

    return request


def test_search_issues():
    request = _fake_request()
    client = LinearClient(api_key="k", request=request)
    issues = client.search_issues("bug", first=5)
    assert issues == [{"id": "i1", "identifier": "TEAM-1", "title": "Fix bug", "url": "https://linear.app/x/TEAM-1"}]


def test_create_issue():
    request = _fake_request()
    client = LinearClient(api_key="k", request=request)
    result = client.create_issue("team1", "New issue", "details")
    assert result == {"id": "i1", "url": "https://linear.app/x/ISSUE-1", "success": True}


def test_requires_api_key():
    request = _fake_request()
    client = LinearClient(api_key=None, request=request)
    with pytest.raises(ProviderError, match="LINEAR_API_KEY"):
        client.search_issues()


def test_graphql_error_raises():
    def request(method, url, **kwargs):
        return 200, {"errors": [{"message": "Unauthorized"}]}

    client = LinearClient(api_key="k", request=request)
    with pytest.raises(ProviderError, match="Unauthorized"):
        client.search_issues()
