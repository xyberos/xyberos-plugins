"""Tests for the AWS Bedrock adapter (injectable client; no boto3 needed)."""

from __future__ import annotations

import importlib.util

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_llm_providers import BedrockLLM


class _FakeConverseClient:
    """A minimal stand-in for a boto3 ``bedrock-runtime`` client."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def converse(self, **kwargs: dict) -> dict:
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": "bedrock says hi"}]}}}


def test_bedrock_generate_with_injected_client():
    client = _FakeConverseClient()
    llm = BedrockLLM("anthropic.claude-x", client=client)
    assert llm.generate("hi") == "bedrock says hi"
    assert client.calls[0]["modelId"] == "anthropic.claude-x"
    assert client.calls[0]["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]


def test_bedrock_requires_sdk():
    if importlib.util.find_spec("boto3"):
        pytest.skip("boto3 is installed")
    llm = BedrockLLM(client=None)
    with pytest.raises(ProviderError, match="boto3"):
        llm.generate("hi")
