"""A minimal Jira Cloud REST API client (stdlib, injectable transport)."""

from __future__ import annotations

import base64
import os
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise ProviderError(f"Jira API returned HTTP {status}: {message[:200]}")


class JiraClient:
    """Thin client for the Jira Cloud REST API v3."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        email: str | None = None,
        api_token: str | None = None,
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = (base_url or os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        self._email = email if email is not None else os.getenv("JIRA_EMAIL")
        self._api_token = api_token if api_token is not None else os.getenv("JIRA_API_TOKEN")
        self._request = request or default_request
        self._timeout = timeout

    def search_issues(self, jql: str, *, max_results: int = 50) -> list[dict[str, Any]]:
        status, body = self._request(
            "GET",
            f"{self._base_url}/rest/api/3/search",
            query={"jql": jql, "maxResults": max_results},
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return [
            {
                "key": issue.get("key"),
                "summary": (issue.get("fields") or {}).get("summary"),
                "status": ((issue.get("fields") or {}).get("status") or {}).get("name"),
                "url": f"{self._base_url}/browse/{issue.get('key')}",
            }
            for issue in body.get("issues", [])
        ]

    def create_issue(self, project_key: str, summary: str, description: str = "", issuetype: str = "Task") -> dict[str, Any]:
        status, body = self._request(
            "POST",
            f"{self._base_url}/rest/api/3/issue",
            json_body={
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary,
                    "description": description,
                    "issuetype": {"name": issuetype},
                }
            },
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return {"id": body.get("id"), "key": body.get("key"), "url": f"{self._base_url}/browse/{body.get('key')}"}

    def _headers(self) -> dict[str, str]:
        if not self._base_url:
            raise ProviderError("Jira requires a base URL (set JIRA_BASE_URL)")
        if not self._email or not self._api_token:
            raise ProviderError("Jira requires an email + API token (set JIRA_EMAIL, JIRA_API_TOKEN)")
        raw = f"{self._email}:{self._api_token}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
