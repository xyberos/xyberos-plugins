"""Unit tests for the QdrantVectorStore (in-memory local mode)."""

from __future__ import annotations

import pytest

from xyberos_qdrant import QdrantVectorStore


@pytest.fixture()
def store():
    pytest.importorskip("qdrant_client")
    instance = QdrantVectorStore(location=":memory:")
    return instance


def test_upsert_and_query(store):
    store.upsert("ns", "a", [1.0, 0.0, 0.0], {"text": "alpha"})
    store.upsert("ns", "b", [0.0, 1.0, 0.0], {"text": "beta"})
    hits = store.query("ns", [1.0, 0.0, 0.0], top_k=2)
    assert hits[0].id == "a"
    assert hits[0].payload["text"] == "alpha"


def test_string_ids_round_trip(store):
    store.upsert("ns", "document-1", [1.0, 0.0], {"text": "one"})
    store.upsert("ns", "document-2", [0.0, 1.0], {"text": "two"})
    hits = store.query("ns", [1.0, 0.0], top_k=2)
    assert {h.id for h in hits} == {"document-1", "document-2"}
    assert {h.payload["text"] for h in hits} == {"one", "two"}


def test_delete(store):
    store.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0])
    store.upsert("ns", "b", [0.0, 1.0, 0.0, 0.0])
    store.delete("ns", "a")
    assert [h.id for h in store.query("ns", [1.0, 0.0, 0.0, 0.0], top_k=2)] == ["b"]


def test_clear(store):
    store.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0])
    store.clear("ns")
    assert store.query("ns", [1.0, 0.0, 0.0, 0.0]) == []


def test_missing_namespace_returns_empty(store):
    assert store.query("missing", [1.0, 0.0, 0.0, 0.0]) == []


def test_provider_error_when_client_missing(monkeypatch):
    import importlib.util

    if importlib.util.find_spec("qdrant_client"):
        pytest.skip("qdrant-client is installed")
    store = QdrantVectorStore(url="http://localhost:6333")
    with pytest.raises(Exception):
        store.upsert("ns", "a", [1.0, 0.0, 0.0])
