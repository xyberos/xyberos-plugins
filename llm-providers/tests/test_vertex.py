"""Tests for the Vertex AI adapter (injectable token + transport)."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_llm_providers import VertexAILlm


def test_vertex_generate():
    seen: list[tuple] = []

    def post(url: str, payload: dict, headers: dict) -> dict:
        seen.append((url, payload, headers))
        return {"candidates": [{"content": {"parts": [{"text": "stub response"}]}}]}

    llm = VertexAILlm(
        "gemini-1.5-flash",
        project="my-project",
        location="us-central1",
        token_provider=lambda: "tok123",
        post=post,
    )
    assert llm.generate("hi") == "stub response"
    url, payload, headers = seen[0]
    assert "projects/my-project" in url
    assert "models/gemini-1.5-flash:generateContent" in url
    assert headers["Authorization"] == "Bearer tok123"
    assert payload["contents"][0]["parts"][0]["text"] == "hi"


def test_vertex_requires_project(monkeypatch):
    monkeypatch.delenv("VERTEX_AI_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    llm = VertexAILlm(project=None, token_provider=lambda: "tok")
    with pytest.raises(ProviderError, match="project"):
        llm.generate("hi")
