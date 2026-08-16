"""Vision plugin (RFC-0019, M8)."""

from .adapters import OpenAICompatibleVision, OpenAIImageGenerator, TesseractOCR
from .contract import ImageGenerator, OCR, VisionModel
from .plugin import VisionPlugin

__all__ = [
    "ImageGenerator",
    "OCR",
    "OpenAICompatibleVision",
    "OpenAIImageGenerator",
    "TesseractOCR",
    "VisionModel",
    "VisionPlugin",
]
