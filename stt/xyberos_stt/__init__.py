"""Speech-to-text plugin (RFC-0019, M8)."""

from .adapters import AssemblyAISTT, DeepgramSTT, LocalWhisperSTT
from .contract import SpeechToText
from .plugin import SttPlugin

__all__ = [
    "AssemblyAISTT",
    "DeepgramSTT",
    "LocalWhisperSTT",
    "SpeechToText",
    "SttPlugin",
]
