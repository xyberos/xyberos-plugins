"""Azure OpenAI adapter (RFC-0019, M6).

Azure OpenAI is OpenAI-compatible but not identical: it posts to
``{endpoint}/openai/deployments/{deployment}/chat/completions?api-version=...``
and authenticates with an ``api-key`` header (not ``Bearer``). This thin
adapter implements exactly that; the transport is injectable for tests.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from .presets import PostCallable
from xyberos.exceptions.provider import ProviderError


def _default_post(url: str, payload: dict[str, Any], headers: dict[str, Any], *, timeout: float) -> Any:
    import json
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class AzureOpenAILLM:
    """Azure OpenAI chat-completions adapter (lazy, injectable transport)."""

    def __init__(
        self,
        deployment: str,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str = "2024-06-01",
        timeout: float = 60.0,
        post: PostCallable | None = None,
    ) -> None:
        self._deployment = deployment
        self._endpoint = (endpoint or os.getenv("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
        self._api_key = api_key if api_key is not None else os.getenv("AZURE_OPENAI_API_KEY")
        self._api_version = api_version
        self._timeout = timeout
        self._post = post or (lambda url, payload, headers: _default_post(url, payload, headers, timeout=timeout))

    def generate(self, prompt: str) -> str:
        if not self._endpoint:
            raise ProviderError("Azure OpenAI requires an endpoint (AZURE_OPENAI_ENDPOINT)")
        if not self._api_key:
            raise ProviderError("Azure OpenAI requires an API key (AZURE_OPENAI_API_KEY)")
        url = (
            f"{self._endpoint}/openai/deployments/{self._deployment}/chat/completions"
            f"?api-version={self._api_version}"
        )
        headers = {"Content-Type": "application/json", "api-key": self._api_key}
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
        }
        data = self._post(url, payload, headers)
        return data["choices"][0]["message"]["content"]
