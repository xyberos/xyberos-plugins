"""M4 parity: FaissVectorStore must behave like SqliteVectorStore."""

from __future__ import annotations

import importlib.util

import pytest
from xyberos.vector import SqliteVectorStore

from xyberos_faiss import FaissVectorStore

QUERY = [1.0, 0.0, 0.0, 0.0]


def run_parity_scenarios(store) -> None:
    """The full VectorStore contract; every adapter must pass these."""
    store.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0], {"text": "alpha"})
    store.upsert("ns", "b", [0.8, 0.2, 0.0, 0.0], {"text": "beta"})
    store.upsert("ns", "c", [0.5, 0.5, 0.0, 0.0], {"text": "gamma"})
    store.upsert("other", "x", [1.0, 1.0, 1.0, 1.0], {"text": "other ns"})

    hits = store.query("ns", QUERY, top_k=3)
    assert [h.id for h in hits] == ["a", "b", "c"]
    assert hits[0].payload["text"] == "alpha"
    assert hits[0].score > hits[1].score > hits[2].score
    assert len(store.query("ns", QUERY, top_k=1)) == 1

    strict = store.query("ns", QUERY, top_k=3, threshold=0.99)
    assert [h.id for h in strict] == ["a"]

    store.delete("ns", "b")
    assert [h.id for h in store.query("ns", QUERY, top_k=3)] == ["a", "c"]
    assert [h.id for h in store.query("other", [1.0, 1.0, 1.0, 1.0], top_k=2)] == ["x"]
    assert all(abs(h.score) < 1e-6 for h in store.query("ns", [0.0, 0.0, 0.0, 1.0], top_k=2))

    store.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0], {"text": "alpha-v2"})
    assert store.query("ns", QUERY, top_k=1)[0].payload["text"] == "alpha-v2"

    store.clear("ns")
    assert store.query("ns", QUERY, top_k=3) == []
    assert [h.id for h in store.query("other", [1.0, 1.0, 1.0, 1.0], top_k=1)] == ["x"]


def test_sqlite_reference() -> None:
    """The stdlib reference passes the same scenarios the adapters must match."""
    run_parity_scenarios(SqliteVectorStore(":memory:"))


@pytest.mark.skipif(
    importlib.util.find_spec("faiss") is None,
    reason="faiss-cpu is not installed on this platform",
)
def test_faiss_parity():
    run_parity_scenarios(FaissVectorStore())
