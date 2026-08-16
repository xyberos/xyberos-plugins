"""Tests for the JWT codec."""

from __future__ import annotations

import importlib.util

import pytest

from xyberos_auth import JwtCodec
from xyberos_auth.errors import AuthError


def test_hs256_roundtrip():
    codec = JwtCodec("secret")
    token = codec.encode({"sub": "user-1", "role": "admin"})
    claims = codec.decode(token)
    assert claims["sub"] == "user-1"
    assert claims["role"] == "admin"


def test_hs256_ttl():
    codec = JwtCodec("secret")
    token = codec.encode({"sub": "u"}, ttl=3600)
    claims = codec.decode(token)
    assert claims["exp"] - claims["iat"] == 3600


def test_hs256_tamper_detected():
    codec = JwtCodec("secret")
    token = codec.encode({"sub": "u"})
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(AuthError, match="signature"):
        codec.decode(tampered)


def test_hs256_wrong_secret():
    token = JwtCodec("secret-a").encode({"sub": "u"})
    with pytest.raises(AuthError, match="signature"):
        JwtCodec("secret-b").decode(token)


def test_requires_secret():
    with pytest.raises(AuthError, match="secret"):
        JwtCodec(algorithm="HS256")


@pytest.mark.skipif(importlib.util.find_spec("cryptography") is None, reason="cryptography not installed")
def test_rs256_roundtrip():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("utf-8")
    )
    codec = JwtCodec(algorithm="RS256", private_key=private_pem, public_key=public_pem)
    token = codec.encode({"sub": "u"})
    assert codec.decode(token)["sub"] == "u"
