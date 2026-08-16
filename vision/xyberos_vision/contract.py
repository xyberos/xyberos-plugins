"""Vision / OCR / image-generation contracts (RFC-0019, M8)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VisionModel(Protocol):
    """Anything that describes an image given a prompt."""

    name: str

    def describe(self, image_path: str, prompt: str) -> str:
        """Return a text description of the image at ``image_path``."""
        ...


@runtime_checkable
class OCR(Protocol):
    """Anything that extracts text from an image."""

    name: str

    def extract_text(self, image_path: str) -> str:
        """Return the text found in the image at ``image_path``."""
        ...


@runtime_checkable
class ImageGenerator(Protocol):
    """Anything that turns a prompt into an image file."""

    name: str

    def generate(self, prompt: str, output_path: str) -> str:
        """Write a generated image to ``output_path`` and return the path."""
        ...
