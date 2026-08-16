"""Example (M8): a voice assistant — STT → LLM → TTS.

Runs offline by default (--stub uses a canned transcript, EchoLLM and a stub
audio writer). With --real it uses the configured STT/TTS providers and an
LLM_PROVIDER-compatible model:

    python examples/voice_assistant.py                 # offline demo
    python examples/voice_assistant.py --real          # real APIs (keys required)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app
from xyberos.llm import EchoLLM

from xyberos_stt import SttPlugin
from xyberos_tts import TtsPlugin


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice assistant: STT -> LLM -> TTS")
    parser.add_argument("--audio", default="input.wav", help="audio file to transcribe")
    parser.add_argument("--output", default="output.mp3", help="where to write the reply")
    parser.add_argument("--stub", action="store_true", help="offline demo (no API keys)")
    args = parser.parse_args()

    app = create_app()

    if args.stub:
        # A canned transcript + a stub TTS writer, so the pipeline runs offline.
        audio_path = Path(args.audio)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        if not audio_path.is_file():
            audio_path.write_bytes(b"PLACEHOLDER-AUDIO")

        def fake_request(method, url, **kwargs):
            return 200, {"results": {"channels": [{"alternatives": [{"transcript": "what is two plus two?"}]}]}}

        def fake_raw_request(method, url, **kwargs):
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_bytes(b"FAKE-AUDIO")
            return 200, b"FAKE-AUDIO"

        app.load_plugin(SttPlugin(provider="deepgram", api_key="stub", request=fake_request))
        app.load_plugin(TtsPlugin(provider="openai", api_key="stub", raw_request=fake_raw_request))
    else:
        app.load_plugin(SttPlugin())   # STT_PROVIDER + key
        app.load_plugin(TtsPlugin())   # TTS_PROVIDER + key

    transcript = app.tools.execute("stt_transcribe", None, audio_path=args.audio)
    print("heard:", transcript)

    response = app.llm.generate(f"Answer briefly: {transcript}")
    print("reply:", response)

    audio_file = app.tools.execute("tts_synthesize", None, text=response, output_path=args.output)
    print("audio:", audio_file)

    app.unload_plugin("stt")
    app.unload_plugin("tts")


if __name__ == "__main__":
    main()
