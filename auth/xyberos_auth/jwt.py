"""JWT encode/decode with HS256 (stdlib) and RS256 (lazy ``cryptography``)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import json
import time
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .errors import AuthError


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


class JwtCodec:
    """Sign and verify JSON Web Tokens (HS256 / RS256)."""

    def __init__(
        self,
        secret: str | None = None,
        *,
        algorithm: str = "HS256",
        private_key: str | None = None,
        public_key: str | None = None,
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm.upper()
        self._private_key = private_key
        self._public_key = public_key
        if self._algorithm not in ("HS256", "RS256"):
            raise AuthError(f"unsupported JWT algorithm: {self._algorithm}")
        if self._algorithm == "HS256" and not secret:
            raise AuthError("HS256 requires a 'secret'")
        if self._algorithm == "RS256" and not (private_key and public_key):
            raise AuthError("RS256 requires both 'private_key' and 'public_key'")

    # -- public API ---------------------------------------------------------

    def encode(self, payload: dict[str, Any], *, ttl: int | None = None) -> str:
        """Return a signed JWT for ``payload`` (optionally with an expiry)."""
        header = {"alg": self._algorithm, "typ": "JWT"}
        claims = dict(payload)
        if ttl is not None:
            now = int(time.time())
            claims.setdefault("iat", now)
            claims.setdefault("exp", now + ttl)
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
            + "."
            + _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
        )
        signature = self._sign(header["alg"], signing_input.encode("utf-8"))
        return f"{signing_input}.{_b64url(signature)}"

    def decode(self, token: str, *, verify: bool = True) -> dict[str, Any]:
        """Decode a JWT; raise :class:`AuthError` on tampering or expiry."""
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthError("invalid JWT: expected three dot-separated parts")
        try:
            header = json.loads(_b64url_decode(parts[0]))
            claims = json.loads(_b64url_decode(parts[1]))
        except (ValueError, json.JSONDecodeError) as exc:
            raise AuthError("invalid JWT: malformed header/claims") from exc
        if verify:
            self._verify(header.get("alg"), f"{parts[0]}.{parts[1]}".encode("utf-8"), parts[2])
            expires = claims.get("exp")
            if isinstance(expires, (int, float)) and time.time() >= expires:
                raise AuthError("JWT has expired")
        return claims

    # -- internals ----------------------------------------------------------

    def _sign(self, alg: str, data: bytes) -> bytes:
        if alg == "HS256":
            return hmac.new(self._secret.encode("utf-8"), data, hashlib.sha256).digest()
        if alg == "RS256":
            return self._rsa_sign(data)
        raise AuthError(f"unsupported JWT algorithm: {alg}")

    def _verify(self, alg: str, data: bytes, signature: str) -> None:
        if alg == "HS256":
            expected = self._sign("HS256", data)
            if not hmac.compare_digest(expected, _b64url_decode(signature)):
                raise AuthError("JWT signature verification failed")
            return
        if alg == "RS256":
            self._rsa_verify(data, _b64url_decode(signature))
            return
        raise AuthError(f"unsupported JWT algorithm: {alg}")

    def _rsa_sign(self, data: bytes) -> bytes:
        primitives, asymmetric, padding, serialization, hashes = self._rsa_modules()
        key = serialization.load_pem_private_key(self._private_key.encode("utf-8"), password=None)
        return key.sign(data, padding.PKCS1v15(), hashes.SHA256())

    def _rsa_verify(self, data: bytes, signature: bytes) -> None:
        primitives, asymmetric, padding, serialization, hashes = self._rsa_modules()
        key = serialization.load_pem_public_key(self._public_key.encode("utf-8"))
        try:
            key.verify(signature, data, padding.PKCS1v15(), hashes.SHA256())
        except Exception as exc:
            raise AuthError("JWT signature verification failed") from exc

    @staticmethod
    def _rsa_modules() -> tuple[Any, Any, Any, Any, Any]:
        """Lazily import the ``cryptography`` modules for RS256 (optional dep)."""
        try:
            primitives = importlib.import_module("cryptography.hazmat.primitives")
            asymmetric = importlib.import_module("cryptography.hazmat.primitives.asymmetric")
        except ImportError as exc:
            raise ProviderError(
                "RS256 requires 'cryptography'; install with "
                "'pip install xyberos-auth[rsa]'"
            ) from exc
        return primitives, asymmetric, asymmetric.padding, primitives.serialization, primitives.hashes
