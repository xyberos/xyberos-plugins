"""Google Vertex AI adapter (RFC-0019, M6).

A thin :class:`~xyberos.contracts.LLMProvider` over the Vertex AI
``generateContent`` REST API using a Google access token. ``google.auth`` is
imported lazily to obtain the token; the HTTP POST uses stdlib ``urllib``.
Both the token provider and the transport are injectable for tests.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable

from xyberos.exceptions.provider import ProviderError

#: (url, payload, headers) -> parsed JSON body
PostCallable = Callable[[str, dict[str, Any], dict[str, Any]], Any]
#: () -> access token
TokenProvider = Callable[[], str]


def _default_token() -> str:
    try:
        import google.auth
        import google.auth.transport.requests
    except ImportError as exc:
        raise ProviderError(
            "the 'google-auth' package is required for Vertex AI; install it with "
            "'pip install xyberos[llm-providers]'"
        ) from exc
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return str(credentials.token)


def _default_post(url: str, payload: dict[str, Any], headers: dict[str, Any], *, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class VertexAILlm:
    """Generate text via the Vertex AI ``generateContent`` REST API."""

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        *,
        project: str | None = None,
        location: str = "us-central1",
        token_provider: TokenProvider | None = None,
        post: PostCallable | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._model = model
        self._project = project or os.getenv("VERTEX_AI_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        self._location = location
        self._token_provider = token_provider or _default_token
        self._timeout = timeout
        self._post = post or (lambda url, payload, headers: _default_post(url, payload, headers, timeout=timeout))

    def generate(self, prompt: str) -> str:
        if not self._project:
            raise ProviderError(
                "Vertex AI requires a project (VERTEX_AI_PROJECT / GOOGLE_CLOUD_PROJECT)"
            )
        token = self._token_provider()
        url = (
            f"https://{self._location}-aiplatform.googleapis.com/v1/projects/"
            f"{self._project}/locations/{self._location}/publishers/google/"
            f"models/{self._model}:generateContent"
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        data = self._post(url, payload, headers)
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Vertex AI returned an unexpected response: {data}") from exc
        return "".join(str(part.get("text", "")) for part in parts)
