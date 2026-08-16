"""OpenID Connect client (discovery, userinfo, id_token verification)."""

from __future__ import annotations

from typing import Any

from .errors import AuthError
from .http import RequestTransport, default_request
from .jwt import JwtCodec


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise AuthError(f"OIDC endpoint returned HTTP {status}: {message[:200]}")


class OidcClient:
    """A minimal OpenID Connect client (discovery + userinfo)."""

    def __init__(
        self,
        issuer: str,
        *,
        client_id: str = "",
        client_secret: str | None = None,
        request: RequestTransport | None = None,
        timeout: float = 30.0,
        codec: JwtCodec | None = None,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._request = request or default_request
        self._timeout = timeout
        self._codec = codec
        self._metadata: dict[str, Any] | None = None

    def discovery(self, *, refresh: bool = False) -> dict[str, Any]:
        """Fetch and cache the OpenID configuration."""
        if self._metadata is not None and not refresh:
            return self._metadata
        status, body = self._request(
            "GET",
            f"{self._issuer}/.well-known/openid-configuration",
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        if not isinstance(body, dict):
            raise AuthError("OIDC discovery returned a non-object response")
        self._metadata = body
        return body

    def userinfo(self, access_token: str) -> dict[str, Any]:
        """Fetch the userinfo endpoint with ``access_token``."""
        metadata = self.discovery()
        endpoint = metadata.get("userinfo_endpoint")
        if not endpoint:
            raise AuthError("OIDC discovery did not advertise a userinfo_endpoint")
        status, body = self._request(
            "GET",
            endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return dict(body)

    def verify_id_token(self, id_token: str) -> dict[str, Any]:
        """Decode and verify an ``id_token`` (HS256 via client_secret)."""
        if self._codec is not None:
            return self._codec.decode(id_token, verify=True)
        if not self._client_secret:
            raise AuthError(
                "cannot verify id_token: no client_secret (HS256) or codec configured"
            )
        codec = JwtCodec(self._client_secret)
        claims = codec.decode(id_token, verify=True)
        audience = claims.get("aud")
        if self._client_id and audience not in (self._client_id, [self._client_id]):
            raise AuthError(f"id_token audience mismatch: {audience}")
        return claims
