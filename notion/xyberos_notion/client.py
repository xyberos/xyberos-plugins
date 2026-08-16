"""A minimal Notion API client (stdlib ``urllib``, injectable transport)."""

from __future__ import annotations

import os
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request

NOTION_VERSION = "2022-06-28"


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise ProviderError(f"Notion API returned HTTP {status}: {message[:200]}")


class NotionClient:
    """Thin client for the Notion API v1."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = "https://api.notion.com/v1",
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = token if token is not None else os.getenv("NOTION_TOKEN")
        self._base_url = base_url.rstrip("/")
        self._request = request or default_request
        self._timeout = timeout

    def search(self, query: str = "") -> list[dict[str, Any]]:
        status, body = self._request(
            "POST",
            f"{self._base_url}/search",
            json_body={"query": query},
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return [
            {"id": item.get("id"), "object": item.get("object"), "url": item.get("url")}
            for item in body.get("results", [])
        ]

    def create_page(self, database_id: str, title: str, *, title_property: str = "Name") -> dict[str, Any]:
        status, body = self._request(
            "POST",
            f"{self._base_url}/pages",
            json_body={
                "parent": {"database_id": database_id},
                "properties": {
                    title_property: {"title": [{"text": {"content": title}}]}
                },
            },
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return {"id": body.get("id"), "url": body.get("url")}

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise ProviderError("Notion requires an integration token (set NOTION_TOKEN)")
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": NOTION_VERSION,
        }
