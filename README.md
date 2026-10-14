# Xyberos Plugins

Standalone plugins implementing the [RFC-0019 integrations roadmap](RFC-0019-integrations-roadmap.md).
Each folder is an independently installable plugin that plugs into the public
`xyberos` API via the `xyberos.plugins` entry-point group.

## Build order (as specified)

| Milestone | Folder | What it is | Status |
| --------- | ------ | ---------- | ------ |
| **M2** — Generic HTTP/API connector | [`http-api/`](http-api/) | Declarative `base_url`/auth/operations → one typed `Tool` per operation | 🟢 |
| **M1** — Filesystem + document loaders | [`documents/`](documents/) | `FileLoader`/`HtmlLoader`/`CsvLoader` (stdlib) + `PdfLoader`/`DocxLoader`/`XlsxLoader` (lazy `[documents]`) → `IngestingKnowledge` | 🟢 |
| **M4** — RAG completeness | [`vector-qdrant/`](vector-qdrant/) · [`vector-faiss/`](vector-faiss/) · [`vector-redis/`](vector-redis/) | `VectorStore`/`Memory`/cache adapters + parity tests vs `SqliteVectorStore` | 🟢 |
| **M3** — MCP | [`mcp/`](mcp/) | the **server** direction: `expose()` an application's tools over MCP. The client lives in the core module `xyberos.mcp`, and the stdio transport is withheld pending the owner's approval | 🟢 |
| **M5** — Web search abstraction | [`web-search/`](web-search/) | one `WebSearch` contract, Tavily/Serper/Brave/Exa/Firecrawl behind it | 🟢 |
| **M6** — Remaining LLM providers | [`llm-providers/xyberos_llm_providers/`](llm-providers/xyberos_llm_providers/) | OpenAI-compatible presets (Mistral/Groq/DeepSeek/Cohere/Together/xAI) + Azure/Bedrock/Vertex | 🟢 |
| **M7** — Community wave | [`github/`](github/) · [`gitlab/`](gitlab/) · [`slack/`](slack/) · [`discord/`](discord/) · [`notion/`](notion/) · [`jira/`](jira/) · [`linear/`](linear/) | comm / PM tools via REST+GraphQL plugins | 🟢 |
| **M8** — Voice + vision / multimodal | [`stt/`](stt/) · [`tts/`](tts/) · [`vision/`](vision/) | STT (Whisper/Deepgram/AssemblyAI), TTS (ElevenLabs/OpenAI/Polly/Piper), vision/OCR/image-gen | 🟢 |
| **M9** — Enterprise + infrastructure | [`auth/`](auth/) · [`storage/xyberos_storage/`](storage/xyberos_storage/) · [`db/xyberos_db/`](db/xyberos_db/) · [`queues/`](queues/) | verification only: an assertion from a shared secret or a JWKS, and a `Principal` — no OAuth2 flows, no OIDC, no IdP presets · object storage (S3/Azure/GCS/OneDrive) · DB contract (RFC-0020) · message queues | 🟢 |
| **M10** — Observability | [`observability/`](observability/) | one explicit call that installs a logging handler, a level, a format, and the runtime's own `ContextLogFilter`, plus spans fed by the runtime's own event sink | 🟢 |

> **Why `vector-*` folder names?** The `faiss` and `redis` third-party packages
> are real top-level modules. A plugin folder named exactly `faiss/` or
> `redis/` would shadow them (as a namespace package) whenever the repo root is
> on `sys.path`. The `vector-*` names avoid that.

## Layout

A distribution lives in a directory of its own. A subject with more than one
distribution groups them in a folder named for the subject: `github/` holds the
`xyberos-github` distribution directly, while `db/` holds `db/xyberos_db/` today
and takes the next database provider beside it — `db/xyberos_postgres/` — rather
than in a folder of its own. The publishing workflow discovers distributions at
both depths, and a tag names the directory: `db/xyberos_postgres/v0.1.0`.

Type checking is per distribution. The repository root's `pyrightconfig.json`
resolves `xyberos` from a `../xyberos` checkout, which is the 1.x line, so a
distribution written against this line carries its own config beside its
`pyproject.toml` and lets the interpreter supply the core range it declares.

## What targets which line

