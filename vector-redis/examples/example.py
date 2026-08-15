"""Example (M4): Redis-backed vector store, memory, and CacheResponder backing.

Run from this folder (uses fakeredis so no Redis server is needed):

    python examples/example.py

To use a real Redis server, drop ``client=fakeredis...`` and pass
``url="redis://localhost:6379"`` (or set REDIS_URL).
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from types import SimpleNamespace

import fakeredis

from xyberos import create_app
from xyberos.llm import HashEmbedder
from xyberos.router import CacheResponder

from xyberos_redis import RedisMemory, RedisPlugin, RedisVectorStore


def main() -> None:
    client = fakeredis.FakeStrictRedis()
    app = create_app()
    app.load_plugin(RedisPlugin(client=client, key_prefix="demo"))

    # 1) Vector store
    vector = app.resolve("redis_vector")
    vector.upsert("examples", "doc-1", [1.0, 0.0, 0.0, 0.0], {"text": "north"})
    vector.upsert("examples", "doc-2", [0.0, 1.0, 0.0, 0.0], {"text": "east"})
    print("vector hits:", [(h.id, round(h.score, 3)) for h in vector.query("examples", [1.0, 0.1, 0.0, 0.0])])

    # 2) Memory
    memory = app.resolve("redis_memory")
    memory.store(SimpleNamespace(prompt="hello", response="hi", metadata={"user": "baltz"}))
    print("memory entries:", [(e.prompt, e.response) for e in memory.retrieve(SimpleNamespace())])

    # 3) CacheResponder backed by RedisVectorStore
    responder = CacheResponder(store=RedisVectorStore(client=client), embedder=HashEmbedder())
    responder.teach("what is xyberos?", "a cognitive platform")
    print("cache hit:", responder.respond(SimpleNamespace(prompt="what is xyberos?")))

    app.unload_plugin("redis")


if __name__ == "__main__":
    main()
