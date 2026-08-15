"""Authentication strategies for the HTTP/API connector.

Secrets are resolved from environment variables first (``*_env`` fields), then
fall back to literal values. ``api_key``, ``bearer`` and ``basic`` are
stateless; ``oauth2`` (client_credentials) fetches a token from ``token_url``
and caches it for reuse.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .errors import HttpApiError
from .spec import AuthSpec

#: Injectable ``urlopen``-shaped transport for tests (no network needed).
UrlOpen = Callable[..., Any]


def _default_urlopen(request: Any, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


@dataclass
class ResolvedAuth:
    """Headers and query params produced by resolving an auth strategy."""

    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)


class AuthResolver:
    """Resolves an :class:`AuthSpec` into concrete headers/query params."""

    def __init__(
        self,
        auth: AuthSpec,
        *,
        urlopen: UrlOpen | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._auth = auth
        self._urlopen = urlopen or _default_urlopen
        self._timeout = timeout
        self._token: str | None = None
        self._token_url: str | None = None

    def resolve(self) -> ResolvedAuth:
        """Return the auth headers/query for the current request."""
        kind = self._auth.type or "none"
        if kind == "none":
            return ResolvedAuth()
        if kind == "api_key":
            return self._api_key()
        if kind == "bearer":
            return self._bearer()
        if kind == "basic":
            return self._basic()
        if kind == "oauth2":
            return self._oauth2()
        raise HttpApiError(status=None, body=f"unsupported auth type: {kind}")

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _secret(literal: str | None, env: str | None) -> str | None:
        if env:
            value = os.getenv(env)
            if value is not None:
                return value
        return literal

    def _api_key(self) -> ResolvedAuth:
        value = self._secret(self._auth.value, self._auth.env)
        if not value:
            return ResolvedAuth()
        if self._auth.key_in == "query":
            return ResolvedAuth(query={self._auth.key_name: value})
        return ResolvedAuth(headers={self._auth.key_name: value})

    def _bearer(self) -> ResolvedAuth:
        token = self._secret(self._auth.token, self._auth.token_env)
        if not token:
            return ResolvedAuth()
        return ResolvedAuth(headers={"Authorization": f"Bearer {token}"})

    def _basic(self) -> ResolvedAuth:
        username = self._secret(self._auth.username, self._auth.username_env) or ""
        password = self._secret(self._auth.password, self._auth.password_env) or ""
        raw = f"{username}:{password}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return ResolvedAuth(headers={"Authorization": f"Basic {encoded}"})

    def _oauth2(self) -> ResolvedAuth:
        auth = self._auth
        token_url = auth.token_url
        if not token_url:
            raise HttpApiError(status=None, body="oauth2 auth requires a 'token_url'")
        if self._token and self._token_url == token_url:
            return ResolvedAuth(headers={"Authorization": f"Bearer {self._token}"})
        client_id = self._secret(auth.client_id, auth.client_id_env) or ""
        client_secret = self._secret(auth.client_secret, auth.client_secret_env) or ""
        form = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if auth.scope:
            form["scope"] = auth.scope
        data = urllib.parse.urlencode(form).encode("utf-8")
        request = urllib.request.Request(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self._urlopen(request, self._timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise HttpApiError(exc.code, exc.read().decode("utf-8", errors="replace")) from exc
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        token = payload.get("access_token")
        if not token:
            raise HttpApiError(status=None, body="oauth2 token response had no access_token")
        self._token = str(token)
        self._token_url = token_url
        return ResolvedAuth(headers={"Authorization": f"Bearer {self._token}"})