Most folders here still target the 1.x line and declare `xyberos>=1.0,<2`. Seven
distributions target this line and declare `xyberos>=2,<3`:

| Distribution | Directory | What it is |
| --- | --- | --- |
| `xyberos-postgres` | [`db/xyberos_postgres/`](db/xyberos_postgres/) | a `DatabaseProvider` over `asyncpg`, proved by `assert_provider_contract` |
| `xyberos-storage-s3` | [`storage/xyberos_storage_s3/`](storage/xyberos_storage_s3/) | a `Storage` provider over `aioboto3`, proved by `assert_storage_contract` |
| `xyberos-openai-compatible` | [`llm-providers/xyberos_openai_compatible/`](llm-providers/xyberos_openai_compatible/) | a `ModelProvider` over `httpx`, proved by `assert_model_provider_contract` |
| `xyberos-templates` | [`templates/xyberos_templates/`](templates/xyberos_templates/) | an engine-neutral `Templates` contract with Jinja2 shipped, rendered off the event loop, autoescape stated rather than inherited |
| `xyberos-mcp` | [`mcp/`](mcp/) | a rewrite: the server direction only |
| `xyberos-auth` | [`auth/`](auth/) | a rewrite: verification only |
| `xyberos-observability` | [`observability/`](observability/) | a rewrite: a handler and spans |

Three of those — `mcp/`, `auth/`, and `observability/` — are **rewrites in place**: the folder kept its
name and its distribution, and the published 1.x release stays on the index while its source stays in
this repository's history. A name this line retires instead keeps its 1.x tree one level down, so
`xyberos-db`'s pointer patch still builds from `db/xyberos_db/`.

One environment holds either line, never both: the two share an import root, so a project that needs
both runs two environments.

## Conventions

Every distribution:

- is a **standalone package** with its own `pyproject.toml` and an
  `xyberos.plugins` entry point;
- uses only the **public `xyberos` API** (`Tool` / `FunctionTool`,
  `Knowledge` / `VectorStore` / `Memory` / `Plugin` contracts,
  `utils.resilience.RateLimiter`, …);
- imports optional third-party dependencies **lazily** and raises a clear
  `ProviderError` when they are missing;
- ships **tests** (optional-dep tests skip cleanly), **examples**, and a
  **README**.

## Install & validate

```bash
# editable install each plugin you want to use
pip install -e ./http-api
pip install -e ./documents
pip install -e ./vector-qdrant -e ./vector-faiss -e ./vector-redis
pip install -e ./mcp -e ./web-search
pip install -e ./llm-providers/xyberos_llm_providers
# community wave (M7) — install any subset
pip install -e ./github -e ./gitlab -e ./slack -e ./discord -e ./notion -e ./jira -e ./linear
# voice + vision (M8)
pip install -e ./stt -e ./tts -e ./vision
# enterprise + infra (M9)
pip install -e ./auth -e ./storage/xyberos_storage -e ./db/xyberos_db -e ./queues
# observability (M10)
pip install -e ./observability

# run a plugin's tests from its folder
cd http-api && python -m pytest tests -q
cd documents && python -m pytest tests -q

# auto-discover installed plugins through the entry-point group
python -c "from xyberos import create_app; app = create_app(); print(app.load_entry_points())"
```

## Ship-location notes (from RFC-0019)

- **M2** ships as a **Plugin** (uses only `Tool`/`FunctionTool` public API).
- **M1** `FileLoader`/`HtmlLoader`/`CsvLoader` are **stdlib Core**-equivalent;
  `PdfLoader`/`DocxLoader`/`XlsxLoader` map to the **`[documents]`** extra.
- **M4** Qdrant/FAISS map to **`[vectors]`**; Redis maps to the **`[state]`**
  extra (`redis`). All added to `pyproject.toml` (plus `[mcp]`).
- **M3** is a **Plugin** + optional **`[mcp]`** extra; the client itself is
  stdlib-only (JSON-RPC over stdio / streamable HTTP).
- **M5** is a **Plugin** (thin `urllib` adapters).
- **M6** is a **Plugin** / `[llm-providers]` extra — presets reuse the core
  `OpenAICompatibleLLM` (no new architecture per provider).
- **M10** is a **Plugin** — thin `EventBus` exporters (`[otel]`/`[prometheus]`/`[sentry]` extras).
