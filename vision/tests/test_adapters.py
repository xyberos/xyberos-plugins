"""Tests for the vision adapters (injectable transports / skips, no network)."""

from __future__ import annotations

import base64
import importlib.util

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_vision import OpenAICompatibleVision, OpenAIImageGenerator, TesseractOCR


def _tiny_png(tmp_path) -> str:
    # A 1x1 PNG so image reading + base64 works without real image deps.
    path = tmp_path / "img.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rioEND")
    return str(path)


def test_vision_describe(tmp_path):
    captured = {}

    def request(method, url, **kwargs):
        captured.update(kwargs)
        return 200, {"choices": [{"message": {"content": "A cat"}}]}

    image = _tiny_png(tmp_path)
    vision = OpenAICompatibleVision(api_key="k", request=request)
    assert vision.describe(image, "What is this?") == "A cat"
    content = captured["json_body"]["messages"][0]["content"]
    assert content[0]["text"] == "What is this?"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_vision_requires_key():
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        OpenAICompatibleVision(api_key=None, request=lambda *a, **k: (200, {})).describe("x.png", "p")


def test_image_generate(tmp_path):
    def request(method, url, **kwargs):
        return 200, {"data": [{"b64_json": base64.b64encode(b"PNGDATA").decode("ascii")}]}

    output = tmp_path / "gen.png"
    gen = OpenAIImageGenerator(api_key="k", request=request)
    assert gen.generate("a dog", str(output)) == str(output)
    assert output.read_bytes() == b"PNGDATA"


def test_ocr():
    if importlib.util.find_spec("pytesseract") is None:
        pytest.skip("pytesseract is not installed")
    ocr = TesseractOCR()
    assert isinstance(ocr, TesseractOCR)
