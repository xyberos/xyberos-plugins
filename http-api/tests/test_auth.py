"""Tests for auth resolution against the local HTTP server."""

from __future__ import annotations

from xyberos_http_api import AuthSpec
from xyberos_http_api.auth import AuthResolver


def test_no_auth():
    assert AuthResolver(AuthSpec()).resolve().headers == {}


def test_api_key_header(monkeypatch):
    resolver = AuthResolver(AuthSpec(type="api_key", key_name="X-API-Key", value="secret123"))
    resolved = resolver.resolve()
    assert resolved.headers == {"X-API-Key": "secret123"}
    assert resolved.query == {}


def test_api_key_query():
    resolved = AuthResolver(
        AuthSpec(type="api_key", key_name="apikey", key_in="query", value="abc")
    ).resolve()
    assert resolved.query == {"apikey": "abc"}


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("MY_KEY", "env-value")
    resolved = AuthResolver(
        AuthSpec(type="api_key", key_name="X-Key", env="MY_KEY", value="literal")
    ).resolve()
    assert resolved.headers == {"X-Key": "env-value"}


def test_bearer():
    resolved = AuthResolver(AuthSpec(type="bearer", token="tok123")).resolve()
    assert resolved.headers == {"Authorization": "Bearer tok123"}


def test_basic():
    resolved = AuthResolver(
        AuthSpec(type="basic", username="user", password="pass")
    ).resolve()
    import base64

    expected = "Basic " + base64.b64encode(b"user:pass").decode("ascii")
    assert resolved.headers == {"Authorization": expected}


def test_oauth2_client_credentials(server):
    base_url, requests = server
    auth = AuthSpec(
        type="oauth2",
        token_url=f"{base_url}/token",
        client_id="cid",
        client_secret="csecret",
        scope="read",
    )
    resolver = AuthResolver(auth)
    first = resolver.resolve()
    second = resolver.resolve()
    assert first.headers == {"Authorization": "Bearer tok123"}
    # Token is cached — only one token request is made.
    token_calls = [r for r in requests if r["path"] == "/token"]
    assert len(token_calls) == 1
    assert second.headers == first.headers
