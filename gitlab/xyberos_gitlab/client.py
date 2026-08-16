"""A minimal GitLab REST client (stdlib ``urllib``, injectable transport)."""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise ProviderError(f"GitLab API returned HTTP {status}: {message[:200]}")


class GitlabClient:
    """Thin client for the GitLab REST API v4."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = "https://gitlab.com/api/v4",
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = token if token is not None else os.getenv("GITLAB_TOKEN")
        self._base_url = base_url.rstrip("/")
        self._request = request or default_request
        self._timeout = timeout

    def get_project(self, project: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(project, safe="")
        status, body = self._request(
            "GET",
            f"{self._base_url}/projects/{encoded}",
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return {
            "id": body.get("id"),
            "name": body.get("name"),
            "path_with_namespace": body.get("path_with_namespace"),
            "web_url": body.get("web_url"),
        }

    def list_projects(self, search: str = "", *, per_page: int = 20) -> list[dict[str, Any]]:
        status, body = self._request(
            "GET",
            f"{self._base_url}/projects",
            query={"search": search, "per_page": per_page},
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return [
            {"name": project.get("name"), "path_with_namespace": project.get("path_with_namespace"), "web_url": project.get("web_url")}
            for project in body
        ]

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise ProviderError("GitLab requires a token (set GITLAB_TOKEN)")
        return {"PRIVATE-TOKEN": self._token}
