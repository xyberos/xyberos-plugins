"""A minimal Slack Web API client (stdlib ``urllib``, injectable transport)."""

from __future__ import annotations

import os
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request


def _raise_for_status(status: int, body: Any) -> None:
    if 200 <= status < 300:
        return
    message = body if isinstance(body, str) else str(body)
    raise ProviderError(f"Slack API returned HTTP {status}: {message[:200]}")


class SlackClient:
    """Thin client for the Slack Web API."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = "https://slack.com/api",
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = token if token is not None else os.getenv("SLACK_TOKEN")
        self._base_url = base_url.rstrip("/")
        self._request = request or default_request
        self._timeout = timeout

    def post_message(self, channel: str, text: str) -> dict[str, Any]:
        status, body = self._request(
            "POST",
            f"{self._base_url}/chat.postMessage",
            json_body={"channel": channel, "text": text},
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        self._check_ok(body, "post_message")
        return {"ok": True, "channel": body.get("channel"), "ts": body.get("ts")}

    def list_channels(self, limit: int = 100) -> list[dict[str, Any]]:
        status, body = self._request(
            "GET",
            f"{self._base_url}/conversations.list",
            query={"types": "public_channel", "limit": limit},
            headers=self._headers(),
            timeout=self._timeout,
        )
        _raise_for_status(status, body)
        self._check_ok(body, "list_channels")
        return [{"id": channel.get("id"), "name": channel.get("name")} for channel in body.get("channels", [])]

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise ProviderError("Slack requires a token (set SLACK_TOKEN)")
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def _check_ok(body: Any, action: str) -> None:
        if isinstance(body, dict) and body.get("ok") is False:
            raise ProviderError(f"Slack '{action}' failed: {body.get('error')}")
