"""Tests for loading the vision plugin into a Xyberos app."""

from __future__ import annotations

import base64

from xyberos import create_app

from xyberos_vision import VisionPlugin


def test_plugin_registers_tools(tmp_path):
    def request(method, url, **kwargs):
        if url.endswith("/images/generations"):
            return 200, {"data": [{"b64_json": base64.b64encode(b"PNG").decode("ascii")}]}
        return 200, {"choices": [{"message": {"content": "A cat"}}]}

    image = tmp_path / "img.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rioEND")

    app = create_app()
    app.load_plugin(VisionPlugin(api_key="k", request=request))
    assert "vision_describe" in app.tools.names
    assert "ocr_extract_text" in app.tools.names
    assert "image_generate" in app.tools.names

    assert app.tools.execute("vision_describe", None, image_path=str(image)) == "A cat"
    output = tmp_path / "gen.png"
    assert app.tools.execute("image_generate", None, prompt="a dog", output_path=str(output)) == str(output)
    assert output.read_bytes() == b"PNG"

    app.unload_plugin("vision")
