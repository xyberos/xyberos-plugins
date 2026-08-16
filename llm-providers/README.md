# xyberos-llm-providers

**Remaining LLM providers plugin — RFC-0019, M6.** Thin configs, no new
architecture. The long tail of OpenAI-compatible providers are covered by
**presets** over the core `OpenAICompatibleLLM`; Azure OpenAI, AWS Bedrock and
Google Vertex AI get dedicated `LLMProvider` adapters.

## Install

```bash
pip install -e ./llm-providers
pip install xyberos[llm-providers]   # optional: boto3 + google-auth for Bedrock/Vertex
```

## Provider presets (OpenAI-compatible — one line each)

| `provider` | base URL | default model | API key env |
| ---------- | -------- | ------------- | ----------- |
| `openai` | `api.openai.com/v1` | `gpt-4o-mini` | `OPENAI_API_KEY` |
| `mistral` | `api.mistral.ai/v1` | `mistral-small-latest` | `MISTRAL_API_KEY` |
| `groq` | `api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| `deepseek` | `api.deepseek.com/v1` | `deepseek-chat` | `DEEPSEEK_API_KEY` |
| `cohere` | `api.cohere.com/compatibility/v1` | `command-r-plus` | `COHERE_API_KEY` |
| `together` | `api.together.xyz/v1` | `Llama-3.3-70B-Instruct-Turbo` | `TOGETHER_API_KEY` |
| `xai` | `api.x.ai/v1` | `grok-2` | `XAI_API_KEY` |
| `openrouter` | `openrouter.ai/api/v1` | `openrouter/auto` | `OPENROUTER_API_KEY` |

```python
from xyberos_llm_providers import get_llm
llm = get_llm("groq")                      # key from GROQ_API_KEY
print(llm.generate("Say hi"))
```

## Dedicated adapters

- **Azure OpenAI** — `AzureOpenAILLM(deployment, endpoint=..., api_key=...)`
  posts to the Azure deployments endpoint with an `api-key` header
  (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`).
- **AWS Bedrock** — `BedrockLLM(model_id)` over `bedrock-runtime.converse`
  (lazy `boto3`; region from `AWS_REGION`/`AWS_DEFAULT_REGION`).
- **Google Vertex AI** — `VertexAILlm(model, project=...)` over the
  `generateContent` REST API (lazy `google-auth` token;
  `VERTEX_AI_PROJECT`/`GOOGLE_CLOUD_PROJECT`).

## Plugin usage

```python
from xyberos import create_app
from xyberos_llm_providers import LlmProvidersPlugin

app = create_app()
app.load_plugin(LlmProvidersPlugin(provider="deepseek"))   # or set LLM_PROVIDER=deepseek
print(app.llm.generate("Say hi"))
```

`provider` accepts a preset name or `azure_openai` / `bedrock` / `vertex`.
An unconfigured plugin registers nothing (logs a warning); calling
`plugin.llm()` directly surfaces misconfiguration errors.

## Examples

- `examples/llm_providers.py` — lists presets and runs one; `--stub` for a
  no-network demo, otherwise a real call.

## Tests

```bash
pip install pytest
pytest tests/
```

All adapters are tested against stub transports / fake clients — no network,
no SDKs required. Bedrock/Vertex lazy-import tests skip when their SDK is
present.

## Ship location

Plugin (`xyberos.plugins` entry point) / `[llm-providers]` extra. One
`LLMProvider` contract; providers are implementations of it.
