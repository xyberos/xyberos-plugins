"""Tests for the Azure OpenAI adapter."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_llm_providers import AzureOpenAILLM


def test_azure_generate(fake_post):
    post, seen = fake_post
    llm = AzureOpenAILLM(
        "my-deploy",
        endpoint="https://res.openai.azure.com",
        api_key="azkey",
        post=post,
    )
    assert llm.generate("hi") == "stub response"
    url, payload, headers = seen[0]
    assert url == (
        "https://res.openai.azure.com/openai/deployments/my-deploy/"
        "chat/completions?api-version=2024-06-01"
    )
    assert headers["api-key"] == "azkey"
    assert payload["messages"][0]["content"] == "hi"


def test_azure_requires_endpoint(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    llm = AzureOpenAILLM("d")
    with pytest.raises(ProviderError, match="endpoint"):
        llm.generate("hi")


def test_azure_requires_api_key(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    llm = AzureOpenAILLM("d", endpoint="https://res.openai.azure.com", api_key=None)
    with pytest.raises(ProviderError, match="API key"):
        llm.generate("hi")
