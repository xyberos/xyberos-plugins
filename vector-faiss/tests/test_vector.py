"""Unit tests for the FaissVectorStore (skip cleanly when faiss is missing)."""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("faiss") is None,
    reason="faiss-cpu is not installed on this platform",
)

from xyberos_faiss import FaissVectorStore  # noqa: E402


@pytest.fixture()
def store():
    return FaissVectorStore()


def test_upsert_and_query(store):
    store.upsert("ns", "a", [1.0, 0.0, 0.0], {"text": "alpha"})
    store.upsert("ns", "b", [0.0, 1.0, 0.0], {"text": "beta"})
    hits = store.query("ns", [1.0, 0.0, 0.0], top_k=2)
    assert hits[0].id == "a"
    assert hits[0].payload["text"] == "alpha"


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
