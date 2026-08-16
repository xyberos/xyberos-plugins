"""Example (M8): synthesize speech via the xyberos TTS plugin.
Requires TTS_PROVIDER (or provider=) + the matching API key.

    python examples/example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_tts import TtsPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(TtsPlugin(provider="openai"))   # key from OPENAI_API_KEY

    output = Path(__file__).parent / "hello.mp3"
    result = app.tools.execute("tts_synthesize", None, text="Hello from Xyberos!", output_path=str(output))
    print("wrote:", result)

    app.unload_plugin("tts")


if __name__ == "__main__":
    main()
