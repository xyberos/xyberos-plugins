"""Tests for the Jira REST client (injectable transport, no network)."""

from __future__ import annotations

import base64

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_jira import JiraClient

BASE = "https://your.atlassian.net"


def _fake_request():
    def request(method, url, **kwargs):
        if url.endswith("/rest/api/3/search"):
            return 200, {
                "issues": [
                    {"key": "PROJ-1", "fields": {"summary": "Fix bug", "status": {"name": "To Do"}}}
                ]
            }
        if url.endswith("/rest/api/3/issue"):
            return 201, {"id": "10001", "key": "PROJ-2"}
        return 404, {"errorMessages": ["Not found"]}

    return request


def test_search_issues():
    request = _fake_request()
    client = JiraClient(BASE, email="a@b.com", api_token="tok", request=request)
    issues = client.search_issues("project = PROJ")
    assert issues == [
        {"key": "PROJ-1", "summary": "Fix bug", "status": "To Do", "url": f"{BASE}/browse/PROJ-1"}
    ]


def test_create_issue():
    request = _fake_request()
    client = JiraClient(BASE, email="a@b.com", api_token="tok", request=request)
    result = client.create_issue("PROJ", "New bug", "details", "Bug")
    assert result == {"id": "10001", "key": "PROJ-2", "url": f"{BASE}/browse/PROJ-2"}


def test_basic_auth_header():
    captured = {}

    def capturing(method, url, **kwargs):
        captured.update(kwargs)
        return 200, {"issues": []}

    JiraClient(BASE, email="a@b.com", api_token="tok", request=capturing).search_issues("x")
    expected = "Basic " + base64.b64encode(b"a@b.com:tok").decode("ascii")
    assert captured["headers"]["Authorization"] == expected


def test_requires_credentials():
    request = _fake_request()
    client = JiraClient(BASE, email=None, api_token=None, request=request)
    with pytest.raises(ProviderError, match="JIRA_EMAIL"):
        client.search_issues("x")


def test_requires_base_url():
    request = _fake_request()
    client = JiraClient(None, email="a@b.com", api_token="tok", request=request)
    with pytest.raises(ProviderError, match="JIRA_BASE_URL"):
        client.search_issues("x")
