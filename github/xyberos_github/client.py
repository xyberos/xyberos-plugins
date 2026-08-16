"""A minimal GitHub REST client (stdlib ``urllib``, injectable transport)."""

from __future__ import annotations

import os
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise ProviderError(f"GitHub API returned HTTP {status}: {message[:200]}")


class GithubClient:
    """Thin client for the GitHub REST API v3."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = "https://api.github.com",
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = token if token is not None else os.getenv("GITHUB_TOKEN")
        self._base_url = base_url.rstrip("/")
        self._request = request or default_request
        self._timeout = timeout

    # -- users --------------------------------------------------------------

    def get_user(self, username: str) -> dict[str, Any]:
        status, body = self._request(
            "GET",
            f"{self._base_url}/users/{username}",
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return {
            "login": body.get("login"),
            "name": body.get("name"),
            "public_repos": body.get("public_repos"),
            "html_url": body.get("html_url"),
        }

    # -- repositories -------------------------------------------------------

    def list_repos(self, username: str, *, per_page: int = 30) -> list[dict[str, Any]]:
        status, body = self._request(
            "GET",
            f"{self._base_url}/users/{username}/repos",
            query={"per_page": per_page},
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return [
            {"full_name": repo.get("full_name"), "html_url": repo.get("html_url"), "language": repo.get("language")}
            for repo in body
        ]

    # -- issues -------------------------------------------------------------

    def create_issue(self, owner: str, repo: str, title: str, body: str = "") -> dict[str, Any]:
        self._require_auth("create_issue")
        status, body_ = self._request(
            "POST",
            f"{self._base_url}/repos/{owner}/{repo}/issues",
            json_body={"title": title, "body": body},
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body_)
        return {"number": body_.get("number"), "html_url": body_.get("html_url"), "state": body_.get("state")}

    # -- internals ----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "xyberos-github"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _require_auth(self, action: str) -> None:
        if not self._token:
            raise ProviderError(
                f"GitHub '{action}' requires a token (set GITHUB_TOKEN)"
            )
