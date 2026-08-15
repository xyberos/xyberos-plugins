"""Exercise the FaissVectorStore logic against a numpy-backed fake faiss.

faiss-cpu has no wheels on every platform (e.g. Windows), so this module runs
the store's full logic — including the M4 parity scenarios — against a faithful
``IndexFlatIP`` stand-in. It gives real coverage wherever pytest runs; the
``test_parity.py`` module covers the real ``faiss-cpu`` when it is present.
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest


class _IndexFlatIP:
    """An in-memory inner-product index matching the faiss API subset used."""

    def __init__(self, dim: int) -> None:
        self._dim = int(dim)
        self._rows = np.empty((0, self._dim), dtype="float32")

    def add(self, x: object) -> None:
        self._rows = np.vstack([self._rows, np.asarray(x, dtype="float32")])

    @property
    def ntotal(self) -> int:
        return self._rows.shape[0]

    def search(self, x: object, k: int) -> tuple[np.ndarray, np.ndarray]:
        matrix = np.asarray(x, dtype="float32")
        if matrix.ndim == 1:
            matrix = matrix[None, :]
        scores = self._rows @ matrix.T
        n_queries = matrix.shape[0]
        k = min(int(k), self.ntotal)
        distances = np.zeros((n_queries, k), dtype="float32")
        indices = np.full((n_queries, k), -1, dtype="int64")
        for query in range(n_queries):
            order = np.argsort(scores[:, query])[::-1][:k]
            distances[query] = scores[order, query]
            indices[query] = order
        return distances, indices


@pytest.fixture(autouse=True)
def fake_faiss():
    """Inject a fake ``faiss`` module unless the real one is already present."""
    if sys.modules.get("faiss") is None:
        module = types.ModuleType("faiss")
        module.IndexFlatIP = _IndexFlatIP
        sys.modules["faiss"] = module
    yield


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


def test_parity_with_fake_faiss():
    from xyberos_faiss import FaissVectorStore

    run_parity_scenarios(FaissVectorStore())


def test_upsert_and_query_order():
    from xyberos_faiss import FaissVectorStore

    store = FaissVectorStore()
    store.upsert("ns", "a", [1.0, 0.0, 0.0], {"text": "alpha"})
    store.upsert("ns", "b", [0.0, 1.0, 0.0], {"text": "beta"})
    hits = store.query("ns", [1.0, 0.0, 0.0], top_k=2)
    assert hits[0].id == "a"
    assert hits[0].payload["text"] == "alpha"


def test_delete_and_clear():
    from xyberos_faiss import FaissVectorStore

    store = FaissVectorStore()
    store.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0])
    store.upsert("ns", "b", [0.0, 1.0, 0.0, 0.0])
    store.delete("ns", "a")
    assert [h.id for h in store.query("ns", [1.0, 0.0, 0.0, 0.0], top_k=2)] == ["b"]
    store.clear("ns")
    assert store.query("ns", [1.0, 0.0, 0.0, 0.0]) == []


def test_dimension_mismatch_raises():
    from xyberos_faiss import FaissVectorStore

    store = FaissVectorStore()
    store.upsert("ns", "a", [1.0, 0.0, 0.0])
    with pytest.raises(ValueError, match="dimension"):
        store.query("ns", [1.0, 0.0, 0.0, 0.0])
