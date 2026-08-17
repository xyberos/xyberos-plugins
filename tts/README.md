# xyberos-tts

**Text-to-speech plugin — RFC-0019, M8.** Synthesize speech via ElevenLabs,
OpenAI, AWS Polly, or local Piper through one `TextToSpeech` contract.

## Install

```bash
pip install xyberos-tts                # from PyPI

# development (editable, from this repo):
pip install -e ./tts
```

## Usage

```python
from xyberos import create_app
from xyberos_tts import TtsPlugin

app = create_app()
app.load_plugin(TtsPlugin(provider="elevenlabs"))   # key from ELEVENLABS_API_KEY

path = app.tools.execute("tts_synthesize", None, text="Hello!", output_path="out.mp3")
```

Provider selection: `TTS_PROVIDER` env or `provider=` (`elevenlabs` default,
`openai`, `polly`, `piper`).

| Provider | Type | Key / config |
| -------- | ---- | ------------ |
| `elevenlabs` | cloud | `ELEVENLABS_API_KEY` |
| `openai` | cloud | `OPENAI_API_KEY` |
| `polly` | cloud (lazy `boto3`) | AWS credentials |
| `piper` | local CLI | `PIPER_MODEL` + `piper` executable |

## Tools

- `tts_synthesize(text, output_path) -> str` (writes the audio file)

## Tests

```bash
pip install pytest
pytest tests/
```

Cloud adapters are tested via injectable raw transports; Polly via a fake
client; Piper via an injectable runner.

## Ship location

Plugin (`xyberos.plugins` entry point) — voice (M8).
