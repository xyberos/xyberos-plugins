"""OAuth 2.0 client (authorization code, client credentials, refresh)."""

from __future__ import annotations

import urllib.parse
from typing import Any

from .errors import AuthError
from .http import RequestTransport, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise AuthError(f"OAuth endpoint returned HTTP {status}: {message[:200]}")


class OAuth2Client:
    """A minimal OAuth 2.0 client with injectable transport."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        authorize_url: str = "",
        token_url: str,
        redirect_uri: str | None = None,
        scope: str = "",
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._authorize_url = authorize_url
        self._token_url = token_url
        self._redirect_uri = redirect_uri
        self._scope = scope
        self._request = request or default_request
        self._timeout = timeout

    def authorization_url(self, state: str, *, redirect_uri: str | None = None) -> str:
        """Build the authorization-code consent URL."""
        if not self._authorize_url:
            raise AuthError("authorize_url is not configured")
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "state": state,
            "redirect_uri": redirect_uri or self._redirect_uri or "",
            "scope": self._scope,
        }
        separator = "&" if "?" in self._authorize_url else "?"
        return self._authorize_url + separator + urllib.parse.urlencode(
            {key: value for key, value in params.items() if value}
        )

    def exchange_code(self, code: str, *, redirect_uri: str | None = None) -> dict[str, Any]:
        """Exchange an authorization code for tokens."""
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri or self._redirect_uri or "",
            }
        )

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an access token."""
        return self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    def client_credentials(self, scope: str | None = None) -> dict[str, Any]:
        """Request a token with the client_credentials grant."""
        form = {"grant_type": "client_credentials"}
        if scope:
            form["scope"] = scope
        return self._token_request(form)

    # -- internals ----------------------------------------------------------

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        form.setdefault("client_id", self._client_id)
        form.setdefault("client_secret", self._client_secret)
        status, body = self._request(
            "POST",
            self._token_url,
            form=form,
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        if not isinstance(body, dict) or "access_token" not in body:
            raise AuthError(f"token endpoint returned an unexpected response: {body}")
        return body
