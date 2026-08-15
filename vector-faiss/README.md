# xyberos-faiss

**FAISS `VectorStore` plugin — RFC-0019, M4.** A purely local, no-server vector
store backed by [FAISS](https://github.com/facebookresearch/faiss). Passes the
same parity scenarios as the stdlib `SqliteVectorStore` (the M4 Definition of
Done).

## Install

```bash
pip install -e ./faiss
pip install faiss-cpu             # or: pip install xyberos[vectors]
```

> `faiss-cpu` wheels are available on PyPI for Linux/macOS; on Windows use a
> conda env or run the parity tests on a platform with wheels — the tests skip
> cleanly when the module is absent.

## Usage

```python
from xyberos import create_app
from xyberos_faiss import FaissPlugin

app = create_app()
app.load_plugin(FaissPlugin())

store = app.resolve("vector_store")
store.upsert("ns", "doc-1", [1.0, 0.0, 0.0, 0.0], {"text": "alpha"})
hits = store.query("ns", [1.0, 0.0, 0.0, 0.0], top_k=3)
```

## Design

- Each **namespace** is an in-memory `faiss.IndexFlatIP` over **L2-normalized**
  vectors, so inner-product scores equal cosine similarity (higher = more
  relevant, matching the `VectorStore` contract).
- `dim` is optional and auto-detected from the first upsert (`FAISS_DIM` env
  honored).
- `faiss` is imported **lazily**; a clear `ProviderError` is raised when it is
  missing.

## Tests

```bash
pip install pytest
pytest tests/          # unit + parity + plugin tests
```

Parity tests run the exact scenarios the `SqliteVectorStore` reference passes;
they skip cleanly when `faiss-cpu` is not importable on the current platform.

## Ship location

`[vectors]` extra (`faiss-cpu` already added to `pyproject.toml`).
