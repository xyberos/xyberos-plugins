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
| **M3** — MCP client | [`mcp/`](mcp/) | stdio + streamable HTTP `McpClient` → one `Tool` per server tool | 🟢 |
| **M5** — Web search abstraction | [`web-search/`](web-search/) | one `WebSearch` contract, Tavily/Serper/Brave/Exa/Firecrawl behind it | 🟢 |

> **Why `vector-*` folder names?** The `faiss` and `redis` third-party packages
> are real top-level modules. A plugin folder named exactly `faiss/` or
> `redis/` would shadow them (as a namespace package) whenever the repo root is
> on `sys.path`. The `vector-*` names avoid that.

## Conventions

Every plugin:

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
