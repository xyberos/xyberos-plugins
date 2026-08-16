"""A minimal Linear GraphQL client (stdlib ``urllib``, injectable transport)."""

from __future__ import annotations

import json
import os
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise ProviderError(f"Linear API returned HTTP {status}: {message[:200]}")


class LinearClient:
    """Thin client for the Linear GraphQL API."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.linear.app/graphql",
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("LINEAR_API_KEY")
        self._base_url = base_url
        self._request = request or default_request
        self._timeout = timeout

    def search_issues(self, query: str = "", *, first: int = 10) -> list[dict[str, Any]]:
        filter_clause = f'filter: {{title: {{contains: {json.dumps(query)}}}}}, ' if query else ""
        graphql = f"{{ issues({filter_clause}first: {first}) {{ nodes {{ id identifier title url }} }} }}"
        data = self._graphql(graphql)
        return [
            {"id": node.get("id"), "identifier": node.get("identifier"), "title": node.get("title"), "url": node.get("url")}
            for node in data.get("issues", {}).get("nodes", [])
        ]

    def create_issue(self, team_id: str, title: str, description: str = "") -> dict[str, Any]:
        graphql = (
            "mutation { issueCreate(input: {"
            f'teamId: {json.dumps(team_id)}, title: {json.dumps(title)}, description: {json.dumps(description)}'
            "}) { success issue { id url } } }"
        )
        data = self._graphql(graphql)
        created = data.get("issueCreate", {})
        issue = created.get("issue") or {}
        return {"id": issue.get("id"), "url": issue.get("url"), "success": created.get("success")}

    def _graphql(self, query: str) -> dict[str, Any]:
        if not self._api_key:
            raise ProviderError("Linear requires an API key (set LINEAR_API_KEY)")
        status, body = self._request(
            "POST",
            self._base_url,
            json_body={"query": query},
            headers={"Authorization": self._api_key},
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        if body.get("errors"):
            raise ProviderError(f"Linear GraphQL error: {body['errors']}")
        return body.get("data") or {}
