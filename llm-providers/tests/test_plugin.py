"""Tests for loading the llm_providers plugin into a Xyberos app."""

from __future__ import annotations

import pytest
from xyberos import create_app

from xyberos_llm_providers import LlmProvidersPlugin


def test_plugin_conforms_to_contract():
    plugin = LlmProvidersPlugin()
    assert plugin.name == "llm_providers"
    assert callable(plugin.register) and callable(plugin.unregister)


def test_unconfigured_register_is_safe():
    app = create_app()
    app.load_plugin(LlmProvidersPlugin())  # no provider, no env -> no-op
    assert app.plugins.names == ("llm_providers",)
    app.unload_plugin("llm_providers")


def test_plugin_registers_llm_by_name(fake_post):
    post, _ = fake_post
    app = create_app()
    app.load_plugin(LlmProvidersPlugin(provider="groq", api_key="k", post=post))
    assert app.llm.generate("hi") == "stub response"
    app.unload_plugin("llm_providers")


def test_plugin_llm_from_env(monkeypatch, fake_post):
    post, _ = fake_post
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    app = create_app()
    app.load_plugin(LlmProvidersPlugin(post=post))
    assert app.llm.generate("hi") == "stub response"
    app.unload_plugin("llm_providers")


def test_plugin_unknown_provider_is_skipped(fake_post):
    post, _ = fake_post
    from xyberos.llm import EchoLLM

    app = create_app()
    # register() is a safe no-op for a bad provider (logs a warning).
    app.load_plugin(LlmProvidersPlugin(provider="bogus", post=post))
    assert isinstance(app.llm, EchoLLM)  # default provider untouched
    # Calling llm() directly surfaces the error.
    with pytest.raises(ValueError, match="unknown LLM provider"):
        LlmProvidersPlugin(provider="bogus").llm()
    app.unload_plugin("llm_providers")
