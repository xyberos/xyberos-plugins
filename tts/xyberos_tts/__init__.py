"""Text-to-speech plugin (RFC-0019, M8)."""

from .adapters import ElevenLabsTTS, OpenAITTS, PiperTTS, PollyTTS
from .contract import TextToSpeech
from .plugin import TtsPlugin

__all__ = ["ElevenLabsTTS", "OpenAITTS", "PiperTTS", "PollyTTS", "TextToSpeech", "TtsPlugin"]
