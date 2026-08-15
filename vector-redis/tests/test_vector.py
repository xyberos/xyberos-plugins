"""Unit tests for RedisVectorStore (fakeredis, no server needed)."""

from __future__ import annotations

import pytest

from xyberos_redis import RedisVectorStore


@pytest.fixture()
def client():
    return pytest.importorskip("fakeredis").FakeStrictRedis()


@pytest.fixture()
def store(client):
    return RedisVectorStore(client=client)


def test_upsert_and_query(store):
    store.upsert("ns", "a", [1.0, 0.0, 0.0], {"text": "alpha"})
    store.upsert("ns", "b", [0.0, 1.0, 0.0], {"text": "beta"})
    hits = store.query("ns", [1.0, 0.0, 0.0], top_k=2)
    assert hits[0].id == "a"
    assert hits[0].payload["text"] == "alpha"


def test_namespaces_isolated(store):
    store.upsert("one", "a", [1.0, 0.0, 0.0], {"text": "one"})
    store.upsert("two", "b", [0.0, 1.0, 0.0], {"text": "two"})
    assert [h.id for h in store.query("one", [1.0, 0.0, 0.0])] == ["a"]
    assert [h.id for h in store.query("two", [1.0, 0.0, 0.0])] == ["b"]


def test_delete(store):
    store.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0])
    store.upsert("ns", "b", [0.0, 1.0, 0.0, 0.0])
    store.delete("ns", "a")
    assert [h.id for h in store.query("ns", [1.0, 0.0, 0.0, 0.0], top_k=2)] == ["b"]


def test_clear(store):
    store.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0])
    store.clear("ns")
    assert store.query("ns", [1.0, 0.0, 0.0, 0.0]) == []
