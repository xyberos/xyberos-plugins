"""AWS Bedrock adapter (RFC-0019, M6).

A thin :class:`~xyberos.contracts.LLMProvider` over the Bedrock Runtime
``converse`` API. ``boto3`` is imported lazily and a clear
:class:`~xyberos.exceptions.provider.ProviderError` is raised when it is
missing. A ``client`` may be injected for tests.
"""

from __future__ import annotations

import importlib
import os
from typing import Any

from xyberos.exceptions.provider import ProviderError


def _require_boto3() -> Any:
    try:
        boto3 = importlib.import_module("boto3")
    except ImportError as exc:
        raise ProviderError(
            "the 'boto3' package is required for AWS Bedrock; install it with "
            "'pip install xyberos[llm-providers]'"
        ) from exc
    return boto3


class BedrockLLM:
    """Generate text via the AWS Bedrock Runtime ``converse`` API."""

    def __init__(
        self,
        model_id: str | None = None,
        *,
        region: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._model_id = model_id or os.getenv("BEDROCK_MODEL_ID") or "anthropic.claude-3-5-sonnet-20240620-v1:0"
        self._region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        self._client = client

    def generate(self, prompt: str) -> str:
        client = self._get_client()
        response = client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
        )
        output = response.get("output", {})
        message = output.get("message", {})
        parts = message.get("content", [])
        text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        if not text:
            raise ProviderError(f"Bedrock returned no text for model {self._model_id}")
        return text

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        boto3 = _require_boto3()
        kwargs: dict[str, Any] = {"service_name": "bedrock-runtime"}
        if self._region:
            kwargs["region_name"] = self._region
        self._client = boto3.client(**kwargs)
        return self._client
