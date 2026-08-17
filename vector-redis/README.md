# xyberos-redis

**Redis plugin — RFC-0019, M4.** `RedisVectorStore` + `RedisMemory` + cache
backing for `CacheResponder`, all lazy-importing `redis`. Covers the
`[state]` extra scope (cache + state + vector).

## Install

```bash
pip install xyberos-redis               # from PyPI
pip install "xyberos-redis[state]"      # pulls in redis

# development (editable, from this repo):
pip install -e ./redis
pip install redis               # or: pip install xyberos[state]
```

## Usage

```python
from xyberos import create_app
from xyberos_redis import RedisPlugin

app = create_app()
app.load_plugin(RedisPlugin(url="redis://localhost:6379"))   # or set REDIS_URL

vector = app.resolve("redis_vector")     # a VectorStore
memory = app.resolve("redis_memory")     # a Memory
cache  = app.resolve("redis_cache")      # exact-match string cache
```

`RedisPlugin(replace_defaults=True)` also swaps the app's `vector_store` /
`memory` providers.

### CacheResponder backing

`RedisVectorStore` is a full `VectorStore`, so it plugs straight into the core
`CacheResponder` for near-exact `prompt -> answer` caching:

```python
from xyberos.llm import HashEmbedder
from xyberos.router import CacheResponder
from xyberos_redis import RedisVectorStore

responder = CacheResponder(store=RedisVectorStore(url="redis://localhost:6379"),
                           embedder=HashEmbedder())
responder.teach("what is xyberos?", "a cognitive platform")
```

## Design

- **`RedisVectorStore`** — one Redis hash per namespace; vectors JSON-encoded;
  queries scored with exact cosine (the same scan-and-score approach as the
  stdlib `SqliteVectorStore`, so behavior — and parity — holds without needing
  a RediSearch vector module).
- **`RedisMemory`** — one entry per `store()` appended to a Redis list;
  `retrieve()` returns `MemoryEntry`s oldest-first, mirroring `SqliteMemory`.
- **`RedisStringCache`** — tiny exact-match `get/set/delete` with optional TTL.
- `redis` is imported **lazily**; a clear `ProviderError` is raised when missing.

## Tests

```bash
pip install pytest fakeredis
pytest tests/
```

Tests run against **fakeredis** (an in-memory redis-py client), so they need no
Redis server; they skip cleanly when `redis`/`fakeredis` are absent. The vector
parity tests run the exact scenarios the `SqliteVectorStore` reference passes.

## Ship location

`[state]` extra (`redis` already added to `pyproject.toml`).
