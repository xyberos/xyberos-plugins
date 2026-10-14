"""OpenAI-compatible chat and embedding endpoints as a Xyberos ``ModelProvider``.

Services depend on :class:`~xyberos.ai.contracts.ModelProvider`, never on this package: the provider
is supplied at composition time, already usable, and the application owns closing it.

    from xyberos import App
    from xyberos.ai import ModelProvider
    from xyberos_openai_compatible import OpenAICompatibleSettings, openai_compatible_provider

    app = App()
    app.provide(
        ModelProvider,
        factory=openai_compatible_provider(OpenAICompatibleSettings(model="gpt-4o-mini")),
        eager=True,
    )

What this package owns is the wire format of ``/chat/completions``, ``/embeddings``, and
``/models``, the error mapping onto Xyberos' exception hierarchy, and the configured capability
claims. What it does not own is a model: Xyberos never downloads, pulls, or chooses one, and a
capability the settings do not claim is refused rather than attempted.
"""

from xyberos_openai_compatible.provider import (
    OpenAICompatibleProvider,
    OpenAICompatibleSettings,
    openai_compatible_provider,
)

__all__ = [
    "OpenAICompatibleProvider",
    "OpenAICompatibleSettings",
    "openai_compatible_provider",
]
