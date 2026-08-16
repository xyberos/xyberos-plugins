"""Example (M8): vision tools via the xyberos plugin.
Requires OPENAI_API_KEY (describe / generate); OCR needs tesseract.

    python examples/example.py IMAGE.png
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_vision import VisionPlugin


def main() -> None:
    image = sys.argv[1] if len(sys.argv) > 1 else "image.png"
    app = create_app()
    app.load_plugin(VisionPlugin())

    print("describe:", app.tools.execute("vision_describe", None, image_path=image))
    print("ocr:", app.tools.execute("ocr_extract_text", None, image_path=image))

    output = Path(__file__).parent / "generated.png"
    print("generated:", app.tools.execute("image_generate", None, prompt="a photo of a sunset", output_path=str(output)))

    app.unload_plugin("vision")


if __name__ == "__main__":
    main()
