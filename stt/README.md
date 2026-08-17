# xyberos-stt

**Speech-to-text plugin — RFC-0019, M8.** Transcribe audio via local OpenAI
Whisper or the Deepgram / AssemblyAI cloud APIs through one `SpeechToText`
contract.

## Install

```bash
pip install xyberos-stt                # from PyPI

# development (editable, from this repo):
pip install -e ./stt
```

## Usage

```python
from xyberos import create_app
from xyberos_stt import SttPlugin

app = create_app()
app.load_plugin(SttPlugin(provider="deepgram"))   # key from DEEPGRAM_API_KEY

transcript = app.tools.execute("stt_transcribe", None, audio_path="call.wav")
```

Provider selection: `STT_PROVIDER` env or `provider=` (`deepgram` default,
`assemblyai`, `whisper`).

| Provider | Type | Key env |
| -------- | ---- | ------- |
| `whisper` | local (lazy `openai-whisper`) | — (downloads model weights) |
| `deepgram` | cloud | `DEEPGRAM_API_KEY` |
| `assemblyai` | cloud (upload → poll) | `ASSEMBLYAI_API_KEY` |

## Tools

- `stt_transcribe(audio_path) -> str`

## Examples

- `examples/voice_assistant.py` — STT → LLM → TTS pipeline (offline `--stub` mode).

## Tests

```bash
pip install pytest
pytest tests/
```

Deepgram/AssemblyAI are tested via injectable transports; Whisper tests skip
when `openai-whisper` is absent.

## Ship location

Plugin (`xyberos.plugins` entry point) — voice (M8).
