# xyberos-vision

**Vision plugin — RFC-0019, M8.** Describe images (vision model), extract text
(OCR), and generate images — three tools, three contracts.

## Install

```bash
pip install xyberos-vision             # from PyPI
pip install "xyberos-vision[ocr]"      # optional: pytesseract + pillow for OCR

# development (editable, from this repo):
pip install -e ./vision
```

## Usage

```python
from xyberos import create_app
from xyberos_vision import VisionPlugin

app = create_app()
app.load_plugin(VisionPlugin())    # key from OPENAI_API_KEY

app.tools.execute("vision_describe", None, image_path="photo.png", prompt="What's in this photo?")
app.tools.execute("ocr_extract_text", None, image_path="scan.png")
app.tools.execute("image_generate", None, prompt="a sunset over the ocean", output_path="out.png")
```

## Tools

| Tool | Backed by |
| ---- | --------- |
| `vision_describe(image_path, prompt=...)` | `OpenAICompatibleVision` (`VISION_MODEL`, default `gpt-4o-mini`) |
| `ocr_extract_text(image_path)` | `TesseractOCR` (lazy `pytesseract` + `pillow`) |
| `image_generate(prompt, output_path)` | `OpenAIImageGenerator` (`dall-e-3`) |

## Tests

```bash
pip install pytest
pytest tests/
```

Vision/image-gen are tested via injectable transports; OCR tests skip when
`pytesseract` is absent.

## Ship location

Plugin (`xyberos.plugins` entry point) — vision/multimodal (M8).
