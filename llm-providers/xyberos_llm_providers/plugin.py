"""LLM providers plugin entry point (RFC-0019, M6).

Registers a single :class:`~xyberos.contracts.LLMProvider` as the app's ``llm``
(replacing the default). The provider is selected by name — either an
OpenAI-compatible preset (``mistral``, ``groq``, ``deepseek``, ``cohere``,
``together``, ``xai``, ``openai``, ``openrouter``) or a dedicated adapter
(``azure_openai``, ``bedrock``, ``vertex``). An unconfigured instance is a safe
no-op for entry-point discovery.
"""

from __future__ import annotations

import os
from typing import Any

from xyberos.contracts import Plugin
from xyberos.llm import LLMProvider

from .azure import AzureOpenAILLM
from .bedrock import BedrockLLM
from .presets import get_llm
from .vertex import VertexAILlm


class LlmProvidersPlugin(Plugin):
    """Registers a configured LLM provider by name."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        *,
        env_prefix: str = "LLM",
        timeout: float = 60.0,
        post: Any = None,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._model = model
        self._env_prefix = env_prefix
        self._timeout = timeout
        self._post = post
        self._llm: LLMProvider | None = None

    @property
    def name(self) -> str:
        return "llm_providers"

    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = self._build()
        return self._llm

    def register(self, kernel: object) -> None:
        try:
            llm = self.llm()
        except ValueError as exc:
            logger = getattr(kernel, "logger", None)
            if logger is not None and callable(getattr(logger, "warning", None)):
                logger.warning("llm_providers plugin not configured: %s", exc)
            return
        kernel.register("llm", llm, replace=True)

    def unregister(self, kernel: object) -> None:
        pass

    # -- internals ----------------------------------------------------------

    def _build(self) -> LLMProvider:
        provider = self._provider or os.getenv(f"{self._env_prefix}_PROVIDER")
        if not provider:
            raise ValueError(
                "llm_providers plugin is not configured: pass provider=... or set "
                f"{self._env_prefix}_PROVIDER"
            )
        name = provider.lower()
        if name == "azure_openai":
            deployment = self._model or os.getenv("AZURE_OPENAI_DEPLOYMENT")
            if not deployment:
                raise ValueError("azure_openai requires a deployment (AZURE_OPENAI_DEPLOYMENT)")
            return AzureOpenAILLM(deployment, timeout=self._timeout, post=self._post)
        if name == "bedrock":
            return BedrockLLM(self._model)
        if name in ("vertex", "vertexai"):
            return VertexAILlm(self._model or "gemini-1.5-flash", post=self._post)
        return get_llm(
            name,
            api_key=self._api_key,
            model=self._model,
            timeout=self._timeout,
            post=self._post,
        )


#: Auto-discovered by ``app.load_entry_points()``.
plugin = LlmProvidersPlugin()
