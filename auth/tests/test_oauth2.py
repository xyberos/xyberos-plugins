"""Tests for the OAuth2 client."""

from __future__ import annotations

import pytest

from xyberos_auth import OAuth2Client
from xyberos_auth.errors import AuthError


def _token_response():
    return {"access_token": "at", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "rt"}


def test_authorization_url():
    client = OAuth2Client("cid", "csecret", authorize_url="https://idp/authorize", token_url="https://idp/token", scope="openid")
    url = client.authorization_url("state-1")
    assert url.startswith("https://idp/authorize?")
    assert "client_id=cid" in url
    assert "state=state-1" in url
    assert "response_type=code" in url
    assert "scope=openid" in url


def test_exchange_code():
    captured = {}

    def request(method, url, **kwargs):
        captured.update(kwargs)
        return 200, _token_response()

    client = OAuth2Client("cid", "csecret", token_url="https://idp/token", request=request)
    result = client.exchange_code("the-code", redirect_uri="https://app/cb")
    assert result["access_token"] == "at"
    assert captured["form"]["grant_type"] == "authorization_code"
    assert captured["form"]["code"] == "the-code"
    assert captured["form"]["client_id"] == "cid"
    assert captured["form"]["client_secret"] == "csecret"


def test_refresh_and_client_credentials():
    captured = []

    def request(method, url, **kwargs):
        captured.append(kwargs["form"])
        return 200, _token_response()

    client = OAuth2Client("cid", "csecret", token_url="https://idp/token", request=request)
    client.refresh("refresh-tok")
    client.client_credentials(scope="api")
    assert captured[0]["grant_type"] == "refresh_token"
    assert captured[1]["grant_type"] == "client_credentials"
    assert captured[1]["scope"] == "api"


def test_token_error_raises():
    def request(method, url, **kwargs):
        return 400, {"error": "invalid_grant"}

    client = OAuth2Client("cid", "csecret", token_url="https://idp/token", request=request)
    with pytest.raises(AuthError, match="400"):
        client.exchange_code("bad")
