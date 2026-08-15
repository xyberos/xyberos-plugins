"""Tests for the Redis cache story: CacheResponder backing + string cache."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from xyberos.llm import HashEmbedder
from xyberos.router import CacheResponder

from xyberos_redis import RedisStringCache, RedisVectorStore


@pytest.fixture()
def client():
    return pytest.importorskip("fakeredis").FakeStrictRedis()


def test_redis_vector_store_backs_cache_responder(client):
    """RedisVectorStore is a VectorStore, so it can back CacheResponder."""
    responder = CacheResponder(
        store=RedisVectorStore(client=client),
        embedder=HashEmbedder(),
        threshold=0.9,
    )
    responder.teach("what is xyberos?", "a cognitive platform")
    assert responder.size == 1

    answer = responder.respond(SimpleNamespace(prompt="what is xyberos?"))
    assert answer == "a cognitive platform"
    # A near-identical prompt also hits (exact-match embedding -> score 1.0).
    assert responder.respond(SimpleNamespace(prompt="what is xyberos?")) is not None


def test_redis_string_cache(client):
    cache = RedisStringCache(client=client)
    assert cache.get("k") is None
    cache.set("k", "v")
    assert cache.get("k") == "v"
    cache.delete("k")
    assert cache.get("k") is None


def test_redis_string_cache_clear(client):
    cache = RedisStringCache(client=client)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
