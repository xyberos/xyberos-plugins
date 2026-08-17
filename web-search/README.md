# xyberos-web-search

**Web search abstraction plugin — RFC-0019, M5.** One `WebSearch` contract
(`search(query, top_k) -> list[Result]`), many providers behind it: **Tavily**,
**Serper**, **Brave**, **Exa**, **Firecrawl**. Each adapter is a thin,
stdlib-only `urllib` call; the plugin exposes a single typed `web_search` tool.

## Install

```bash
pip install xyberos-web-search         # from PyPI

# development (editable, from this repo):
pip install -e ./web-search
```

## Usage

```python
from xyberos import create_app
from xyberos_web_search import WebSearchPlugin

app = create_app()
app.load_plugin(WebSearchPlugin(provider="tavily"))   # API key from TAVILY_API_KEY

app.tools.execute("web_search", None, query="xyberos", top_k=5)
```

Provider + key resolution (explicit args, then env):

| Provider | `provider` | API key env |
| -------- | ---------- | ----------- |
| Tavily | `tavily` | `TAVILY_API_KEY` |
| Serper | `serper` | `SERPER_API_KEY` |
| Brave | `brave` | `BRAVE_API_KEY` |
| Exa | `exa` | `EXA_API_KEY` |
| Firecrawl | `firecrawl` | `FIRECRAWL_API_KEY` |

`WEB_SEARCH_PROVIDER` selects the default provider (default `tavily`). Calling
the tool without a key raises a clear `ProviderError`.

### Use the contract directly (provider-agnostic)

```python
from xyberos_web_search import get_web_search

search = get_web_search("serper")   # reads SERPER_API_KEY
for result in search.search("xyberos", top_k=3):
    print(result.title, result.url, result.snippet)
```

## Design

- **Contract** — `WebSearch` protocol + `SearchResult(title, url, snippet,
  score, extra)`.
- **Adapters** — thin, dependency-free, with an injectable `request` transport
  so tests run without a network.
- **Tool** — the plugin registers `web_search(query: str, top_k: int = 5)`
  through the public `FunctionTool` API.

## Examples

- `examples/web_search.py` — CLI example; needs an API key (see README).

## Tests

```bash
pip install pytest
pytest tests/
```

Adapters are tested against canned responses via a fake transport — no network
required.

## Ship location

Plugin (`xyberos.plugins` entry point). Depends on M2's HTTP patterns.
