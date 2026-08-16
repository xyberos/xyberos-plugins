"""A minimal Discord bot API client (stdlib ``urllib``, injectable transport)."""

from __future__ import annotations

import os
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise ProviderError(f"Discord API returned HTTP {status}: {message[:200]}")


class DiscordClient:
    """Thin client for the Discord bot API (v10)."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = "https://discord.com/api/v10",
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = token if token is not None else os.getenv("DISCORD_TOKEN")
        self._base_url = base_url.rstrip("/")
        self._request = request or default_request
        self._timeout = timeout

    def send_message(self, channel_id: str, content: str) -> dict[str, Any]:
        status, body = self._request(
            "POST",
            f"{self._base_url}/channels/{channel_id}/messages",
            json_body={"content": content},
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return {"id": body.get("id"), "channel_id": body.get("channel_id"), "content": body.get("content")}

    def get_channel(self, channel_id: str) -> dict[str, Any]:
        status, body = self._request(
            "GET",
            f"{self._base_url}/channels/{channel_id}",
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        return {"id": body.get("id"), "name": body.get("name"), "type": body.get("type")}

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise ProviderError("Discord requires a bot token (set DISCORD_TOKEN)")
        return {"Authorization": f"Bot {self._token}"}
