# xyberos-openai-compatible

**A `ModelProvider` for OpenAI-compatible chat and embedding endpoints, proved against the suite
this project ships.**

Xyberos keeps one AI provider in the core (the Ollama adapter, `xyberos[ollama]`) and makes the
boundary a protocol: a service depends on `ModelProvider`, never on a vendor. This package supplies
a second implementation — the `POST /chat/completions`, `POST /embeddings`, and `GET /models` shape
that OpenAI, and most gateways that speak for it, serve — and proves it the way the contract
requires, by running the shipped conformance suite against a real HTTP service rather than by
asserting that it works.

## Install

```bash
pip install xyberos-openai-compatible
```

## Register it

A provider arrives the way any other service does: supplied as an instance the application owns and
closes.

```python
from xyberos import App
from xyberos.ai import ModelProvider
from xyberos_openai_compatible import OpenAICompatibleSettings, openai_compatible_provider

app = App()
app.provide(
    ModelProvider,
    factory=openai_compatible_provider(
        OpenAICompatibleSettings(
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            api_key="******",
            structured_output=True,
            tools=True,
        )
    ),
    eager=True,
)
```

The settings carry the base URL, the API key, the connect and read timeouts, and the retry budget.
The key is never rendered: `repr(settings)` and `safe_base_url` are the two a log line or an error
message should name, and `safe_base_url` also masks the values of a gateway's query-string token
while leaving the names readable.

Capabilities are declared, not guessed: `chat`, `structured_output`, `tools`, `streaming`, and
`embeddings` are configuration, and a request that needs one the settings do not claim is refused
with `AIUnsupportedCapabilityError` before any call is made.

## Conformance

```bash
python -m xyberos_openai_compatible.conformance     # no configuration needed
```

With `XYBEROS_OPENAI_BASE_URL` set, the suites run against that deployment:

```bash
XYBEROS_OPENAI_BASE_URL=https://gateway.internal/v1 \
XYBEROS_OPENAI_API_KEY=****** \
XYBEROS_OPENAI_MODEL=your-model \
  python -m xyberos_openai_compatible.conformance
```

The core repository's `packages.toml` names that module as this package's conformance target, so the
compatibility job runs it against the published core. With nothing configured it serves the fake
endpoint this distribution ships — `xyberos_openai_compatible.stub`, a real local HTTP service rather
than a mock of one, so the provider still speaks HTTP over a socket — and runs the suites against
that. That is what lets a job which holds no credential check this adapter at all; a deployment's
endpoint is checked instead when one is named.

`python -m xyberos_openai_compatible.stub` serves the same fake on port 59080, which is what the
`XYBEROS_OPENAI_BASE_URL` default in the module documents, for reading the wire directly.

Every claim above is a promise the suite then holds the endpoint to, so a deployment whose endpoint
cannot do something turns that claim off in the environment —
`XYBEROS_OPENAI_TOOLS=false`, `XYBEROS_OPENAI_STRUCTURED_OUTPUT=false`,
`XYBEROS_OPENAI_STREAMING=false`, `XYBEROS_OPENAI_EMBEDDINGS=false`,
`XYBEROS_OPENAI_CHAT=false` — and the suite checks that the provider *refuses* it instead of
attempting it. Point `XYBEROS_OPENAI_EMBEDDING_MODEL` at the embedding model the endpoint serves
before claiming embeddings.

## What it does not do

- **No model management.** Xyberos never downloads, pulls, or loads a model; readiness is reported
  from `GET /models`, and a service that does not implement that route is reported unhealthy rather
  than assumed usable.
- **No vendor dialects.** Azure's `deployments` path and `api-key` header, Bedrock's `converse`
  body, and Vertex's `generateContent` body are different APIs with their own providers. This
  package serves the OpenAI shape and nothing else.
- **No tool identity beyond the tool name.** The contract's `Message.tool_result` names the tool
  that answered and carries no call id, so a tool result is sent with `name` and without a
  `tool_call_id`; a gateway that insists on the id will reject such a round trip.
- **No multimodal content.** Message content is text, which is all the contract carries in this
  release.
