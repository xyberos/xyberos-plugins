"""Langfuse exporter — pushes events to the Langfuse ingestion API (stdlib HTTP).

Each event becomes one ``observation-create`` batch item. The transport is
injectable so tests run without a network; the exporter also records what it
has sent for inspection.
"""

from __future__ import annotations

import base64
import os
import time
import uuid
from typing import Any

from xyberos.events import Event
from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request


class LangfuseExporter:
    """Sends each Xyberos event to Langfuse's ``/api/public/ingestion``."""

    def __init__(
        self,
        public_key: str | None = None,
        secret_key: str | None = None,
        *,
        host: str | None = None,
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._public_key = public_key if public_key is not None else os.getenv("LANGFUSE_PUBLIC_KEY")
        self._secret_key = secret_key if secret_key is not None else os.getenv("LANGFUSE_SECRET_KEY")
        self._host = (host or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com").rstrip("/")
        self._request = request or default_request
        self._timeout = timeout
        self.sent: list[dict[str, Any]] = []
        self._last_status: int | None = None

    @property
    def count(self) -> int:
        return len(self.sent)

    def export(self, event: Event) -> None:
        if not (self._public_key and self._secret_key):
            raise ProviderError(
                "Langfuse requires LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"
            )
        prompt = getattr(event.context, "prompt", None)
        payload: dict[str, Any] = {
            "batch": [
                {
                    "id": uuid.uuid4().hex,
                    "type": "observation-create",
                    "timestamp": time.time() * 1000,
                    "name": event.name,
                    "input": str(prompt) if prompt else None,
                    "output": dict(event.data or {}),
                }
            ]
        }
        credentials = base64.b64encode(f"{self._public_key}:{self._secret_key}".encode()).decode("ascii")
        status, _body = self._request(
            "POST",
            f"{self._host}/api/public/ingestion",
            json_body=payload,
            headers={"Authorization": f"Basic {credentials}"},
            timeout=self._timeout,
        )
        self._last_status = status
        self.sent.append(payload)

    def __call__(self, event: Event) -> None:
        self.export(event)
