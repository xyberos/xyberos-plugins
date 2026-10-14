"""Tests for the OpenAI-compatible provider preset registry."""

from __future__ import annotations

import pytest

from xyberos_llm_providers import PRESETS, get_llm, list_presets


def test_presets_are_complete():
    names = set(list_presets())
    assert {"openai", "mistral", "groq", "deepseek", "cohere", "together", "xai"} <= names
    for name in names:
        preset = PRESETS[name]
        assert preset.name == name
        assert preset.base_url and preset.default_model and preset.api_key_env


def test_get_llm_is_openai_compatible(fake_post):
    post, seen = fake_post
    llm = get_llm("groq", api_key="k", post=post)
    assert llm.generate("hello") == "stub response"
    url, payload, headers = seen[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert payload["model"] == "llama-3.3-70b-versatile"
    assert payload["messages"][0]["content"] == "hello"
    assert headers["Authorization"] == "Bearer k"


def test_api_key_from_env(monkeypatch, fake_post):
    post, seen = fake_post
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    get_llm("deepseek", post=post).generate("hi")
    assert seen[0][2]["Authorization"] == "Bearer secret"


def test_custom_model_overrides_preset(fake_post):
    post, seen = fake_post
    get_llm("mistral", api_key="k", model="mistral-large-latest", post=post).generate("hi")
    assert seen[0][1]["model"] == "mistral-large-latest"


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="unknown LLM provider"):
        get_llm("bogus")


def test_azure_is_not_a_preset():
    with pytest.raises(ValueError, match="azure_openai"):
        get_llm("azure_openai")
