"""Provider preset registry (RFC-0019, M6).

Most of the remaining providers are OpenAI-compatible — they differ only by
``base_url``, model name and API key environment variable. The registry turns
them into one line: ``get_llm("groq")`` -> a configured
:class:`~xyberos.llm.OpenAICompatibleLLM`. No new adapter per provider.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from xyberos.llm import LLMProvider, OpenAICompatibleLLM

#: (method, url, payload, headers) -> parsed JSON body (same shape as the core).
PostCallable = Callable[[str, dict[str, Any], dict[str, Any]], Any]


@dataclass(frozen=True)
class ProviderPreset:
    """An OpenAI-compatible provider: base URL, default model, key env var."""

    name: str
    base_url: str
    default_model: str
    api_key_env: str


PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        "openai", "https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"
    ),
    "mistral": ProviderPreset(
        "mistral", "https://api.mistral.ai/v1", "mistral-small-latest", "MISTRAL_API_KEY"
    ),
    "groq": ProviderPreset(
        "groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"
    ),
    "deepseek": ProviderPreset(
        "deepseek", "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY"
    ),
    "cohere": ProviderPreset(
        "cohere", "https://api.cohere.com/compatibility/v1", "command-r-plus", "COHERE_API_KEY"
    ),
    "together": ProviderPreset(
        "together", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_API_KEY"
    ),
    "xai": ProviderPreset(
        "xai", "https://api.x.ai/v1", "grok-2", "XAI_API_KEY"
    ),
    "openrouter": ProviderPreset(
        "openrouter", "https://openrouter.ai/api/v1", "openrouter/auto", "OPENROUTER_API_KEY"
    ),
}


def list_presets() -> list[str]:
    """The available OpenAI-compatible preset names, sorted."""
    return sorted(PRESETS)


def get_llm(
    provider: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 60.0,
    post: PostCallable | None = None,
) -> OpenAICompatibleLLM:
    """Return an ``OpenAICompatibleLLM`` configured for ``provider`` by name."""
    key = provider.lower()
    if key not in PRESETS:
        raise ValueError(
            f"unknown LLM provider '{provider}' (choose from {list_presets()}; "
            "bedrock / vertex / azure_openai are handled by their own adapters)"
        )
    preset = PRESETS[key]
    resolved_key = api_key if api_key is not None else os.getenv(preset.api_key_env)
    return OpenAICompatibleLLM(
        model or preset.default_model,
        base_url=preset.base_url,
        api_key=resolved_key,
        timeout=timeout,
        post=post,
    )
