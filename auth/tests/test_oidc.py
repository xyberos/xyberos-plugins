"""Tests for the OIDC client and presets."""

from __future__ import annotations

import pytest

from xyberos_auth import OidcClient, build_oidc, get_preset
from xyberos_auth.errors import AuthError
from xyberos_auth.jwt import JwtCodec


def _discovery_body():
    return {
        "issuer": "https://idp.example.com",
        "userinfo_endpoint": "https://idp.example.com/userinfo",
        "authorization_endpoint": "https://idp.example.com/authorize",
    }


def test_discovery_and_userinfo():
    def request(method, url, **kwargs):
        if url.endswith("/.well-known/openid-configuration"):
            return 200, _discovery_body()
        if url.endswith("/userinfo"):
            return 200, {"sub": "user-1", "email": "a@b.com"}
        return 404, {}

    client = OidcClient("https://idp.example.com", request=request)
    metadata = client.discovery()
    assert metadata["userinfo_endpoint"] == "https://idp.example.com/userinfo"
    user = client.userinfo("at")
    assert user["email"] == "a@b.com"


def test_verify_id_token_hs256():
    codec = JwtCodec("client-secret")
    token = codec.encode({"sub": "u", "aud": "app-id"})
    client = OidcClient("https://idp", client_id="app-id", client_secret="client-secret")
    claims = client.verify_id_token(token)
    assert claims["sub"] == "u"


def test_verify_id_token_audience_mismatch():
    codec = JwtCodec("client-secret")
    token = codec.encode({"sub": "u", "aud": "other-app"})
    client = OidcClient("https://idp", client_id="app-id", client_secret="client-secret")
    with pytest.raises(AuthError, match="audience"):
        client.verify_id_token(token)


def test_presets():
    assert get_preset("auth0", tenant="myco") == "https://myco.auth0.com"
    assert get_preset("okta", org="myorg") == "https://myorg.okta.com/oauth2/default"
    assert get_preset("entra", tenant="mytenant") == "https://login.microsoftonline.com/mytenant/v2.0"


def test_preset_requires_tenant():
    with pytest.raises(ValueError, match="tenant"):
        get_preset("auth0")


def test_unknown_preset():
    with pytest.raises(ValueError, match="unknown OIDC preset"):
        get_preset("bogus")


def test_build_oidc():
    client = build_oidc("auth0", client_id="cid", client_secret="s", tenant="myco")
    assert isinstance(client, OidcClient)
