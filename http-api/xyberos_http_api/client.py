"""Minimal dependency-free HTTP client used by generated operation tools.

Uses only the standard library (``urllib``), applies the declared auth, merges
the declared headers, and optionally throttles calls with the core's
:class:`~xyberos.utils.resilience.RateLimiter`. The ``urlopen`` transport is
injectable so tests can run without a network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from xyberos.utils.resilience import RateLimiter

from .auth import AuthResolver, ResolvedAuth, UrlOpen
from .errors import HttpApiError
from .spec import AuthSpec, RateLimitSpec

#: Injectable ``urlopen``-shaped transport (defaults to the stdlib opener).
UrlOpenCallable = Callable[..., Any]


def _default_urlopen(request: Any, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


class HttpClient:
    """A tiny typed-over-JSON HTTP client for one API base URL."""

    def __init__(
        self,
        base_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        auth: AuthSpec | None = None,
        rate_limit: RateLimitSpec | None = None,
        timeout: float = 30.0,
        urlopen: UrlOpen | None = None,
    ) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._headers = dict(headers or {})
        self._auth_resolver = AuthResolver(auth, urlopen=urlopen, timeout=timeout) if auth else None
        self._timeout = timeout
        self._urlopen = urlopen or _default_urlopen
        self._limiter: RateLimiter | None = None
        if rate_limit is not None:
            self._limiter = RateLimiter(
                calls_per_second=rate_limit.calls_per_second,
                burst=rate_limit.burst,
            )

    @property
    def base_url(self) -> str:
        return self._base_url

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Send one request and return the decoded body (JSON dict/list or text)."""
        resolved = self._auth_resolver.resolve() if self._auth_resolver else ResolvedAuth()

        url = self._base_url + (path or "/")
        query_params = dict(resolved.query)
        query_params.update({k: v for k, v in (query or {}).items() if v is not None})
        if query_params:
            separator = "&" if "?" in url else "?"
            url += separator + urllib.parse.urlencode(query_params)

        request_headers = dict(self._headers)
        request_headers.update(resolved.headers)
        request_headers.update(headers or {})

        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        if self._limiter is not None:
            self._limiter.acquire()

        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with self._urlopen(request, self._timeout) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()

        text = raw.decode("utf-8", errors="replace") if raw else ""
        if not 200 <= status < 300:
            raise HttpApiError(status, text)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    # -- convenience verbs --------------------------------------------------

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)
