# xyberos-qdrant

**Qdrant `VectorStore` plugin — RFC-0019, M4.** Hosted or local [Qdrant](https://qdrant.tech)
as an `xyberos` `VectorStore`. Passes the same parity scenarios as the stdlib
`SqliteVectorStore` (the M4 Definition of Done).

## Install

```bash
pip install xyberos-qdrant             # from PyPI
pip install "xyberos-qdrant[vectors]"  # pulls in qdrant-client

# development (editable, from this repo):
pip install -e ./qdrant
pip install qdrant-client        # or: pip install xyberos[vectors]
```

## Usage

```python
from xyberos import create_app
from xyberos_qdrant import QdrantPlugin

app = create_app()
app.load_plugin(QdrantPlugin(location=":memory:"))   # local, no infrastructure
# hosted: QdrantPlugin(url="https://...", api_key=os.getenv("QDRANT_API_KEY"))

store = app.resolve("vector_store")
store.upsert("ns", "doc-1", [1.0, 0.0, 0.0, 0.0], {"text": "alpha"})
hits = store.query("ns", [1.0, 0.0, 0.0, 0.0], top_k=3)
```

Or configure through the environment (`QDRANT_URL`, `QDRANT_API_KEY`,
`QDRANT_DIM`) and let the `xyberos.plugins` entry point register it.

## Design

- Each **namespace** maps to a Qdrant collection using **cosine** distance
  (higher score = more relevant, matching the `VectorStore` contract).
- The client is imported **lazily** and a clear `ProviderError` is raised when
  `qdrant-client` is missing.
- Arbitrary string ids are mapped to deterministic UUIDs (Qdrant point ids are
  `int`/`UUID`); the original id round-trips through the payload, so the
  contract's string ids hold exactly.

## Tests

```bash
pip install pytest
pytest tests/          # unit + parity + plugin tests
```

Parity tests run against Qdrant's **in-memory local mode**, so they need no
server; they skip cleanly if `qdrant-client` is absent.

## Ship location

`[vectors]` extra (`qdrant-client` already added to `pyproject.toml`).
