"""Remaining LLM providers plugin (RFC-0019, M6).

Thin configs, no new architecture: OpenAI-compatible presets (Mistral, Groq,
DeepSeek, Cohere, Together, xAI, OpenAI, OpenRouter) via the core
``OpenAICompatibleLLM``, plus dedicated adapters for Azure OpenAI, AWS Bedrock
and Google Vertex AI. All are ``LLMProvider`` implementations.
"""

from .azure import AzureOpenAILLM
from .bedrock import BedrockLLM
from .plugin import LlmProvidersPlugin
from .presets import PRESETS, ProviderPreset, get_llm, list_presets
from .vertex import VertexAILlm

__all__ = [
    "AzureOpenAILLM",
    "BedrockLLM",
    "LlmProvidersPlugin",
    "PRESETS",
    "ProviderPreset",
    "VertexAILlm",
    "get_llm",
    "list_presets",
]
